from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from paper_insights.adapters.catalog.sqlite.engine import create_catalog_engine
from paper_insights.adapters.catalog.sqlite.readers import (
    CatalogRevisionMismatch,
    SqliteCatalogReader,
    SqliteCatalogRevisionGuard,
)
from paper_insights.adapters.catalog.sqlite.uow import SqliteCatalogUnitOfWorkFactory
from paper_insights.domain.corpus import CitationSelector, CreateCollection
from paper_insights.domain.identifiers import PaperId, PaperSelector, PaperVersionId
from paper_insights.domain.retrieval import CatalogRevision

NOW = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
IDS = tuple(UUID(f"01890f3b-0000-7000-8000-{value:012d}") for value in range(1, 10))


class FrozenClock:
    def now(self) -> datetime:
        return NOW


class SequenceIds:
    def __init__(self, *values: UUID) -> None:
        self._values = deque(values)

    def new(self) -> UUID:
        return self._values.popleft()


def _factory(engine: Engine, *ids: UUID) -> SqliteCatalogUnitOfWorkFactory:
    return SqliteCatalogUnitOfWorkFactory(
        engine=engine,
        clock=FrozenClock(),
        ids=SequenceIds(*ids),
    )


def test_snapshot_is_coherent_materialized_and_read_only(engine: Engine) -> None:
    factory = _factory(engine, *IDS[:2])
    with factory.begin() as uow:
        uow.collections.create(CreateCollection(slug="first", title="First"))
        uow.commit()

    reader = SqliteCatalogReader(engine)
    with reader.snapshot() as snapshot:
        before = snapshot.list_collections()
        with factory.begin() as uow:
            uow.collections.create(CreateCollection(slug="second", title="Second"))
            uow.commit()

        assert isinstance(before, tuple)
        assert snapshot.revision == CatalogRevision(1)
        assert snapshot.list_collections() == before
        with pytest.raises(OperationalError, match="readonly"):
            snapshot._connection.execute(sa.text("DELETE FROM collections"))

    with reader.snapshot() as refreshed:
        assert refreshed.revision == CatalogRevision(2)
        assert tuple(item.slug for item in refreshed.list_collections()) == ("first", "second")

    with pytest.raises(RuntimeError, match="closed"):
        snapshot.list_collections()


def test_revision_guard_holds_a_writer_lock_and_rejects_stale_revision(
    engine: Engine,
) -> None:
    guard = SqliteCatalogRevisionGuard(engine)
    factory = _factory(engine, IDS[2])

    with guard.hold_if_current(CatalogRevision(0)) as lease:
        assert lease.revision == CatalogRevision(0)
        with pytest.raises(OperationalError, match="database is locked"):
            with factory.begin():
                pass

    with factory.begin() as uow:
        uow.collections.create(CreateCollection(slug="after-lease", title="After lease"))
        uow.commit()

    with pytest.raises(CatalogRevisionMismatch):
        with guard.hold_if_current(CatalogRevision(0)):
            pass


def test_snapshot_reconstructs_versioned_paper_index_and_citation(engine: Engine) -> None:
    paper_id = PaperId(IDS[3])
    version_id = IDS[4]
    observation_id = IDS[5]
    blob_id = IDS[6]
    artifact_id = IDS[7]
    snapshot_id = IDS[8]
    normalized = "a" * 64
    raw = "b" * 64
    now = NOW.isoformat()
    with engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO papers (id, created_at) VALUES (:id, :now)"),
            {"id": str(paper_id), "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO paper_versions "
                "(id, paper_id, source_id, source_version_key, is_current, created_at) "
                "VALUES (:id, :paper_id, 'arxiv', '2608.00001v1', 1, :now)"
            ),
            {"id": str(version_id), "paper_id": str(paper_id), "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO stored_blobs "
                "(id, sha256, size_bytes, media_type, relative_path, created_at) "
                "VALUES (:id, :sha, 10, 'application/json', 'blobs/aa/test', :now)"
            ),
            {"id": str(blob_id), "sha": normalized, "now": now},
        )
        run_id = UUID("01890f3b-0000-7000-8000-000000000098")
        connection.execute(
            sa.text(
                "INSERT INTO source_snapshots "
                "(id, capture_id, source_id, stored_blob_id, request_fingerprint, retrieved_at) "
                "VALUES (:id, :capture, 'arxiv', :blob_id, :request, :now)"
            ),
            {
                "id": str(snapshot_id),
                "capture": str(UUID("01890f3b-0000-7000-8000-000000000099")),
                "blob_id": str(blob_id),
                "request": "d" * 64,
                "now": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO snapshot_records "
                "(source_snapshot_id, ordinal, source_item_id, source_version_key, "
                "raw_record_sha256) VALUES (:snapshot_id, 0, '2608.00001', "
                "'2608.00001v1', :raw)"
            ),
            {"snapshot_id": str(snapshot_id), "raw": raw},
        )
        connection.execute(
            sa.text(
                "INSERT INTO ingestion_runs "
                "(id, source_id, prepared_digest, query_json, status, started_at, "
                "selected_records, new_papers, new_versions, metadata_updates, "
                "unchanged_records, failed_records) VALUES (:run, 'arxiv', :digest, "
                "'{\"schema_version\":\"discovery-query-v1\"}', 'running', :now, "
                "1, 0, 0, 0, 0, 0)"
            ),
            {"run": str(run_id), "digest": "c" * 64, "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO ingestion_run_snapshots "
                "(run_id, page_ordinal, source_snapshot_id, source_id) "
                "VALUES (:run, 0, :snapshot, 'arxiv')"
            ),
            {"run": str(run_id), "snapshot": str(snapshot_id)},
        )
        connection.execute(
            sa.text(
                "INSERT INTO ingestion_run_selected_records "
                "(run_id, selection_ordinal, source_snapshot_id, record_ordinal) "
                "VALUES (:run, 0, :snapshot, 0)"
            ),
            {"run": str(run_id), "snapshot": str(snapshot_id)},
        )
        connection.execute(
            sa.text(
                "INSERT INTO version_observations "
                "(id, paper_version_id, normalized_sha256, observed_at, origin_source_id, "
                "origin_run_id, "
                "origin_source_snapshot_id, origin_record_ordinal, title, title_normalized, "
                "abstract, source_url) VALUES (:id, :version_id, :sha, :now, 'arxiv', :run, "
                ":snapshot, 0, 'Exact title', 'exact title', 'Exact abstract', "
                "'https://arxiv.org/abs/2608.00001')"
            ),
            {
                "id": str(observation_id),
                "version_id": str(version_id),
                "sha": normalized,
                "now": now,
                "run": str(run_id),
                "snapshot": str(snapshot_id),
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO artifacts "
                "(id, paper_version_id, version_observation_id, stored_blob_id, kind, "
                "source_url, created_at) "
                "VALUES (:id, :version_id, :observation_id, :blob_id, 'metadata', "
                "'https://arxiv.org/abs/2608.00001', :now)"
            ),
            {
                "id": str(artifact_id),
                "version_id": str(version_id),
                "observation_id": str(observation_id),
                "blob_id": str(blob_id),
                "now": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO paper_identifiers (paper_id, scheme, canonical_value) "
                "VALUES (:paper_id, 'arxiv', '2608.00001')"
            ),
            {"paper_id": str(paper_id)},
        )
        connection.execute(
            sa.text(
                "UPDATE snapshot_records SET version_observation_id = :observation_id "
                "WHERE source_snapshot_id = :snapshot_id AND ordinal = 0"
            ),
            {
                "snapshot_id": str(snapshot_id),
                "observation_id": str(observation_id),
            },
        )

    reader = SqliteCatalogReader(engine)
    with reader.snapshot() as snapshot:
        paper = snapshot.get_paper(PaperSelector.by_arxiv("2608.00001"))
        documents = snapshot.list_index_documents()
        citation = snapshot.get_citation_input(
            CitationSelector(paper=PaperSelector(paper_id=paper_id))
        )

    assert paper is not None
    assert paper.identity.paper_id == paper_id
    assert paper.observations[0].observed.title == "Exact title"
    assert paper.artifacts[0].sha256.value == normalized
    assert len(documents) == 1
    assert documents[0].version_observation_id.value == observation_id
    assert citation is not None
    assert citation.snapshot_id.value == snapshot_id
    assert citation.source_item_id == "2608.00001"

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO sources (id, base_url, enabled) "
                "VALUES ('crossref', 'https://api.crossref.org', 1)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO paper_versions "
                "(id, paper_id, source_id, source_version_key, is_current, created_at) "
                "VALUES (:id, :paper, 'crossref', '10.1000/catalog', 1, :now)"
            ),
            {"id": str(IDS[0]), "paper": str(paper_id), "now": now},
        )

    with reader.snapshot() as ambiguous_snapshot:
        ambiguous = ambiguous_snapshot.get_citation_input(
            CitationSelector(paper=PaperSelector(paper_id=paper_id))
        )
        explicit = ambiguous_snapshot.get_citation_input(
            CitationSelector(
                paper=PaperSelector(paper_id=paper_id),
                paper_version_id=PaperVersionId(version_id),
            )
        )

    assert ambiguous is None
    assert explicit is not None
    assert explicit.observation.paper_version_id == PaperVersionId(version_id)


def test_snapshot_rejects_current_version_without_metadata_artifact(engine: Engine) -> None:
    paper_id = IDS[3]
    version_id = IDS[4]
    with engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO papers (id, created_at) VALUES (:id, :now)"),
            {"id": str(paper_id), "now": NOW.isoformat()},
        )
        connection.execute(
            sa.text(
                "INSERT INTO paper_versions "
                "(id, paper_id, source_id, source_version_key, is_current, created_at) "
                "VALUES (:id, :paper_id, 'arxiv', '2608.00003v1', 1, :now)"
            ),
            {"id": str(version_id), "paper_id": str(paper_id), "now": NOW.isoformat()},
        )

    reader = SqliteCatalogReader(engine)
    with reader.snapshot() as snapshot:
        with pytest.raises(RuntimeError, match="metadata artifact"):
            snapshot.list_index_documents()


def test_snapshot_missing_database_is_not_created(tmp_path: Path) -> None:
    database_path = tmp_path / "missing.sqlite3"
    engine = create_catalog_engine(database_path)
    reader = SqliteCatalogReader(engine)

    try:
        with pytest.raises(OperationalError):
            with reader.snapshot():
                pass
    finally:
        engine.dispose()

    assert not database_path.exists()
