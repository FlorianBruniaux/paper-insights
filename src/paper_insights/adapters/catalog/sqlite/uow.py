from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from types import TracebackType
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Connection, Engine

from paper_insights.application.ports.clock import Clock
from paper_insights.application.ports.ids import IdGenerator
from paper_insights.domain.acquisition import IdentifierScope, ObservedPaperVersion
from paper_insights.domain.corpus import (
    AddCollectionPaper,
    AttachedSnapshotRef,
    AttachPreparedRun,
    CollectionView,
    CreateCollection,
    IngestionFailureStage,
    IngestionItemRef,
    IngestionOutcome,
    IngestionRunRef,
    IngestionStatus,
    IngestionSummary,
    InterruptedRunRepairOutcome,
    InterruptedRunRepairResult,
    PaperIdentity,
    PreparedSnapshotAttachment,
    RecordIngestionFailure,
    RecordIngestionItem,
    RemoveCollectionPaper,
    RenameCollection,
    RepairInterruptedRun,
    RunCounters,
    StoredBlobRef,
)
from paper_insights.domain.errors import ErrorCode
from paper_insights.domain.identifiers import (
    ArtifactId,
    AuthorId,
    BlobId,
    CollectionId,
    PaperId,
    PaperSelector,
    PaperVersionId,
    RunId,
    SnapshotId,
    VersionObservationId,
)


class CatalogConflict(RuntimeError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.CATALOG_CONFLICT.value)


def _utc_text(value: datetime) -> str:
    return value.isoformat()


def _title_normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


class SqliteCorpusRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def resolve_paper(self, selector: PaperSelector) -> PaperIdentity | None:
        if selector.paper_id is not None:
            row = (
                self._connection.execute(
                    sa.text("SELECT id, created_at FROM papers WHERE id = :id"),
                    {"id": str(selector.paper_id)},
                )
                .mappings()
                .one_or_none()
            )
        else:
            scheme = "arxiv" if selector.arxiv_id is not None else "doi"
            canonical = selector.arxiv_id if selector.arxiv_id is not None else selector.doi
            row = (
                self._connection.execute(
                    sa.text(
                        "SELECT p.id, p.created_at FROM paper_identifiers AS pi "
                        "JOIN papers AS p ON p.id = pi.paper_id "
                        "WHERE pi.scheme = :scheme AND pi.canonical_value = :canonical"
                    ),
                    {"scheme": scheme, "canonical": canonical},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return PaperIdentity(
            paper_id=PaperId(UUID(row["id"])),
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class SqliteIngestionRepository:
    def __init__(
        self,
        connection: Connection,
        clock: Clock,
        ids: IdGenerator,
        mark_visible: Callable[[], None],
        revision_after_commit: Callable[[], int],
    ) -> None:
        self._connection = connection
        self._clock = clock
        self._ids = ids
        self._mark_visible = mark_visible
        self._revision_after_commit = revision_after_commit

    def _new_id(self) -> UUID:
        return self._ids.new()

    def _ensure_blob(self, blob: StoredBlobRef) -> BlobId:
        row = (
            self._connection.execute(
                sa.text(
                    "SELECT id, size_bytes, media_type, relative_path FROM stored_blobs "
                    "WHERE sha256 = :sha"
                ),
                {"sha": str(blob.sha256)},
            )
            .mappings()
            .one_or_none()
        )
        expected_path = blob.relative_path.as_posix()
        if row is not None:
            if (
                int(row["size_bytes"]) != blob.size_bytes
                or row["media_type"] != blob.media_type
                or row["relative_path"] != expected_path
            ):
                raise CatalogConflict()
            return BlobId(UUID(row["id"]))
        blob_id = BlobId(self._new_id())
        self._connection.execute(
            sa.text(
                "INSERT INTO stored_blobs "
                "(id, sha256, size_bytes, media_type, relative_path, created_at) "
                "VALUES (:id, :sha, :size, :media, :path, :created_at)"
            ),
            {
                "id": str(blob_id),
                "sha": str(blob.sha256),
                "size": blob.size_bytes,
                "media": blob.media_type,
                "path": expected_path,
                "created_at": _utc_text(self._clock.now()),
            },
        )
        return blob_id

    def attach_prepared_run(self, command: AttachPreparedRun) -> IngestionRunRef:
        existing = self._connection.execute(
            sa.text("SELECT 1 FROM ingestion_runs WHERE id = :id"),
            {"id": str(command.run_id)},
        ).scalar_one_or_none()
        if existing is not None:
            return self._replay_run(command)

        snapshot_refs: list[AttachedSnapshotRef] = []
        snapshot_ids: dict[int, SnapshotId] = {}
        for page in command.pages:
            blob_id = self._blob_for_capture(page)
            if blob_id is None:
                blob_id = self._ensure_blob(page.blob)
            snapshot_id = self._attach_snapshot(command, page, blob_id)
            snapshot_ids[page.page_ordinal] = snapshot_id
            snapshot_refs.append(
                AttachedSnapshotRef(
                    page_ordinal=page.page_ordinal,
                    snapshot_id=snapshot_id,
                )
            )

        self._connection.execute(
            sa.text(
                "INSERT INTO ingestion_runs "
                "(id, source_id, prepared_digest, query_json, status, started_at, "
                "selected_records, new_papers, new_versions, metadata_updates, "
                "unchanged_records, failed_records) "
                "VALUES (:id, :source, :digest, :query, 'running', :started, "
                ":selected, 0, 0, 0, 0, 0)"
            ),
            {
                "id": str(command.run_id),
                "source": str(command.source_id),
                "digest": str(command.prepared_digest),
                "query": command.query_json,
                "started": _utc_text(self._clock.now()),
                "selected": command.selected_records,
            },
        )
        for page in command.pages:
            self._connection.execute(
                sa.text(
                    "INSERT INTO ingestion_run_snapshots "
                    "(run_id, page_ordinal, source_snapshot_id, source_id) "
                    "VALUES (:run, :page, :snapshot, :source)"
                ),
                {
                    "run": str(command.run_id),
                    "page": page.page_ordinal,
                    "snapshot": str(snapshot_ids[page.page_ordinal]),
                    "source": str(command.source_id),
                },
            )
        for selection_ordinal, locator in enumerate(command.selected_locators):
            self._connection.execute(
                sa.text(
                    "INSERT INTO ingestion_run_selected_records "
                    "(run_id, selection_ordinal, source_snapshot_id, record_ordinal) "
                    "VALUES (:run, :selection, :snapshot, :record)"
                ),
                {
                    "run": str(command.run_id),
                    "selection": selection_ordinal,
                    "snapshot": str(snapshot_ids[locator.page_ordinal]),
                    "record": locator.record_ordinal,
                },
            )
        self._mark_visible()
        return IngestionRunRef(
            run_id=command.run_id,
            revision=self._revision_after_commit(),
            snapshots=tuple(snapshot_refs),
        )

    def _blob_for_capture(self, page: PreparedSnapshotAttachment) -> BlobId | None:
        row = (
            self._connection.execute(
                sa.text(
                    "SELECT ss.stored_blob_id, b.sha256, b.size_bytes, b.media_type, "
                    "b.relative_path FROM source_snapshots AS ss "
                    "JOIN stored_blobs AS b ON b.id = ss.stored_blob_id "
                    "WHERE ss.capture_id = :capture"
                ),
                {"capture": str(page.capture_id)},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        if (
            row["sha256"] != str(page.blob.sha256)
            or int(row["size_bytes"]) != page.blob.size_bytes
            or row["media_type"] != page.blob.media_type
            or row["relative_path"] != page.blob.relative_path.as_posix()
        ):
            raise CatalogConflict()
        return BlobId(UUID(row["stored_blob_id"]))

    def _attach_snapshot(
        self,
        command: AttachPreparedRun,
        page: PreparedSnapshotAttachment,
        blob_id: BlobId,
    ) -> SnapshotId:
        row = (
            self._connection.execute(
                sa.text(
                    "SELECT id, source_id, stored_blob_id, request_fingerprint, "
                    "retrieved_at, next_cursor FROM source_snapshots WHERE capture_id = :capture"
                ),
                {"capture": str(page.capture_id)},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            snapshot_id = SnapshotId(self._new_id())
            self._connection.execute(
                sa.text(
                    "INSERT INTO source_snapshots "
                    "(id, capture_id, source_id, stored_blob_id, request_fingerprint, "
                    "retrieved_at, next_cursor) "
                    "VALUES (:id, :capture, :source, :blob, :request, :retrieved, :cursor)"
                ),
                {
                    "id": str(snapshot_id),
                    "capture": str(page.capture_id),
                    "source": str(command.source_id),
                    "blob": str(blob_id),
                    "request": str(page.request_fingerprint),
                    "retrieved": _utc_text(page.retrieved_at),
                    "cursor": page.next_cursor,
                },
            )
            for record in page.records:
                locator = record.locator
                self._connection.execute(
                    sa.text(
                        "INSERT INTO snapshot_records "
                        "(source_snapshot_id, ordinal, source_item_id, source_version_key, "
                        "raw_record_sha256) VALUES (:snapshot, :ordinal, :item, :version, :sha)"
                    ),
                    {
                        "snapshot": str(snapshot_id),
                        "ordinal": locator.record_ordinal,
                        "item": locator.source_item_id,
                        "version": locator.source_version_key,
                        "sha": str(locator.raw_record_sha256),
                    },
                )
            return snapshot_id
        immutable = (
            row["source_id"],
            row["stored_blob_id"],
            row["request_fingerprint"],
            row["retrieved_at"],
            row["next_cursor"],
        )
        expected = (
            str(command.source_id),
            str(blob_id),
            str(page.request_fingerprint),
            _utc_text(page.retrieved_at),
            page.next_cursor,
        )
        snapshot_id = SnapshotId(UUID(row["id"]))
        records = tuple(
            self._connection.execute(
                sa.text(
                    "SELECT ordinal, source_item_id, source_version_key, raw_record_sha256 "
                    "FROM snapshot_records WHERE source_snapshot_id = :snapshot ORDER BY ordinal"
                ),
                {"snapshot": str(snapshot_id)},
            )
            .mappings()
            .all()
        )
        expected_records = tuple(
            (
                record.locator.record_ordinal,
                record.locator.source_item_id,
                record.locator.source_version_key,
                str(record.locator.raw_record_sha256),
            )
            for record in page.records
        )
        actual_records = tuple(
            (
                int(record["ordinal"]),
                record["source_item_id"],
                record["source_version_key"],
                record["raw_record_sha256"],
            )
            for record in records
        )
        if immutable != expected or actual_records != expected_records:
            raise CatalogConflict()
        return snapshot_id

    def _replay_run(self, command: AttachPreparedRun) -> IngestionRunRef:
        run = (
            self._connection.execute(
                sa.text(
                    "SELECT source_id, prepared_digest, query_json, selected_records "
                    "FROM ingestion_runs WHERE id = :run"
                ),
                {"run": str(command.run_id)},
            )
            .mappings()
            .one()
        )
        if (
            run["source_id"] != str(command.source_id)
            or run["prepared_digest"] != str(command.prepared_digest)
            or run["query_json"] != command.query_json
            or int(run["selected_records"]) != command.selected_records
        ):
            raise CatalogConflict()
        persisted_pages = tuple(
            self._connection.execute(
                sa.text(
                    "SELECT irs.page_ordinal, irs.source_snapshot_id, ss.capture_id, "
                    "ss.stored_blob_id, b.sha256 FROM ingestion_run_snapshots AS irs "
                    "JOIN source_snapshots AS ss ON ss.id = irs.source_snapshot_id "
                    "JOIN stored_blobs AS b ON b.id = ss.stored_blob_id "
                    "WHERE irs.run_id = :run ORDER BY irs.page_ordinal"
                ),
                {"run": str(command.run_id)},
            )
            .mappings()
            .all()
        )
        if len(persisted_pages) != len(command.pages):
            raise CatalogConflict()
        refs: list[AttachedSnapshotRef] = []
        for page, persisted in zip(command.pages, persisted_pages, strict=True):
            if (
                int(persisted["page_ordinal"]) != page.page_ordinal
                or persisted["capture_id"] != str(page.capture_id)
                or persisted["sha256"] != str(page.blob.sha256)
            ):
                raise CatalogConflict()
            snapshot_id = self._attach_snapshot(
                command,
                page,
                BlobId(UUID(persisted["stored_blob_id"])),
            )
            if str(snapshot_id) != persisted["source_snapshot_id"]:
                raise CatalogConflict()
            refs.append(
                AttachedSnapshotRef(page_ordinal=page.page_ordinal, snapshot_id=snapshot_id)
            )
        selected = tuple(
            self._connection.execute(
                sa.text(
                    "SELECT irs.page_ordinal, selected.record_ordinal "
                    "FROM ingestion_run_selected_records AS selected "
                    "JOIN ingestion_run_snapshots AS irs ON irs.run_id = selected.run_id "
                    "AND irs.source_snapshot_id = selected.source_snapshot_id "
                    "WHERE selected.run_id = :run ORDER BY selected.selection_ordinal"
                ),
                {"run": str(command.run_id)},
            ).all()
        )
        expected_selected = tuple(
            (item.page_ordinal, item.record_ordinal) for item in command.selected_locators
        )
        if tuple((int(row[0]), int(row[1])) for row in selected) != expected_selected:
            raise CatalogConflict()
        return IngestionRunRef(
            run_id=command.run_id,
            revision=self._revision_after_commit(),
            snapshots=tuple(refs),
        )

    def _selected_record(
        self, run_id: RunId, snapshot_id: SnapshotId, ordinal: int
    ) -> sa.RowMapping:
        row = (
            self._connection.execute(
                sa.text(
                    "SELECT r.status, r.source_id, irs.page_ordinal, sr.source_item_id, "
                    "sr.source_version_key, sr.raw_record_sha256, sr.version_observation_id "
                    "FROM ingestion_run_selected_records AS selected "
                    "JOIN ingestion_runs AS r ON r.id = selected.run_id "
                    "JOIN ingestion_run_snapshots AS irs ON irs.run_id = selected.run_id "
                    "AND irs.source_snapshot_id = selected.source_snapshot_id "
                    "JOIN snapshot_records AS sr ON sr.source_snapshot_id = "
                    "selected.source_snapshot_id "
                    "AND sr.ordinal = selected.record_ordinal "
                    "WHERE selected.run_id = :run AND selected.source_snapshot_id = :snapshot "
                    "AND selected.record_ordinal = :ordinal"
                ),
                {"run": str(run_id), "snapshot": str(snapshot_id), "ordinal": ordinal},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise CatalogConflict()
        return row

    def record_item(self, command: RecordIngestionItem) -> IngestionItemRef:
        record = command.record
        selected = self._selected_record(command.run_id, record.snapshot_id, record.record_ordinal)
        existing = self._load_item(command.run_id, record.snapshot_id, record.record_ordinal)
        if existing is not None:
            if existing.outcome is IngestionOutcome.FAILED:
                raise CatalogConflict()
            observed_hash = self._connection.execute(
                sa.text("SELECT normalized_sha256 FROM version_observations WHERE id = :id"),
                {"id": str(existing.version_observation_id)},
            ).scalar_one()
            if observed_hash != str(record.observed.normalized_sha256):
                raise CatalogConflict()
            return existing
        observed = record.observed
        if (
            selected["status"] != IngestionStatus.RUNNING.value
            or selected["source_id"] != str(observed.source_id)
            or int(selected["page_ordinal"]) != observed.page_ordinal
            or selected["source_item_id"] != observed.source_item_id
            or selected["source_version_key"] != observed.source_version_key
        ):
            raise CatalogConflict()
        if selected["version_observation_id"] is not None:
            linked = (
                self._connection.execute(
                    sa.text(
                        "SELECT vo.normalized_sha256, pv.source_id, pv.source_version_key "
                        "FROM version_observations AS vo JOIN paper_versions AS pv "
                        "ON pv.id = vo.paper_version_id WHERE vo.id = :observation"
                    ),
                    {"observation": selected["version_observation_id"]},
                )
                .mappings()
                .one()
            )
            if (
                linked["normalized_sha256"] != str(observed.normalized_sha256)
                or linked["source_id"] != str(observed.source_id)
                or linked["source_version_key"] != observed.source_version_key
            ):
                raise CatalogConflict()

        paper_identifiers = [(str(observed.source_id), observed.source_item_id)] + [
            (item.scheme, item.canonical_value)
            for item in observed.identifiers
            if item.scope is IdentifierScope.PAPER
        ]
        paper_targets = self._identifier_targets("paper_identifiers", "paper_id", paper_identifiers)
        if len(paper_targets) > 1:
            raise CatalogConflict()
        paper_id = PaperId(UUID(next(iter(paper_targets)))) if paper_targets else None
        created_paper = False

        version_identifiers = [(str(observed.source_id), observed.source_version_key)] + [
            (item.scheme, item.canonical_value)
            for item in observed.identifiers
            if item.scope is IdentifierScope.VERSION
        ]
        version_targets = self._identifier_targets(
            "version_identifiers", "paper_version_id", version_identifiers
        )
        if len(version_targets) > 1:
            raise CatalogConflict()
        version_row = (
            self._connection.execute(
                sa.text(
                    "SELECT id, paper_id FROM paper_versions "
                    "WHERE source_id = :source AND source_version_key = :version"
                ),
                {"source": str(observed.source_id), "version": observed.source_version_key},
            )
            .mappings()
            .one_or_none()
        )
        if version_row is not None:
            if paper_id is not None and version_row["paper_id"] != str(paper_id):
                raise CatalogConflict()
            paper_id = PaperId(UUID(version_row["paper_id"]))
            version_id = PaperVersionId(UUID(version_row["id"]))
            if version_targets and version_targets != {str(version_id)}:
                raise CatalogConflict()
            created_version = False
        else:
            if version_targets:
                raise CatalogConflict()
            created_version = True
            version_id = PaperVersionId(self._new_id())

        now = self._clock.now()
        if paper_id is None:
            paper_id = PaperId(self._new_id())
            created_paper = True
            self._connection.execute(
                sa.text("INSERT INTO papers (id, created_at) VALUES (:id, :created_at)"),
                {"id": str(paper_id), "created_at": _utc_text(now)},
            )
        if created_version:
            self._connection.execute(
                sa.text(
                    "UPDATE paper_versions SET is_current = 0 "
                    "WHERE paper_id = :paper AND source_id = :source AND is_current = 1"
                ),
                {"paper": str(paper_id), "source": str(observed.source_id)},
            )
            self._connection.execute(
                sa.text(
                    "INSERT INTO paper_versions "
                    "(id, paper_id, source_id, source_version_key, is_current, created_at) "
                    "VALUES (:id, :paper, :source, :version, 1, :created_at)"
                ),
                {
                    "id": str(version_id),
                    "paper": str(paper_id),
                    "source": str(observed.source_id),
                    "version": observed.source_version_key,
                    "created_at": _utc_text(now),
                },
            )

        observation_row = self._connection.execute(
            sa.text(
                "SELECT id FROM version_observations "
                "WHERE paper_version_id = :version AND normalized_sha256 = :sha"
            ),
            {"version": str(version_id), "sha": str(observed.normalized_sha256)},
        ).scalar_one_or_none()
        if observation_row is None:
            observation_id = VersionObservationId(self._new_id())
            self._connection.execute(
                sa.text(
                    "INSERT INTO version_observations "
                    "(id, paper_version_id, normalized_sha256, observed_at, origin_run_id, "
                    "origin_source_snapshot_id, origin_record_ordinal, title, title_normalized, "
                    "abstract, comment, journal_reference, language, source_url, submitted_at, "
                    "announced_at) VALUES (:id, :version, :sha, :observed_at, :run, :snapshot, "
                    ":ordinal, :title, :title_normalized, :abstract, :comment, :journal, "
                    ":language, :source_url, :submitted, :announced)"
                ),
                {
                    "id": str(observation_id),
                    "version": str(version_id),
                    "sha": str(observed.normalized_sha256),
                    "observed_at": _utc_text(now),
                    "run": str(command.run_id),
                    "snapshot": str(record.snapshot_id),
                    "ordinal": record.record_ordinal,
                    "title": observed.title,
                    "title_normalized": _title_normalized(observed.title),
                    "abstract": observed.abstract,
                    "comment": observed.comment,
                    "journal": observed.journal_reference,
                    "language": observed.language,
                    "source_url": observed.source_url,
                    "submitted": (
                        _utc_text(observed.submitted_at) if observed.submitted_at else None
                    ),
                    "announced": (
                        _utc_text(observed.announced_at) if observed.announced_at else None
                    ),
                },
            )
            self._record_observation_children(observation_id, observed, now)
            metadata_blob_id = self._ensure_blob(record.metadata_blob.blob)
            artifact_id = ArtifactId(self._new_id())
            self._connection.execute(
                sa.text(
                    "INSERT INTO artifacts "
                    "(id, paper_version_id, version_observation_id, stored_blob_id, kind, "
                    "source_url, created_at) VALUES (:id, :version, :observation, :blob, "
                    "'metadata', :source_url, :created_at)"
                ),
                {
                    "id": str(artifact_id),
                    "version": str(version_id),
                    "observation": str(observation_id),
                    "blob": str(metadata_blob_id),
                    "source_url": observed.source_url,
                    "created_at": _utc_text(now),
                },
            )
            outcome = (
                IngestionOutcome.NEW_VERSION
                if created_version
                else IngestionOutcome.METADATA_UPDATE
            )
        else:
            observation_id = VersionObservationId(UUID(observation_row))
            outcome = IngestionOutcome.UNCHANGED

        linked = selected["version_observation_id"]
        if linked is not None and linked != str(observation_id):
            raise CatalogConflict()
        if linked is None:
            self._connection.execute(
                sa.text(
                    "UPDATE snapshot_records SET version_observation_id = :observation "
                    "WHERE source_snapshot_id = :snapshot AND ordinal = :ordinal"
                ),
                {
                    "observation": str(observation_id),
                    "snapshot": str(record.snapshot_id),
                    "ordinal": record.record_ordinal,
                },
            )
        self._record_identifiers(
            paper_id,
            version_id,
            record.snapshot_id,
            record.record_ordinal,
            str(observed.source_id),
            paper_identifiers,
            version_identifiers,
            now,
        )
        self._connection.execute(
            sa.text(
                "INSERT INTO ingestion_run_items "
                "(run_id, source_snapshot_id, record_ordinal, paper_id, paper_version_id, "
                "version_observation_id, outcome, created_paper, recorded_at) "
                "VALUES (:run, :snapshot, :ordinal, :paper, :version, :observation, "
                ":outcome, :created, :recorded_at)"
            ),
            {
                "run": str(command.run_id),
                "snapshot": str(record.snapshot_id),
                "ordinal": record.record_ordinal,
                "paper": str(paper_id),
                "version": str(version_id),
                "observation": str(observation_id),
                "outcome": outcome.value,
                "created": created_paper,
                "recorded_at": _utc_text(now),
            },
        )
        self._mark_visible()
        return IngestionItemRef(
            run_id=command.run_id,
            snapshot_id=record.snapshot_id,
            record_ordinal=record.record_ordinal,
            outcome=outcome,
            paper_id=paper_id,
            paper_version_id=version_id,
            version_observation_id=observation_id,
            created_paper=created_paper,
        )

    def _identifier_targets(
        self, table: str, target: str, identifiers: list[tuple[str, str]]
    ) -> set[str]:
        if (table, target) == ("paper_identifiers", "paper_id"):
            query = (
                "SELECT paper_id FROM paper_identifiers "
                "WHERE scheme = :scheme AND canonical_value = :canonical"
            )
        elif (table, target) == ("version_identifiers", "paper_version_id"):
            query = (
                "SELECT paper_version_id FROM version_identifiers "
                "WHERE scheme = :scheme AND canonical_value = :canonical"
            )
        else:
            raise ValueError("unsupported identifier target")
        values: set[str] = set()
        for scheme, canonical in identifiers:
            row = self._connection.execute(
                sa.text(query),
                {"scheme": scheme, "canonical": canonical},
            ).scalar_one_or_none()
            if row is not None:
                values.add(row)
        return values

    def _record_observation_children(
        self,
        observation_id: VersionObservationId,
        observed: ObservedPaperVersion,
        now: datetime,
    ) -> None:
        for position, author in enumerate(observed.authors, start=1):
            author_id = AuthorId(self._new_id())
            self._connection.execute(
                sa.text("INSERT INTO authors (id, created_at) VALUES (:id, :created_at)"),
                {"id": str(author_id), "created_at": _utc_text(now)},
            )
            self._connection.execute(
                sa.text(
                    "INSERT INTO paper_authors "
                    "(version_observation_id, position, author_id, raw_name, affiliation_raw) "
                    "VALUES (:observation, :position, :author, :name, :affiliation)"
                ),
                {
                    "observation": str(observation_id),
                    "position": position,
                    "author": str(author_id),
                    "name": author.raw_name,
                    "affiliation": author.affiliation_raw,
                },
            )
        for position, category in enumerate(observed.categories, start=1):
            self._connection.execute(
                sa.text(
                    "INSERT INTO paper_version_categories "
                    "(version_observation_id, position, category, is_primary) "
                    "VALUES (:observation, :position, :category, :primary)"
                ),
                {
                    "observation": str(observation_id),
                    "position": position,
                    "category": category.value,
                    "primary": category.is_primary,
                },
            )

    def _record_identifiers(
        self,
        paper_id: PaperId,
        version_id: PaperVersionId,
        snapshot_id: SnapshotId,
        ordinal: int,
        source_id: str,
        paper_identifiers: list[tuple[str, str]],
        version_identifiers: list[tuple[str, str]],
        observed_at: datetime,
    ) -> None:
        for table, _target, target_id, _evidence, identifiers in (
            (
                "paper_identifiers",
                "paper_id",
                paper_id,
                "paper_identifier_evidence",
                paper_identifiers,
            ),
            (
                "version_identifiers",
                "paper_version_id",
                version_id,
                "version_identifier_evidence",
                version_identifiers,
            ),
        ):
            if table == "paper_identifiers":
                insert_identifier = (
                    "INSERT OR IGNORE INTO paper_identifiers "
                    "(paper_id, scheme, canonical_value) "
                    "VALUES (:target, :scheme, :canonical)"
                )
                select_identifier = (
                    "SELECT paper_id FROM paper_identifiers "
                    "WHERE scheme = :scheme AND canonical_value = :canonical"
                )
                insert_evidence = (
                    "INSERT OR IGNORE INTO paper_identifier_evidence "
                    "(scheme, canonical_value, source_id, source_snapshot_id, "
                    "record_ordinal, observed_at) VALUES (:scheme, :canonical, :source, "
                    ":snapshot, :ordinal, :observed_at)"
                )
            else:
                insert_identifier = (
                    "INSERT OR IGNORE INTO version_identifiers "
                    "(paper_version_id, scheme, canonical_value) "
                    "VALUES (:target, :scheme, :canonical)"
                )
                select_identifier = (
                    "SELECT paper_version_id FROM version_identifiers "
                    "WHERE scheme = :scheme AND canonical_value = :canonical"
                )
                insert_evidence = (
                    "INSERT OR IGNORE INTO version_identifier_evidence "
                    "(scheme, canonical_value, source_id, source_snapshot_id, "
                    "record_ordinal, observed_at) VALUES (:scheme, :canonical, :source, "
                    ":snapshot, :ordinal, :observed_at)"
                )
            for scheme, canonical in identifiers:
                self._connection.execute(
                    sa.text(insert_identifier),
                    {"target": str(target_id), "scheme": scheme, "canonical": canonical},
                )
                actual = self._connection.execute(
                    sa.text(select_identifier),
                    {"scheme": scheme, "canonical": canonical},
                ).scalar_one()
                if actual != str(target_id):
                    raise CatalogConflict()
                self._connection.execute(
                    sa.text(insert_evidence),
                    {
                        "scheme": scheme,
                        "canonical": canonical,
                        "source": source_id,
                        "snapshot": str(snapshot_id),
                        "ordinal": ordinal,
                        "observed_at": _utc_text(observed_at),
                    },
                )

    def _load_item(
        self, run_id: RunId, snapshot_id: SnapshotId, ordinal: int
    ) -> IngestionItemRef | None:
        row = (
            self._connection.execute(
                sa.text(
                    "SELECT * FROM ingestion_run_items WHERE run_id = :run "
                    "AND source_snapshot_id = :snapshot AND record_ordinal = :ordinal"
                ),
                {"run": str(run_id), "snapshot": str(snapshot_id), "ordinal": ordinal},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return IngestionItemRef(
            run_id=run_id,
            snapshot_id=snapshot_id,
            record_ordinal=ordinal,
            outcome=IngestionOutcome(row["outcome"]),
            paper_id=PaperId(UUID(row["paper_id"])) if row["paper_id"] else None,
            paper_version_id=(
                PaperVersionId(UUID(row["paper_version_id"])) if row["paper_version_id"] else None
            ),
            version_observation_id=(
                VersionObservationId(UUID(row["version_observation_id"]))
                if row["version_observation_id"]
                else None
            ),
            created_paper=bool(row["created_paper"]),
        )

    def record_failure(self, command: RecordIngestionFailure) -> IngestionItemRef:
        selected = self._selected_record(
            command.run_id, command.snapshot_id, command.record_ordinal
        )
        existing = self._load_item(command.run_id, command.snapshot_id, command.record_ordinal)
        if existing is not None:
            if existing.outcome is not IngestionOutcome.FAILED:
                raise CatalogConflict()
            error = (
                self._connection.execute(
                    sa.text(
                        "SELECT stage, code FROM collection_errors WHERE run_id = :run "
                        "AND source_snapshot_id = :snapshot AND record_ordinal = :ordinal"
                    ),
                    {
                        "run": str(command.run_id),
                        "snapshot": str(command.snapshot_id),
                        "ordinal": command.record_ordinal,
                    },
                )
                .mappings()
                .one()
            )
            if error["stage"] != command.stage.value or error["code"] != command.code.value:
                raise CatalogConflict()
            return existing
        if selected["status"] != IngestionStatus.RUNNING.value:
            raise CatalogConflict()
        self._insert_failure(command)
        self._mark_visible()
        return IngestionItemRef(
            run_id=command.run_id,
            snapshot_id=command.snapshot_id,
            record_ordinal=command.record_ordinal,
            outcome=IngestionOutcome.FAILED,
        )

    def _insert_failure(self, command: RecordIngestionFailure) -> None:
        occurred_at = _utc_text(command.occurred_at)
        self._connection.execute(
            sa.text(
                "INSERT INTO ingestion_run_items "
                "(run_id, source_snapshot_id, record_ordinal, outcome, created_paper, recorded_at) "
                "VALUES (:run, :snapshot, :ordinal, 'failed', 0, :occurred_at)"
            ),
            {
                "run": str(command.run_id),
                "snapshot": str(command.snapshot_id),
                "ordinal": command.record_ordinal,
                "occurred_at": occurred_at,
            },
        )
        self._connection.execute(
            sa.text(
                "INSERT INTO collection_errors "
                "(run_id, source_snapshot_id, record_ordinal, stage, code, message, occurred_at) "
                "VALUES (:run, :snapshot, :ordinal, :stage, :code, :message, :occurred_at)"
            ),
            {
                "run": str(command.run_id),
                "snapshot": str(command.snapshot_id),
                "ordinal": command.record_ordinal,
                "stage": command.stage.value,
                "code": command.code.value,
                "message": command.message,
                "occurred_at": occurred_at,
            },
        )

    def _summary(self, run_id: RunId) -> IngestionSummary:
        row = (
            self._connection.execute(
                sa.text(
                    "SELECT selected_records, new_papers, new_versions, metadata_updates, "
                    "unchanged_records, failed_records FROM ingestion_runs WHERE id = :run"
                ),
                {"run": str(run_id)},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise LookupError("ingestion run does not exist")
        return IngestionSummary(
            run_id=run_id,
            counters=RunCounters(**{key: int(value) for key, value in row.items()}),
        )

    def finalize_run(self, run_id: RunId) -> IngestionSummary:
        status = self._connection.execute(
            sa.text("SELECT status FROM ingestion_runs WHERE id = :run"),
            {"run": str(run_id)},
        ).scalar_one_or_none()
        if status is None:
            raise LookupError("ingestion run does not exist")
        if status != IngestionStatus.RUNNING.value:
            return self._summary(run_id)
        selected = int(
            self._connection.execute(
                sa.text("SELECT selected_records FROM ingestion_runs WHERE id = :run"),
                {"run": str(run_id)},
            ).scalar_one()
        )
        counts = {
            row[0]: int(row[1])
            for row in self._connection.execute(
                sa.text(
                    "SELECT outcome, count(*) FROM ingestion_run_items "
                    "WHERE run_id = :run GROUP BY outcome"
                ),
                {"run": str(run_id)},
            )
        }
        item_count = sum(counts.values())
        if item_count != selected:
            raise RuntimeError("ingestion run items do not match selected records")
        created_papers = int(
            self._connection.execute(
                sa.text(
                    "SELECT count(*) FROM ingestion_run_items "
                    "WHERE run_id = :run AND created_paper = 1"
                ),
                {"run": str(run_id)},
            ).scalar_one()
        )
        counters = RunCounters(
            selected_records=selected,
            new_papers=created_papers,
            new_versions=counts.get(IngestionOutcome.NEW_VERSION.value, 0),
            metadata_updates=counts.get(IngestionOutcome.METADATA_UPDATE.value, 0),
            unchanged_records=counts.get(IngestionOutcome.UNCHANGED.value, 0),
            failed_records=counts.get(IngestionOutcome.FAILED.value, 0),
        )
        self._connection.execute(
            sa.text(
                "UPDATE ingestion_runs SET status = :status, finished_at = :finished, "
                "new_papers = :new_papers, new_versions = :new_versions, "
                "metadata_updates = :metadata_updates, unchanged_records = :unchanged, "
                "failed_records = :failed WHERE id = :run"
            ),
            {
                "status": counters.status.value,
                "finished": _utc_text(self._clock.now()),
                "new_papers": counters.new_papers,
                "new_versions": counters.new_versions,
                "metadata_updates": counters.metadata_updates,
                "unchanged": counters.unchanged_records,
                "failed": counters.failed_records,
                "run": str(run_id),
            },
        )
        self._mark_visible()
        return IngestionSummary(run_id=run_id, counters=counters)

    def repair_interrupted_run(self, command: RepairInterruptedRun) -> InterruptedRunRepairResult:
        row = (
            self._connection.execute(
                sa.text("SELECT status, started_at FROM ingestion_runs WHERE id = :run"),
                {"run": str(command.run_id)},
            )
            .mappings()
            .one_or_none()
        )
        if (
            row is None
            or row["status"] != IngestionStatus.RUNNING.value
            or datetime.fromisoformat(row["started_at"]) >= command.cutoff
        ):
            return InterruptedRunRepairResult(
                run_id=command.run_id,
                outcome=InterruptedRunRepairOutcome.NOT_ELIGIBLE,
                summary=None,
                revision=self._revision_after_commit(),
            )
        missing = tuple(
            self._connection.execute(
                sa.text(
                    "SELECT selected.source_snapshot_id, selected.record_ordinal "
                    "FROM ingestion_run_selected_records AS selected "
                    "LEFT JOIN ingestion_run_items AS item ON item.run_id = selected.run_id "
                    "AND item.source_snapshot_id = selected.source_snapshot_id "
                    "AND item.record_ordinal = selected.record_ordinal "
                    "WHERE selected.run_id = :run AND item.run_id IS NULL "
                    "ORDER BY selected.selection_ordinal"
                ),
                {"run": str(command.run_id)},
            ).all()
        )
        for snapshot, ordinal in missing:
            self._insert_failure(
                RecordIngestionFailure(
                    run_id=command.run_id,
                    snapshot_id=SnapshotId(UUID(snapshot)),
                    record_ordinal=int(ordinal),
                    stage=IngestionFailureStage.RECOVERY,
                    code=ErrorCode.INTERRUPTED,
                    occurred_at=command.occurred_at,
                )
            )
        summary = self.finalize_run(command.run_id)
        return InterruptedRunRepairResult(
            run_id=command.run_id,
            outcome=InterruptedRunRepairOutcome.REPAIRED,
            summary=summary,
            revision=self._revision_after_commit(),
        )


class SqliteCollectionRepository:
    def __init__(
        self,
        connection: Connection,
        clock: Clock,
        ids: IdGenerator,
        mark_visible: Callable[[], None],
    ) -> None:
        self._connection = connection
        self._clock = clock
        self._ids = ids
        self._mark_visible = mark_visible

    def create(self, command: CreateCollection) -> CollectionView:
        collection_id = CollectionId(self._ids.new())
        now = self._clock.now()
        self._connection.execute(
            sa.text(
                "INSERT INTO collections (id, slug, title, created_at, updated_at) "
                "VALUES (:id, :slug, :title, :created_at, :updated_at)"
            ),
            {
                "id": str(collection_id),
                "slug": command.slug,
                "title": command.title,
                "created_at": _utc_text(now),
                "updated_at": _utc_text(now),
            },
        )
        self._mark_visible()
        return CollectionView(
            collection_id=collection_id,
            slug=command.slug,
            title=command.title,
            paper_count=0,
            created_at=now,
            updated_at=now,
        )

    def rename(self, command: RenameCollection) -> CollectionView:
        current = self._load(command.collection_id)
        if current.title == command.title:
            return current
        now = self._clock.now()
        self._connection.execute(
            sa.text(
                "UPDATE collections SET title = :title, updated_at = :updated_at WHERE id = :id"
            ),
            {
                "id": str(command.collection_id),
                "title": command.title,
                "updated_at": _utc_text(now),
            },
        )
        self._mark_visible()
        return CollectionView(
            collection_id=current.collection_id,
            slug=current.slug,
            title=command.title,
            paper_count=current.paper_count,
            created_at=current.created_at,
            updated_at=now,
        )

    def add(self, command: AddCollectionPaper) -> CollectionView:
        current = self._load(command.collection_id)
        paper_id = self._resolve_paper(command.selector)
        existing = self._connection.execute(
            sa.text(
                "SELECT note FROM collection_papers "
                "WHERE collection_id = :collection_id AND paper_id = :paper_id"
            ),
            {"collection_id": str(command.collection_id), "paper_id": str(paper_id)},
        ).scalar_one_or_none()
        if existing == command.note and (
            existing is not None
            or self._connection.execute(
                sa.text(
                    "SELECT 1 FROM collection_papers "
                    "WHERE collection_id = :collection_id AND paper_id = :paper_id"
                ),
                {"collection_id": str(command.collection_id), "paper_id": str(paper_id)},
            ).scalar_one_or_none()
            is not None
        ):
            return current
        now = self._clock.now()
        if existing is None:
            result = self._connection.execute(
                sa.text(
                    "INSERT OR IGNORE INTO collection_papers "
                    "(collection_id, paper_id, added_at, note) "
                    "VALUES (:collection_id, :paper_id, :added_at, :note)"
                ),
                {
                    "collection_id": str(command.collection_id),
                    "paper_id": str(paper_id),
                    "added_at": _utc_text(now),
                    "note": command.note,
                },
            )
            if result.rowcount == 0:
                self._connection.execute(
                    sa.text(
                        "UPDATE collection_papers SET note = :note "
                        "WHERE collection_id = :collection_id AND paper_id = :paper_id"
                    ),
                    {
                        "collection_id": str(command.collection_id),
                        "paper_id": str(paper_id),
                        "note": command.note,
                    },
                )
        else:
            self._connection.execute(
                sa.text(
                    "UPDATE collection_papers SET note = :note "
                    "WHERE collection_id = :collection_id AND paper_id = :paper_id"
                ),
                {
                    "collection_id": str(command.collection_id),
                    "paper_id": str(paper_id),
                    "note": command.note,
                },
            )
        self._connection.execute(
            sa.text("UPDATE collections SET updated_at = :now WHERE id = :id"),
            {"now": _utc_text(now), "id": str(command.collection_id)},
        )
        self._mark_visible()
        return self._load(command.collection_id)

    def remove(self, command: RemoveCollectionPaper) -> CollectionView:
        current = self._load(command.collection_id)
        paper_id = self._resolve_paper(command.selector)
        result = self._connection.execute(
            sa.text(
                "DELETE FROM collection_papers "
                "WHERE collection_id = :collection_id AND paper_id = :paper_id"
            ),
            {"collection_id": str(command.collection_id), "paper_id": str(paper_id)},
        )
        if result.rowcount == 0:
            return current
        now = self._clock.now()
        self._connection.execute(
            sa.text("UPDATE collections SET updated_at = :now WHERE id = :id"),
            {"now": _utc_text(now), "id": str(command.collection_id)},
        )
        self._mark_visible()
        return self._load(command.collection_id)

    def _resolve_paper(self, selector: PaperSelector) -> PaperId:
        if selector.paper_id is not None:
            requested = str(selector.paper_id)
            value: str | None = self._connection.execute(
                sa.text("SELECT id FROM papers WHERE id = :id"), {"id": requested}
            ).scalar_one_or_none()
        else:
            scheme = "arxiv" if selector.arxiv_id is not None else "doi"
            canonical = selector.arxiv_id if selector.arxiv_id is not None else selector.doi
            value = self._connection.execute(
                sa.text(
                    "SELECT paper_id FROM paper_identifiers "
                    "WHERE scheme = :scheme AND canonical_value = :canonical"
                ),
                {"scheme": scheme, "canonical": canonical},
            ).scalar_one_or_none()
        if value is None:
            raise LookupError("paper does not exist")
        return PaperId(UUID(value))

    def _load(self, collection_id: CollectionId) -> CollectionView:
        row = (
            self._connection.execute(
                sa.text(
                    "SELECT c.id, c.slug, c.title, c.created_at, c.updated_at, "
                    "count(cp.paper_id) AS paper_count "
                    "FROM collections AS c "
                    "LEFT JOIN collection_papers AS cp ON cp.collection_id = c.id "
                    "WHERE c.id = :id "
                    "GROUP BY c.id, c.slug, c.title, c.created_at, c.updated_at"
                ),
                {"id": str(collection_id)},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise LookupError("collection does not exist")
        return CollectionView(
            collection_id=CollectionId(UUID(row["id"])),
            slug=row["slug"],
            title=row["title"],
            paper_count=int(row["paper_count"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


class SqliteCatalogUnitOfWork:
    def __init__(self, engine: Engine, clock: Clock, ids: IdGenerator) -> None:
        self._engine = engine
        self._clock = clock
        self._ids = ids
        self._connection: Connection | None = None
        self._visible_mutation = False
        self._finished = False
        self.corpus: SqliteCorpusRepository
        self.ingestion: SqliteIngestionRepository
        self.collections: SqliteCollectionRepository

    def __enter__(self) -> SqliteCatalogUnitOfWork:
        if self._connection is not None:
            raise RuntimeError("catalog unit of work is already open")
        connection = self._engine.connect()
        try:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        except BaseException:
            connection.close()
            raise
        self._connection = connection
        self.corpus = SqliteCorpusRepository(connection)
        self.ingestion = SqliteIngestionRepository(
            connection,
            self._clock,
            self._ids,
            self._mark_visible,
            self._revision_after_commit,
        )
        self.collections = SqliteCollectionRepository(
            connection,
            self._clock,
            self._ids,
            self._mark_visible,
        )
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
                if not self._finished:
                    connection.rollback()
            finally:
                connection.close()
                self._connection = None
        return False

    def _mark_visible(self) -> None:
        self._require_active()
        self._visible_mutation = True

    def _require_active(self) -> Connection:
        if self._connection is None or self._finished:
            raise RuntimeError("catalog unit of work is not active")
        return self._connection

    def _revision_after_commit(self) -> int:
        connection = self._require_active()
        revision = int(
            connection.execute(
                sa.text("SELECT revision FROM catalog_meta WHERE singleton_id = 1")
            ).scalar_one()
        )
        return revision + int(self._visible_mutation)

    def commit(self) -> None:
        connection = self._require_active()
        if self._visible_mutation:
            result = connection.execute(
                sa.text("UPDATE catalog_meta SET revision = revision + 1 WHERE singleton_id = 1")
            )
            if result.rowcount != 1:
                raise RuntimeError("catalog metadata singleton is missing")
        connection.commit()
        self._finished = True

    def rollback(self) -> None:
        connection = self._require_active()
        connection.rollback()
        self._finished = True


class SqliteCatalogUnitOfWorkFactory:
    def __init__(self, *, engine: Engine, clock: Clock, ids: IdGenerator) -> None:
        self._engine = engine
        self._clock = clock
        self._ids = ids

    def begin(self) -> SqliteCatalogUnitOfWork:
        return SqliteCatalogUnitOfWork(self._engine, self._clock, self._ids)
