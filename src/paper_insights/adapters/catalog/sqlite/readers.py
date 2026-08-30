from __future__ import annotations

import os
import sqlite3
import stat
from datetime import datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Literal
from urllib.parse import quote
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from paper_insights.domain.acquisition import (
    IdentifierScope,
    ObservedAuthor,
    ObservedCategory,
    ObservedIdentifier,
    ObservedPaperVersion,
)
from paper_insights.domain.corpus import (
    ArtifactKind,
    ArtifactRef,
    CitationInput,
    CitationSelector,
    CollectionView,
    InterruptedRunCandidate,
    PaperIdentity,
    PaperView,
    VersionObservation,
)
from paper_insights.domain.identifiers import (
    ArtifactId,
    CollectionId,
    PaperId,
    PaperSelector,
    PaperVersionId,
    RunId,
    Sha256,
    SnapshotId,
    SourceId,
    VersionObservationId,
)
from paper_insights.domain.retrieval import CatalogRevision, IndexDocument, SearchIdentifier

from .errors import CatalogConflict


class CatalogRevisionMismatch(RuntimeError):
    pass


def _open_immutable_catalog(database_path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(database_path, flags)
    except OSError as exc:
        raise OperationalError(None, None, exc) from exc
    try:
        _assert_immutable_catalog(database_path, descriptor)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _assert_immutable_catalog(database_path: Path, descriptor: int) -> None:
    opened = os.fstat(descriptor)
    try:
        current = os.lstat(database_path)
    except OSError as exc:
        raise OperationalError(None, None, exc) from exc
    if (
        not stat.S_ISREG(opened.st_mode)
        or stat.S_ISLNK(current.st_mode)
        or not stat.S_ISREG(current.st_mode)
        or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
    ):
        raise OperationalError(None, None, sqlite3.OperationalError("binding changed"))
    for suffix in ("-wal", "-shm"):
        try:
            os.lstat(f"{database_path}{suffix}")
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise OperationalError(None, None, exc) from exc
        raise OperationalError(
            None,
            None,
            sqlite3.OperationalError("catalog snapshot has an active WAL sidecar"),
        )


class SqliteCatalogSnapshot:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        database = engine.url.database
        if database is None or database == ":memory:":
            raise ValueError("catalog snapshots require a file-backed database")
        self._database_path = Path(database)
        self._read_engine: Engine | None = None
        self._connection: Connection | None = None
        self._file_descriptor: int | None = None
        self.revision = CatalogRevision(0)

    def __enter__(self) -> SqliteCatalogSnapshot:
        if self._connection is not None:
            raise RuntimeError("catalog snapshot is already open")
        file_descriptor = _open_immutable_catalog(self._database_path)
        database_uri = quote(f"/dev/fd/{file_descriptor}", safe="/")

        def _open_readonly() -> sqlite3.Connection:
            return sqlite3.connect(
                f"file:{database_uri}?mode=ro&immutable=1",
                uri=True,
                check_same_thread=False,
            )

        read_engine = create_engine(
            f"sqlite+pysqlite:///{self._database_path}",
            creator=_open_readonly,
            poolclass=NullPool,
        )
        try:
            connection = read_engine.connect()
            _assert_immutable_catalog(self._database_path, file_descriptor)
            connection.exec_driver_sql("PRAGMA query_only = ON")
            connection.exec_driver_sql("BEGIN")
            revision = connection.execute(
                sa.text("SELECT revision FROM catalog_meta WHERE singleton_id = 1")
            ).scalar_one()
        except BaseException:
            if "connection" in locals():
                connection.close()
            read_engine.dispose()
            os.close(file_descriptor)
            raise
        self._read_engine = read_engine
        self._connection = connection
        self._file_descriptor = file_descriptor
        self.revision = CatalogRevision(int(revision))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc_type, exc, traceback
        connection = self._connection
        if connection is not None:
            try:
                connection.rollback()
            finally:
                connection.close()
                self._connection = None
                if self._read_engine is not None:
                    self._read_engine.dispose()
                    self._read_engine = None
                if self._file_descriptor is not None:
                    os.close(self._file_descriptor)
                    self._file_descriptor = None
        return False

    def _require_open(self) -> Connection:
        if self._connection is None:
            raise RuntimeError("catalog snapshot is closed")
        return self._connection

    def list_collections(self) -> tuple[CollectionView, ...]:
        connection = self._require_open()
        rows = connection.execute(
            sa.text(
                "SELECT c.id, c.slug, c.title, c.created_at, c.updated_at, "
                "count(cp.paper_id) AS paper_count "
                "FROM collections AS c "
                "LEFT JOIN collection_papers AS cp ON cp.collection_id = c.id "
                "GROUP BY c.id, c.slug, c.title, c.created_at, c.updated_at "
                "ORDER BY c.slug, c.id"
            )
        ).mappings()
        return tuple(
            CollectionView(
                collection_id=CollectionId(UUID(row["id"])),
                slug=row["slug"],
                title=row["title"],
                paper_count=row["paper_count"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        )

    def list_interrupted_runs(self, cutoff: datetime) -> tuple[InterruptedRunCandidate, ...]:
        if cutoff.tzinfo is None or cutoff.utcoffset() != timedelta(0):
            raise ValueError("interrupted run cutoff must use UTC")
        connection = self._require_open()
        rows = connection.execute(
            sa.text(
                "SELECT r.id, r.started_at, r.selected_records, count(item.run_id) AS recorded "
                "FROM ingestion_runs AS r LEFT JOIN ingestion_run_items AS item "
                "ON item.run_id = r.id WHERE r.status = 'running' AND r.started_at < :cutoff "
                "GROUP BY r.id, r.started_at, r.selected_records ORDER BY r.started_at, r.id"
            ),
            {"cutoff": cutoff.isoformat()},
        ).mappings()
        return tuple(
            InterruptedRunCandidate(
                run_id=RunId(UUID(row["id"])),
                started_at=datetime.fromisoformat(row["started_at"]),
                selected_records=int(row["selected_records"]),
                recorded_items=int(row["recorded"]),
            )
            for row in rows
        )

    def get_paper(self, selector: PaperSelector) -> PaperView | None:
        connection = self._require_open()
        paper_id = self._resolve_paper_id(selector)
        if paper_id is None:
            return None
        paper_row = (
            connection.execute(
                sa.text("SELECT id, created_at FROM papers WHERE id = :id"),
                {"id": str(paper_id)},
            )
            .mappings()
            .one()
        )
        observation_rows = connection.execute(
            sa.text(
                "SELECT vo.id FROM version_observations AS vo "
                "JOIN paper_versions AS pv ON pv.id = vo.paper_version_id "
                "WHERE pv.paper_id = :paper_id "
                "ORDER BY vo.observed_at, vo.id"
            ),
            {"paper_id": str(paper_id)},
        ).scalars()
        observations = tuple(self._load_observation(value) for value in observation_rows)
        artifact_rows = connection.execute(
            sa.text(
                "SELECT a.id, a.paper_version_id, a.version_observation_id, b.sha256, a.kind "
                "FROM artifacts AS a "
                "JOIN stored_blobs AS b ON b.id = a.stored_blob_id "
                "JOIN paper_versions AS pv ON pv.id = a.paper_version_id "
                "WHERE pv.paper_id = :paper_id ORDER BY a.created_at, a.id"
            ),
            {"paper_id": str(paper_id)},
        ).mappings()
        artifacts = tuple(
            ArtifactRef(
                artifact_id=ArtifactId(UUID(row["id"])),
                paper_version_id=PaperVersionId(UUID(row["paper_version_id"])),
                version_observation_id=(
                    VersionObservationId(UUID(row["version_observation_id"]))
                    if row["version_observation_id"] is not None
                    else None
                ),
                sha256=Sha256(row["sha256"]),
                kind=ArtifactKind(row["kind"]),
            )
            for row in artifact_rows
        )
        return PaperView(
            identity=PaperIdentity(
                paper_id=paper_id,
                created_at=datetime.fromisoformat(paper_row["created_at"]),
            ),
            observations=observations,
            artifacts=artifacts,
        )

    def list_index_documents(self) -> tuple[IndexDocument, ...]:
        connection = self._require_open()
        version_rows = connection.execute(
            sa.text(
                "SELECT pv.id, pv.paper_id, pv.source_id FROM paper_versions AS pv "
                "WHERE pv.is_current = 1 ORDER BY pv.paper_id, pv.source_id, pv.id"
            )
        ).mappings()
        documents: list[IndexDocument] = []
        for version in version_rows:
            observation = (
                connection.execute(
                    sa.text(
                        "SELECT vo.id, vo.title, vo.abstract, vo.language, vo.submitted_at, "
                        "b.sha256 "
                        "FROM version_observations AS vo "
                        "LEFT JOIN artifacts AS a ON a.version_observation_id = vo.id "
                        "AND a.kind = 'metadata' "
                        "LEFT JOIN stored_blobs AS b ON b.id = a.stored_blob_id "
                        "WHERE vo.paper_version_id = :version_id "
                        "ORDER BY vo.observed_at DESC, vo.id DESC LIMIT 1"
                    ),
                    {"version_id": version["id"]},
                )
                .mappings()
                .one_or_none()
            )
            if observation is None or observation["sha256"] is None:
                raise RuntimeError(f"current version {version['id']} has no metadata artifact")
            author_rows = connection.execute(
                sa.text(
                    "SELECT raw_name FROM paper_authors "
                    "WHERE version_observation_id = :observation_id ORDER BY position"
                ),
                {"observation_id": observation["id"]},
            ).scalars()
            category_rows = connection.execute(
                sa.text(
                    "SELECT category FROM paper_version_categories "
                    "WHERE version_observation_id = :observation_id ORDER BY position"
                ),
                {"observation_id": observation["id"]},
            ).scalars()
            identifier_rows = connection.execute(
                sa.text(
                    "SELECT scheme, canonical_value, 'paper' AS scope, 0 AS scope_order "
                    "FROM paper_identifiers WHERE paper_id = :paper_id "
                    "UNION ALL "
                    "SELECT scheme, canonical_value, 'version' AS scope, 1 AS scope_order "
                    "FROM version_identifiers WHERE paper_version_id = :version_id "
                    "ORDER BY scope_order, scheme, canonical_value"
                ),
                {
                    "paper_id": version["paper_id"],
                    "version_id": version["id"],
                },
            ).mappings()
            collection_rows = connection.execute(
                sa.text(
                    "SELECT c.id, c.slug FROM collection_papers AS cp "
                    "JOIN collections AS c ON c.id = cp.collection_id "
                    "WHERE cp.paper_id = :paper_id ORDER BY c.slug, c.id"
                ),
                {"paper_id": version["paper_id"]},
            ).mappings()
            collections = tuple(collection_rows)
            documents.append(
                IndexDocument(
                    paper_id=PaperId(UUID(version["paper_id"])),
                    paper_version_id=PaperVersionId(UUID(version["id"])),
                    version_observation_id=VersionObservationId(UUID(observation["id"])),
                    source_id=SourceId(version["source_id"]),
                    title=observation["title"],
                    abstract=observation["abstract"],
                    metadata_artifact_sha256=Sha256(observation["sha256"]),
                    authors=tuple(author_rows),
                    categories=tuple(category_rows),
                    language=observation["language"],
                    submitted_at=(
                        datetime.fromisoformat(observation["submitted_at"])
                        if observation["submitted_at"] is not None
                        else None
                    ),
                    collection_ids=tuple(CollectionId(UUID(row["id"])) for row in collections),
                    collection_slugs=tuple(row["slug"] for row in collections),
                    identifiers=tuple(
                        SearchIdentifier(
                            scheme=row["scheme"],
                            canonical_value=row["canonical_value"],
                            scope=IdentifierScope(row["scope"]),
                        )
                        for row in identifier_rows
                    ),
                )
            )
        return tuple(documents)

    def get_citation_input(self, selector: CitationSelector) -> CitationInput | None:
        connection = self._require_open()
        paper_id = self._resolve_paper_id(selector.paper)
        if paper_id is None:
            return None
        if selector.paper_version_id is None:
            source_id = "arxiv" if selector.paper.arxiv_id is not None else None
            version_ids = tuple(
                connection.execute(
                    sa.text(
                        "SELECT id FROM paper_versions WHERE paper_id = :paper_id "
                        "AND is_current = 1 AND (:source_id IS NULL OR source_id = :source_id) "
                        "ORDER BY source_id, id"
                    ),
                    {"paper_id": str(paper_id), "source_id": source_id},
                ).scalars()
            )
            if not version_ids:
                return None
            if len(version_ids) > 1:
                raise CatalogConflict()
            version_id = version_ids[0]
        else:
            version_id = connection.execute(
                sa.text(
                    "SELECT id FROM paper_versions WHERE id = :version_id AND paper_id = :paper_id"
                ),
                {
                    "version_id": str(selector.paper_version_id),
                    "paper_id": str(paper_id),
                },
            ).scalar_one_or_none()
        if version_id is None:
            return None
        observation_id = connection.execute(
            sa.text(
                "SELECT id FROM version_observations WHERE paper_version_id = :version_id "
                "ORDER BY observed_at DESC, id DESC LIMIT 1"
            ),
            {"version_id": version_id},
        ).scalar_one_or_none()
        if observation_id is None:
            return None
        observation = self._load_observation(observation_id)
        provenance = self._observation_provenance(observation_id)
        return CitationInput(
            paper_id=paper_id,
            observation=observation,
            source_id=SourceId(provenance["source_id"]),
            source_item_id=provenance["source_item_id"],
            snapshot_id=SnapshotId(UUID(provenance["snapshot_id"])),
            record_ordinal=int(provenance["record_ordinal"]),
            retrieved_at=datetime.fromisoformat(provenance["retrieved_at"]),
        )

    def _resolve_paper_id(self, selector: PaperSelector) -> PaperId | None:
        connection = self._require_open()
        if selector.paper_id is not None:
            value = connection.execute(
                sa.text("SELECT id FROM papers WHERE id = :id"),
                {"id": str(selector.paper_id)},
            ).scalar_one_or_none()
        elif selector.doi is not None:
            values = tuple(
                connection.execute(
                    sa.text(
                        "SELECT paper_id FROM paper_identifiers "
                        "WHERE scheme = 'doi' AND canonical_value = :canonical "
                        "UNION "
                        "SELECT pv.paper_id FROM version_identifiers AS vi "
                        "JOIN paper_versions AS pv ON pv.id = vi.paper_version_id "
                        "WHERE vi.scheme = 'doi' AND vi.canonical_value = :canonical "
                        "ORDER BY paper_id"
                    ),
                    {"canonical": selector.doi},
                ).scalars()
            )
            if len(values) > 1:
                raise CatalogConflict()
            value = values[0] if values else None
        else:
            value = connection.execute(
                sa.text(
                    "SELECT paper_id FROM paper_identifiers "
                    "WHERE scheme = 'arxiv' AND canonical_value = :canonical"
                ),
                {"canonical": selector.arxiv_id},
            ).scalar_one_or_none()
        return PaperId(UUID(value)) if value is not None else None

    def _observation_provenance(self, observation_id: str) -> sa.RowMapping:
        row = (
            self._require_open()
            .execute(
                sa.text(
                    "SELECT ss.id AS snapshot_id, ss.source_id, ss.retrieved_at, "
                    "vo.origin_run_id, vo.origin_record_ordinal AS record_ordinal, "
                    "sr.source_item_id, sr.source_version_key "
                    "FROM version_observations AS vo "
                    "JOIN source_snapshots AS ss ON ss.id = vo.origin_source_snapshot_id "
                    "JOIN snapshot_records AS sr ON sr.source_snapshot_id = "
                    "vo.origin_source_snapshot_id AND sr.ordinal = vo.origin_record_ordinal "
                    "WHERE vo.id = :observation_id"
                ),
                {"observation_id": observation_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["source_item_id"] is None or row["source_version_key"] is None:
            raise RuntimeError("version observation has no complete source provenance")
        return row

    def _load_observation(self, observation_id: str) -> VersionObservation:
        connection = self._require_open()
        row = (
            connection.execute(
                sa.text(
                    "SELECT vo.*, pv.source_id FROM version_observations AS vo "
                    "JOIN paper_versions AS pv ON pv.id = vo.paper_version_id "
                    "WHERE vo.id = :id"
                ),
                {"id": observation_id},
            )
            .mappings()
            .one()
        )
        provenance = self._observation_provenance(observation_id)
        author_rows = connection.execute(
            sa.text(
                "SELECT raw_name, affiliation_raw FROM paper_authors "
                "WHERE version_observation_id = :id ORDER BY position"
            ),
            {"id": observation_id},
        ).mappings()
        category_rows = connection.execute(
            sa.text(
                "SELECT category, is_primary FROM paper_version_categories "
                "WHERE version_observation_id = :id ORDER BY position"
            ),
            {"id": observation_id},
        ).mappings()
        paper_id = connection.execute(
            sa.text("SELECT paper_id FROM paper_versions WHERE id = :version_id"),
            {"version_id": row["paper_version_id"]},
        ).scalar_one()
        identifier_rows = connection.execute(
            sa.text(
                "SELECT pi.scheme, pi.canonical_value, 'paper' AS scope "
                "FROM paper_identifiers AS pi JOIN paper_identifier_evidence AS evidence "
                "ON evidence.scheme = pi.scheme AND evidence.canonical_value = "
                "pi.canonical_value WHERE pi.paper_id = :paper_id "
                "AND evidence.source_snapshot_id = :snapshot "
                "AND evidence.record_ordinal = :record "
                "UNION ALL "
                "SELECT vi.scheme, vi.canonical_value, 'version' AS scope "
                "FROM version_identifiers AS vi JOIN version_identifier_evidence AS evidence "
                "ON evidence.scheme = vi.scheme AND evidence.canonical_value = "
                "vi.canonical_value WHERE vi.paper_version_id = :version_id "
                "AND evidence.source_snapshot_id = :snapshot "
                "AND evidence.record_ordinal = :record "
                "ORDER BY 1, 2"
            ),
            {
                "paper_id": paper_id,
                "version_id": row["paper_version_id"],
                "snapshot": provenance["snapshot_id"],
                "record": provenance["record_ordinal"],
            },
        ).mappings()
        observed = ObservedPaperVersion(
            source_id=SourceId(row["source_id"]),
            source_item_id=provenance["source_item_id"],
            source_version_key=provenance["source_version_key"],
            title=row["title"],
            abstract=row["abstract"],
            page_ordinal=int(
                connection.execute(
                    sa.text(
                        "SELECT page_ordinal FROM ingestion_run_snapshots "
                        "WHERE run_id = :run AND source_snapshot_id = :snapshot"
                    ),
                    {
                        "run": provenance["origin_run_id"],
                        "snapshot": provenance["snapshot_id"],
                    },
                ).scalar_one()
            ),
            record_ordinal=int(provenance["record_ordinal"]),
            normalized_sha256=Sha256(row["normalized_sha256"]),
            authors=tuple(
                ObservedAuthor(
                    raw_name=author["raw_name"], affiliation_raw=author["affiliation_raw"]
                )
                for author in author_rows
            ),
            categories=tuple(
                ObservedCategory(
                    value=category["category"], is_primary=bool(category["is_primary"])
                )
                for category in category_rows
            ),
            identifiers=tuple(
                ObservedIdentifier(
                    scheme=identifier["scheme"],
                    canonical_value=identifier["canonical_value"],
                    scope=IdentifierScope(identifier["scope"]),
                )
                for identifier in identifier_rows
                if not (
                    identifier["scheme"] == row["source_id"]
                    and identifier["canonical_value"]
                    in (provenance["source_item_id"], provenance["source_version_key"])
                )
            ),
            comment=row["comment"],
            journal_reference=row["journal_reference"],
            language=row["language"],
            source_url=row["source_url"],
            submitted_at=(
                datetime.fromisoformat(row["submitted_at"])
                if row["submitted_at"] is not None
                else None
            ),
            announced_at=(
                datetime.fromisoformat(row["announced_at"])
                if row["announced_at"] is not None
                else None
            ),
        )
        return VersionObservation(
            observation_id=VersionObservationId(UUID(row["id"])),
            paper_version_id=PaperVersionId(UUID(row["paper_version_id"])),
            observed=observed,
            observed_at=datetime.fromisoformat(row["observed_at"]),
        )


class SqliteCatalogReader:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def snapshot(self) -> SqliteCatalogSnapshot:
        return SqliteCatalogSnapshot(self._engine)


class SqliteCatalogRevisionLease:
    def __init__(self, engine: Engine, expected: CatalogRevision) -> None:
        self._engine = engine
        self._expected = expected
        self._connection: Connection | None = None
        self.revision = expected

    def __enter__(self) -> SqliteCatalogRevisionLease:
        connection = self._engine.connect()
        try:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            current = CatalogRevision(
                int(
                    connection.execute(
                        sa.text("SELECT revision FROM catalog_meta WHERE singleton_id = 1")
                    ).scalar_one()
                )
            )
            if current != self._expected:
                raise CatalogRevisionMismatch(
                    f"catalog revision is {current.value}, expected {self._expected.value}"
                )
        except BaseException:
            connection.rollback()
            connection.close()
            raise
        self._connection = connection
        self.revision = current
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc_type, exc, traceback
        connection = self._connection
        if connection is not None:
            try:
                connection.rollback()
            finally:
                connection.close()
                self._connection = None
        return False


class SqliteCatalogRevisionGuard:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def hold_if_current(self, expected: CatalogRevision) -> SqliteCatalogRevisionLease:
        return SqliteCatalogRevisionLease(self._engine, expected)
