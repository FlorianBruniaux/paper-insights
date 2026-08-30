from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from uuid import UUID

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from paper_insights.adapters.artifacts.filesystem.store import FilesystemBlobStore
from paper_insights.adapters.catalog.sqlite.engine import create_catalog_engine
from paper_insights.adapters.catalog.sqlite.readers import SqliteCatalogReader
from paper_insights.adapters.catalog.sqlite.uow import SqliteCatalogUnitOfWorkFactory
from paper_insights.adapters.providers.arxiv.normalizer import normalized_metadata_payload
from paper_insights.adapters.providers.arxiv.parser import parse_arxiv_feed
from paper_insights.application.ingestion.execute import ExecutePreparedIngestion
from paper_insights.application.ingestion.repair import (
    RepairConfirmationRequired,
    RepairInterruptedRuns,
)
from paper_insights.domain.acquisition import (
    DiscoveryBatch,
    DiscoveryPage,
    DiscoveryQuery,
    PreparedDiscovery,
)
from paper_insights.domain.corpus import (
    IngestionSummary,
    InterruptedRunCandidate,
    InterruptedRunRepairOutcome,
    InterruptedRunRepairResult,
    RunCounters,
)
from paper_insights.domain.identifiers import RunId, Sha256, SourceId
from paper_insights.domain.retrieval import CatalogRevision
from paper_insights.paths import CorpusPaths

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "arxiv"
NOW = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)
RUNS = (
    RunId(UUID("01890f3c-0000-7000-8000-000000000001")),
    RunId(UUID("01890f3c-0000-7000-8000-000000000002")),
)


class FrozenClock:
    def now(self) -> datetime:
        return NOW


class RepairClock:
    def now(self) -> datetime:
        return NOW + timedelta(minutes=30)


class SequenceIds:
    def __init__(self) -> None:
        self._values = deque(
            UUID(f"01890f3c-0000-7000-8000-{value:012x}") for value in range(10, 300)
        )

    def new(self) -> UUID:
        return self._values.popleft()


def _prepared() -> PreparedDiscovery:
    payload = (FIXTURES / "page-1.xml").read_bytes()
    parsed = parse_arxiv_feed(payload, page_ordinal=0)
    query = DiscoveryQuery(text="paper agents", limit=2)
    page = DiscoveryPage(
        capture_id=UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a"),
        records=parsed.records,
        raw_payload=payload,
        media_type="application/atom+xml",
        retrieved_at=NOW,
        request_fingerprint=Sha256("f" * 64),
        next_cursor=None,
    )
    batch = DiscoveryBatch(
        source_id=SourceId("arxiv"),
        query=query,
        pages=(page,),
        records=tuple(
            record.observation for record in parsed.records if record.observation is not None
        ),
        issues=parsed.issues,
    )
    return PreparedDiscovery.prepare(
        batch=batch,
        selected_records=tuple(record.locator for record in parsed.records),
        prepared_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )


def _migrate(database: Path) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")


class CrashRepository:
    def __init__(self, inner: object) -> None:
        self._inner = inner

    def record_item(self, command: object) -> object:
        del command
        raise RuntimeError("injected interruption")

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


class CrashUnit:
    def __init__(self, inner: object, *, crash_item: bool) -> None:
        self._inner = inner
        self._crash_item = crash_item

    def __enter__(self) -> CrashUnit:
        active = self._inner.__enter__()
        self.ingestion = CrashRepository(active.ingestion) if self._crash_item else active.ingestion
        self.corpus = active.corpus
        self.collections = active.collections
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        return self._inner.__exit__(exc_type, exc, traceback)

    def commit(self) -> None:
        self._inner.commit()

    def rollback(self) -> None:
        self._inner.rollback()


class CrashFirstItemCatalog:
    def __init__(self, inner: object) -> None:
        self._inner = inner
        self._begins = 0

    def begin(self) -> CrashUnit:
        self._begins += 1
        return CrashUnit(self._inner.begin(), crash_item=self._begins == 2)


class Snapshot:
    revision = CatalogRevision(7)

    def __init__(self, candidates: tuple[InterruptedRunCandidate, ...]) -> None:
        self._candidates = candidates
        self.cutoffs: list[datetime] = []

    def __enter__(self) -> Snapshot:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc_type, exc, traceback
        return False

    def list_interrupted_runs(self, cutoff: datetime) -> tuple[InterruptedRunCandidate, ...]:
        self.cutoffs.append(cutoff)
        return self._candidates


class Reader:
    def __init__(self, snapshot: Snapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> Snapshot:
        return self._snapshot


class RepairRepository:
    def __init__(self) -> None:
        self.commands: list[object] = []

    def repair_interrupted_run(self, command: object) -> InterruptedRunRepairResult:
        self.commands.append(command)
        if command.run_id == RUNS[1]:
            return InterruptedRunRepairResult(
                run_id=command.run_id,
                outcome=InterruptedRunRepairOutcome.NOT_ELIGIBLE,
                summary=None,
                revision=9,
            )
        summary = IngestionSummary(
            run_id=command.run_id,
            counters=RunCounters(selected_records=1, failed_records=1),
        )
        return InterruptedRunRepairResult(
            run_id=command.run_id,
            outcome=InterruptedRunRepairOutcome.REPAIRED,
            summary=summary,
            revision=8,
        )


class Unit:
    def __init__(self, repository: RepairRepository) -> None:
        self.ingestion = repository
        self.corpus = None
        self.collections = None
        self.committed = False

    def __enter__(self) -> Unit:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc_type, exc, traceback
        return False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        raise AssertionError("repair service unexpectedly rolled back")


class Catalog:
    def __init__(self) -> None:
        self.repository = RepairRepository()
        self.units: list[Unit] = []

    def begin(self) -> Unit:
        unit = Unit(self.repository)
        self.units.append(unit)
        return unit


def _candidates() -> tuple[InterruptedRunCandidate, ...]:
    return tuple(
        InterruptedRunCandidate(
            run_id=run_id,
            started_at=NOW - timedelta(hours=1),
            selected_records=1,
            recorded_items=0,
        )
        for run_id in RUNS
    )


def test_preview_is_read_only_and_unconfirmed_execution_does_not_open_a_writer() -> None:
    snapshot = Snapshot(_candidates())
    catalog = Catalog()
    service = RepairInterruptedRuns(
        reader=Reader(snapshot),
        catalog=catalog,
        clock=FrozenClock(),
        stale_after=timedelta(minutes=15),
    )

    preview = service.preview()

    assert preview.cutoff == NOW - timedelta(minutes=15)
    assert preview.candidates == _candidates()
    assert snapshot.cutoffs == [preview.cutoff]
    assert catalog.units == []
    with pytest.raises(RepairConfirmationRequired):
        service.execute(preview, confirmed=False)
    assert catalog.units == []


def test_confirmed_repair_reuses_one_cutoff_and_accepts_locked_no_ops() -> None:
    snapshot = Snapshot(_candidates())
    catalog = Catalog()
    service = RepairInterruptedRuns(
        reader=Reader(snapshot),
        catalog=catalog,
        clock=FrozenClock(),
        stale_after=timedelta(minutes=15),
    )
    preview = service.preview()

    results = service.execute(preview, confirmed=True)

    assert tuple(result.outcome for result in results) == (
        InterruptedRunRepairOutcome.REPAIRED,
        InterruptedRunRepairOutcome.NOT_ELIGIBLE,
    )
    assert tuple(command.cutoff for command in catalog.repository.commands) == (
        preview.cutoff,
        preview.cutoff,
    )
    assert tuple(command.occurred_at for command in catalog.repository.commands) == (NOW, NOW)
    assert all(unit.committed for unit in catalog.units)


def test_unexpected_item_interruption_is_repaired_from_persisted_selection(
    tmp_path: Path,
) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    paths.data_root.mkdir(parents=True)
    _migrate(paths.catalog)
    engine = create_catalog_engine(paths.catalog, busy_timeout_ms=100)
    ids = SequenceIds()
    factory = SqliteCatalogUnitOfWorkFactory(engine=engine, clock=FrozenClock(), ids=ids)
    prepared = _prepared()
    execute = ExecutePreparedIngestion(
        blobs=FilesystemBlobStore(paths),
        catalog=CrashFirstItemCatalog(factory),
        clock=FrozenClock(),
        ids=ids,
        metadata_payload=normalized_metadata_payload,
    )

    with pytest.raises(RuntimeError, match="injected interruption"):
        execute.execute(prepared, confirmation=prepared.digest)

    with engine.connect() as connection:
        run = connection.execute(
            sa.text("SELECT id, status, selected_records FROM ingestion_runs")
        ).one()
        assert (run.status, run.selected_records) == ("running", 2)
        assert (
            connection.execute(sa.text("SELECT count(*) FROM ingestion_run_items")).scalar_one()
            == 0
        )

    repair = RepairInterruptedRuns(
        reader=SqliteCatalogReader(engine),
        catalog=factory,
        clock=RepairClock(),
        stale_after=timedelta(minutes=15),
    )
    preview = repair.preview()
    results = repair.execute(preview, confirmed=True)

    assert tuple(candidate.run_id for candidate in preview.candidates) == (RunId(UUID(run.id)),)
    assert len(results) == 1
    assert results[0].summary is not None
    assert results[0].summary.counters.failed_records == 2
    with engine.connect() as connection:
        assert (
            connection.execute(sa.text("SELECT status FROM ingestion_runs")).scalar_one()
            == "failed"
        )
        assert (
            connection.execute(sa.text("SELECT count(*) FROM ingestion_run_items")).scalar_one()
            == 2
        )
        assert (
            connection.execute(sa.text("SELECT count(*) FROM collection_errors")).scalar_one() == 2
        )
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    engine.dispose()
