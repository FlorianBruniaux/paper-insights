from __future__ import annotations

from collections import deque
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from paper_insights.adapters.catalog.sqlite.readers import SqliteCatalogReader
from paper_insights.adapters.catalog.sqlite.uow import (
    CatalogConflict,
    SqliteCatalogUnitOfWorkFactory,
)
from paper_insights.domain.acquisition import (
    DiscoveryBatch,
    DiscoveryPage,
    DiscoveryQuery,
    DiscoveryRecord,
    IdentifierScope,
    ObservedAuthor,
    ObservedCategory,
    ObservedIdentifier,
    ObservedPaperVersion,
    PreparedDiscovery,
    RecordLocator,
)
from paper_insights.domain.corpus import (
    AttachPreparedRun,
    IngestionFailureStage,
    IngestionOutcome,
    IngestionStatus,
    InterruptedRunRepairOutcome,
    MetadataBlobRef,
    PreparedSnapshotAttachment,
    RecordIngestionFailure,
    RecordIngestionItem,
    RecordObservation,
    RepairInterruptedRun,
    SnapshotRecordAttachment,
    StoredBlobRef,
)
from paper_insights.domain.errors import ErrorCode
from paper_insights.domain.identifiers import PaperSelector, RunId, Sha256, SnapshotId, SourceId

NOW = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
IDS = tuple(UUID(f"01890f3c-0000-7000-8000-{value:012d}") for value in range(1, 100))


class FrozenClock:
    def now(self) -> datetime:
        return NOW


class SequenceIds:
    def __init__(self, *values: UUID) -> None:
        self._values = deque(values)

    def new(self) -> UUID:
        return self._values.popleft()


def _factory(engine: Engine) -> SqliteCatalogUnitOfWorkFactory:
    return SqliteCatalogUnitOfWorkFactory(
        engine=engine,
        clock=FrozenClock(),
        ids=SequenceIds(*IDS),
    )


def _manifest(
    *,
    run_id: UUID,
    capture_id: UUID,
    version: str = "2608.00001v1",
    normalized: str = "a" * 64,
    raw_payload: bytes = b"source-page",
    selected: bool = True,
    doi: str = "10.1000/catalog",
) -> tuple[AttachPreparedRun, ObservedPaperVersion]:
    locator = RecordLocator(
        page_ordinal=0,
        record_ordinal=0,
        source_item_id="2608.00001",
        source_version_key=version,
        raw_record_sha256=Sha256("b" * 64),
    )
    observed = ObservedPaperVersion(
        source_id=SourceId("arxiv"),
        source_item_id="2608.00001",
        source_version_key=version,
        title="A versioned paper",
        abstract="Exact abstract",
        page_ordinal=0,
        record_ordinal=0,
        normalized_sha256=Sha256(normalized),
        authors=(ObservedAuthor(raw_name="Ada Lovelace", affiliation_raw="Analytical"),),
        categories=(ObservedCategory(value="cs.AI", is_primary=True),),
        identifiers=(
            ObservedIdentifier(
                scheme="doi",
                canonical_value=doi,
                scope=IdentifierScope.PAPER,
            ),
        ),
    )
    page = DiscoveryPage(
        capture_id=capture_id,
        records=(DiscoveryRecord(locator=locator, observation=observed),),
        raw_payload=raw_payload,
        media_type="application/atom+xml",
        retrieved_at=NOW,
        request_fingerprint=Sha256("c" * 64),
        next_cursor=None,
    )
    batch = DiscoveryBatch(
        source_id=SourceId("arxiv"),
        query=DiscoveryQuery(identifiers=("2608.00001",), limit=1),
        pages=(page,),
        records=(observed,),
        issues=(),
    )
    prepared = PreparedDiscovery.prepare(
        batch=batch,
        selected_records=(locator,) if selected else (),
        prepared_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    blob = StoredBlobRef(
        sha256=page.payload_sha256,
        size_bytes=len(raw_payload),
        media_type=page.media_type,
        relative_path=Path(f"blobs/{page.payload_sha256.value[:2]}/{page.payload_sha256.value}"),
    )
    return (
        AttachPreparedRun(
            run_id=RunId(run_id),
            prepared=prepared,
            pages=(
                PreparedSnapshotAttachment(
                    page_ordinal=0,
                    capture_id=capture_id,
                    blob=blob,
                    request_fingerprint=page.request_fingerprint,
                    retrieved_at=page.retrieved_at,
                    next_cursor=None,
                    records=(SnapshotRecordAttachment(locator=locator),),
                ),
            ),
        ),
        observed,
    )


def _record(
    run: AttachPreparedRun,
    snapshot_id: UUID,
    observed: ObservedPaperVersion,
) -> RecordIngestionItem:
    digest = observed.normalized_sha256
    return RecordIngestionItem(
        run_id=run.run_id,
        record=RecordObservation(
            snapshot_id=SnapshotId(snapshot_id),
            record_ordinal=0,
            observed=observed,
            metadata_blob=MetadataBlobRef(
                blob=StoredBlobRef(
                    sha256=digest,
                    size_bytes=123,
                    media_type="application/json",
                    relative_path=Path(f"blobs/{digest.value[:2]}/{digest.value}"),
                ),
                normalized_sha256=digest,
            ),
        ),
    )


def _two_record_manifest(*, run_id: UUID, capture_id: UUID) -> AttachPreparedRun:
    command, first_observed = _manifest(run_id=run_id, capture_id=capture_id)
    first_page = command.prepared.batch.pages[0]
    second_locator = RecordLocator(
        page_ordinal=0,
        record_ordinal=1,
        source_item_id="2608.00002",
        source_version_key="2608.00002v1",
        raw_record_sha256=Sha256("f" * 64),
    )
    second_observed = replace(
        first_observed,
        source_item_id="2608.00002",
        source_version_key="2608.00002v1",
        record_ordinal=1,
        normalized_sha256=Sha256("e" * 64),
        identifiers=(
            ObservedIdentifier(
                scheme="doi",
                canonical_value="10.1000/catalog-two",
                scope=IdentifierScope.PAPER,
            ),
        ),
    )
    records = (
        first_page.records[0],
        DiscoveryRecord(locator=second_locator, observation=second_observed),
    )
    page = replace(first_page, records=records)
    batch = DiscoveryBatch(
        source_id=command.source_id,
        query=DiscoveryQuery(identifiers=("2608.00001", "2608.00002"), limit=2),
        pages=(page,),
        records=(first_observed, second_observed),
        issues=(),
    )
    prepared = PreparedDiscovery.prepare(
        batch=batch,
        selected_records=(records[0].locator, records[1].locator),
        prepared_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )
    attachment = replace(
        command.pages[0],
        records=tuple(SnapshotRecordAttachment(record.locator) for record in records),
    )
    return AttachPreparedRun(
        run_id=RunId(run_id),
        prepared=prepared,
        pages=(attachment,),
    )


def test_attach_persists_manifest_selection_and_exact_replay(engine: Engine) -> None:
    factory = _factory(engine)
    command, _ = _manifest(run_id=IDS[80], capture_id=IDS[81])

    with factory.begin() as uow:
        attached = uow.ingestion.attach_prepared_run(command)
        uow.commit()

    assert attached.run_id == command.run_id
    assert attached.revision == 1
    assert tuple(item.page_ordinal for item in attached.snapshots) == (0,)

    with factory.begin() as uow:
        replayed = uow.ingestion.attach_prepared_run(command)
        uow.commit()

    assert replayed == attached
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT revision FROM catalog_meta")).scalar_one() == 1
        snapshot_count = connection.execute(
            sa.text("SELECT count(*) FROM source_snapshots")
        ).scalar_one()
        assert snapshot_count == 1
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM ingestion_run_selected_records")
            ).scalar_one()
            == 1
        )


def test_capture_collision_compares_only_immutable_source_graph(engine: Engine) -> None:
    factory = _factory(engine)
    first, observed = _manifest(run_id=IDS[80], capture_id=IDS[81])
    with factory.begin() as uow:
        attached = uow.ingestion.attach_prepared_run(first)
        uow.commit()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE snapshot_records SET version_observation_id = NULL "
                "WHERE source_snapshot_id = :snapshot"
            ),
            {"snapshot": str(attached.snapshots[0].snapshot_id)},
        )

    same_source, _ = _manifest(run_id=IDS[82], capture_id=IDS[81])
    with factory.begin() as uow:
        reused = uow.ingestion.attach_prepared_run(same_source)
        uow.commit()
    assert reused.snapshots[0].snapshot_id == attached.snapshots[0].snapshot_id

    divergent, _ = _manifest(
        run_id=IDS[83], capture_id=IDS[81], raw_payload=b"divergent-source-page"
    )
    with pytest.raises(CatalogConflict):
        with factory.begin() as uow:
            uow.ingestion.attach_prepared_run(divergent)

    assert observed.source_item_id == "2608.00001"


def test_record_item_routes_identifiers_and_classifies_all_outcomes(engine: Engine) -> None:
    factory = _factory(engine)
    outcomes: list[IngestionOutcome] = []
    cases = (
        (IDS[80], IDS[81], "2608.00001v1", "a" * 64),
        (IDS[82], IDS[83], "2608.00001v1", "d" * 64),
        (IDS[84], IDS[85], "2608.00001v2", "e" * 64),
        (IDS[86], IDS[87], "2608.00001v2", "e" * 64),
    )
    for run_id, capture_id, version, normalized in cases:
        command, observed = _manifest(
            run_id=run_id,
            capture_id=capture_id,
            version=version,
            normalized=normalized,
        )
        with factory.begin() as uow:
            attached = uow.ingestion.attach_prepared_run(command)
            uow.commit()
        with factory.begin() as uow:
            item = uow.ingestion.record_item(
                _record(command, attached.snapshots[0].snapshot_id.value, observed)
            )
            summary = uow.ingestion.finalize_run(command.run_id)
            uow.commit()
        outcomes.append(item.outcome)
        assert summary.counters.status is IngestionStatus.SUCCEEDED

    assert outcomes == [
        IngestionOutcome.NEW_VERSION,
        IngestionOutcome.METADATA_UPDATE,
        IngestionOutcome.NEW_VERSION,
        IngestionOutcome.UNCHANGED,
    ]
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT count(*) FROM papers")).scalar_one() == 1
        assert connection.execute(sa.text("SELECT count(*) FROM paper_versions")).scalar_one() == 2
        observation_count = connection.execute(
            sa.text("SELECT count(*) FROM version_observations")
        ).scalar_one()
        assert observation_count == 3
        assert (
            connection.execute(
                sa.text("SELECT canonical_value FROM paper_identifiers WHERE scheme = 'arxiv'")
            ).scalar_one()
            == "2608.00001"
        )
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM paper_identifiers WHERE scheme = 'doi'")
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM version_identifiers WHERE scheme = 'arxiv'")
            ).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM paper_versions WHERE is_current = 1")
            ).scalar_one()
            == 1
        )
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert connection.exec_driver_sql("PRAGMA quick_check").scalar_one() == "ok"

    reader = SqliteCatalogReader(engine)
    with reader.snapshot() as snapshot:
        paper = snapshot.get_paper(PaperSelector.by_arxiv("2608.00001"))
    assert paper is not None
    assert tuple(item.observed.page_ordinal for item in paper.observations) == (0, 0, 0)


def test_reader_scopes_identifiers_to_each_observation_provenance(engine: Engine) -> None:
    factory = _factory(engine)
    cases = (
        (IDS[80], IDS[81], "a" * 64, "10.1000/first"),
        (IDS[82], IDS[83], "d" * 64, "10.1000/second"),
    )
    for run_id, capture_id, normalized, doi in cases:
        command, observed = _manifest(
            run_id=run_id,
            capture_id=capture_id,
            normalized=normalized,
            doi=doi,
        )
        with factory.begin() as uow:
            attached = uow.ingestion.attach_prepared_run(command)
            uow.commit()
        with factory.begin() as uow:
            uow.ingestion.record_item(
                _record(command, attached.snapshots[0].snapshot_id.value, observed)
            )
            uow.ingestion.finalize_run(command.run_id)
            uow.commit()

    reader = SqliteCatalogReader(engine)
    with reader.snapshot() as snapshot:
        paper = snapshot.get_paper(PaperSelector.by_arxiv("2608.00001"))

    assert paper is not None
    assert tuple(
        tuple((item.scheme, item.canonical_value) for item in observation.observed.identifiers)
        for observation in paper.observations
    ) == (
        (("doi", "10.1000/first"),),
        (("doi", "10.1000/second"),),
    )


def test_failure_retry_and_repair_are_idempotent_revisioned_transactions(
    engine: Engine,
) -> None:
    factory = _factory(engine)
    command, _ = _manifest(run_id=IDS[80], capture_id=IDS[81])
    with factory.begin() as uow:
        attached = uow.ingestion.attach_prepared_run(command)
        uow.commit()
    snapshot_id = attached.snapshots[0].snapshot_id
    failure = RecordIngestionFailure(
        run_id=command.run_id,
        snapshot_id=snapshot_id,
        record_ordinal=0,
        stage=IngestionFailureStage.CATALOG_WRITE,
        code=ErrorCode.RECORD_INVALID,
        occurred_at=NOW + timedelta(minutes=1),
    )
    with factory.begin() as uow:
        failed = uow.ingestion.record_failure(failure)
        uow.commit()
    assert failed.outcome is IngestionOutcome.FAILED

    with factory.begin() as uow:
        assert uow.ingestion.record_failure(failure) == failed
        uow.commit()

    with pytest.raises(CatalogConflict):
        with factory.begin() as uow:
            uow.ingestion.record_failure(
                RecordIngestionFailure(
                    run_id=command.run_id,
                    snapshot_id=snapshot_id,
                    record_ordinal=0,
                    stage=IngestionFailureStage.CATALOG_WRITE,
                    code=ErrorCode.ARTIFACT_INVALID,
                    occurred_at=NOW + timedelta(minutes=2),
                )
            )

    with factory.begin() as uow:
        summary = uow.ingestion.finalize_run(command.run_id)
        uow.commit()
    assert summary.counters.status is IngestionStatus.FAILED

    repair_command, _ = _manifest(run_id=IDS[82], capture_id=IDS[83], selected=False)
    with factory.begin() as uow:
        uow.ingestion.attach_prepared_run(repair_command)
        uow.commit()
    cutoff = NOW + timedelta(minutes=5)
    reader = SqliteCatalogReader(engine)
    with reader.snapshot() as snapshot:
        candidates = snapshot.list_interrupted_runs(cutoff)
    assert tuple(item.run_id for item in candidates) == (repair_command.run_id,)

    repair = RepairInterruptedRun(
        run_id=repair_command.run_id,
        cutoff=cutoff,
        occurred_at=cutoff,
    )
    with factory.begin() as uow:
        result = uow.ingestion.repair_interrupted_run(repair)
        uow.commit()
    assert result.outcome is InterruptedRunRepairOutcome.REPAIRED
    assert result.summary is not None
    assert result.summary.counters.status is IngestionStatus.SUCCEEDED
    revision = result.revision

    with factory.begin() as uow:
        no_op = uow.ingestion.repair_interrupted_run(repair)
        uow.commit()
    assert no_op.outcome is InterruptedRunRepairOutcome.NOT_ELIGIBLE
    assert no_op.revision == revision


def test_repair_records_all_missing_items_and_increments_once(engine: Engine) -> None:
    factory = _factory(engine)
    command = _two_record_manifest(run_id=IDS[80], capture_id=IDS[81])
    with factory.begin() as uow:
        uow.ingestion.attach_prepared_run(command)
        uow.commit()

    cutoff = NOW + timedelta(minutes=5)
    repair = RepairInterruptedRun(
        run_id=command.run_id,
        cutoff=cutoff,
        occurred_at=cutoff,
    )
    with factory.begin() as uow:
        result = uow.ingestion.repair_interrupted_run(repair)
        uow.commit()

    assert result.outcome is InterruptedRunRepairOutcome.REPAIRED
    assert result.summary is not None
    assert result.summary.counters.failed_records == 2
    assert result.summary.counters.status is IngestionStatus.FAILED
    assert result.revision == 2
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM ingestion_run_items WHERE run_id = :run"),
                {"run": str(command.run_id)},
            ).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM collection_errors WHERE run_id = :run"),
                {"run": str(command.run_id)},
            ).scalar_one()
            == 2
        )
        assert connection.execute(sa.text("SELECT revision FROM catalog_meta")).scalar_one() == 2
