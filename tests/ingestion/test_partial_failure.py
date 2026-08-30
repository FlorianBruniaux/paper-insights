from __future__ import annotations

import hashlib
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
from paper_insights.adapters.catalog.sqlite.uow import SqliteCatalogUnitOfWorkFactory
from paper_insights.adapters.providers.arxiv.normalizer import normalized_metadata_payload
from paper_insights.adapters.providers.arxiv.parser import parse_arxiv_feed
from paper_insights.application.ingestion.execute import (
    ExecutePreparedIngestion,
    IngestionExecutionError,
)
from paper_insights.domain.acquisition import (
    DiscoveryBatch,
    DiscoveryPage,
    DiscoveryQuery,
    PreparedDiscovery,
)
from paper_insights.domain.corpus import (
    AttachedSnapshotRef,
    BlobInspection,
    IngestionItemRef,
    IngestionOutcome,
    IngestionRunRef,
    IngestionStatus,
    IngestionSummary,
    RunCounters,
    StoredBlobRef,
)
from paper_insights.domain.errors import ErrorCode
from paper_insights.domain.identifiers import Sha256, SnapshotId, SourceId
from paper_insights.paths import CorpusPaths

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "arxiv"
NOW = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)


class FrozenClock:
    def now(self) -> datetime:
        return NOW


class SequenceIds:
    def __init__(self) -> None:
        self._values = deque(
            UUID(f"01890f3c-0000-7000-8000-{value:012x}") for value in range(1, 200)
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


class MemoryBlobs:
    def __init__(self, *, fail_at: int | None = None) -> None:
        self.refs: list[StoredBlobRef] = []
        self._fail_at = fail_at

    def put(self, blob: object) -> StoredBlobRef:
        if self._fail_at == len(self.refs):
            raise OSError("injected blob publication failure")
        content = blob.content
        digest = Sha256(hashlib.sha256(content).hexdigest())
        ref = StoredBlobRef(
            sha256=digest,
            size_bytes=len(content),
            media_type=blob.media_type,
            relative_path=Path(f"blobs/{digest.value}.blob"),
        )
        self.refs.append(ref)
        return ref

    def open_verified(self, ref: StoredBlobRef) -> object:
        raise NotImplementedError(ref)

    def inspect(self, ref: StoredBlobRef) -> BlobInspection:
        raise NotImplementedError(ref)


class PartialRepository:
    def __init__(self) -> None:
        self.run_id = None
        self.items: list[IngestionItemRef] = []
        self.failures: list[object] = []

    def attach_prepared_run(self, command: object) -> IngestionRunRef:
        self.run_id = command.run_id
        return IngestionRunRef(
            run_id=command.run_id,
            revision=1,
            snapshots=(
                AttachedSnapshotRef(
                    page_ordinal=0,
                    snapshot_id=SnapshotId(SequenceIds().new()),
                ),
            ),
        )

    def record_item(self, command: object) -> IngestionItemRef:
        if command.record.record_ordinal == 1:
            raise ValueError("invalid second record")
        item = IngestionItemRef(
            run_id=command.run_id,
            snapshot_id=command.record.snapshot_id,
            record_ordinal=0,
            outcome=IngestionOutcome.NEW_VERSION,
            paper_id=command.run_id,
            paper_version_id=command.run_id,
            version_observation_id=command.run_id,
            created_paper=True,
        )
        self.items.append(item)
        return item

    def record_failure(self, command: object) -> IngestionItemRef:
        self.failures.append(command)
        item = IngestionItemRef(
            run_id=command.run_id,
            snapshot_id=command.snapshot_id,
            record_ordinal=command.record_ordinal,
            outcome=IngestionOutcome.FAILED,
        )
        self.items.append(item)
        return item

    def finalize_run(self, run_id: object) -> IngestionSummary:
        assert run_id == self.run_id
        return IngestionSummary(
            run_id=run_id,
            counters=RunCounters(
                selected_records=2,
                new_papers=1,
                new_versions=1,
                failed_records=1,
            ),
        )


class Unit:
    def __init__(self, repository: PartialRepository, *, fail_commit: bool = False) -> None:
        self.ingestion = repository
        self.corpus = None
        self.collections = None
        self._fail_commit = fail_commit
        self.rolled_back = False

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
        if self._fail_commit:
            raise OSError("injected snapshot commit failure")

    def rollback(self) -> None:
        self.rolled_back = True


class Catalog:
    def __init__(self, *, fail_first_commit: bool = False) -> None:
        self.repository = PartialRepository()
        self.begins = 0
        self._fail_first_commit = fail_first_commit

    def begin(self) -> Unit:
        self.begins += 1
        return Unit(
            self.repository,
            fail_commit=self._fail_first_commit and self.begins == 1,
        )


class FailFirstCommitUnit:
    def __init__(self, inner: object) -> None:
        self._inner = inner

    def __enter__(self) -> FailFirstCommitUnit:
        active = self._inner.__enter__()
        self.ingestion = active.ingestion
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
        raise OSError("injected snapshot commit failure")

    def rollback(self) -> None:
        self._inner.rollback()


class FailFirstCommitCatalog:
    def __init__(self, inner: object) -> None:
        self._inner = inner
        self._failed = False

    def begin(self) -> object:
        unit = self._inner.begin()
        if self._failed:
            return unit
        self._failed = True
        return FailFirstCommitUnit(unit)


def _service(blobs: MemoryBlobs, catalog: Catalog) -> ExecutePreparedIngestion:
    return ExecutePreparedIngestion(
        blobs=blobs,
        catalog=catalog,
        clock=FrozenClock(),
        ids=SequenceIds(),
        metadata_payload=normalized_metadata_payload,
    )


def test_item_rollback_is_followed_by_a_closed_failure_and_partial_summary() -> None:
    blobs = MemoryBlobs()
    catalog = Catalog()
    prepared = _prepared()

    summary = _service(blobs, catalog).execute(prepared, confirmation=prepared.digest)

    assert summary.counters.status is IngestionStatus.PARTIAL
    assert summary.counters.new_versions == 1
    assert summary.counters.failed_records == 1
    assert len(catalog.repository.failures) == 1
    failure = catalog.repository.failures[0]
    assert failure.stage.value == "catalog_write"
    assert failure.code is ErrorCode.RECORD_INVALID
    assert failure.record_ordinal == 1


@pytest.mark.parametrize(
    ("confirmation", "clock", "code"),
    (
        (Sha256("0" * 64), FrozenClock(), ErrorCode.PREVIEW_MISMATCH),
        (
            None,
            type(
                "ExpiredClock",
                (),
                {"now": lambda self: _prepared().expires_at},
            )(),
            ErrorCode.PREVIEW_EXPIRED,
        ),
    ),
)
def test_invalid_confirmation_precedes_every_blob_or_catalog_mutation(
    confirmation: Sha256 | None, clock: object, code: ErrorCode
) -> None:
    blobs = MemoryBlobs()
    catalog = Catalog()
    prepared = _prepared()
    service = ExecutePreparedIngestion(
        blobs=blobs,
        catalog=catalog,
        clock=clock,
        ids=SequenceIds(),
        metadata_payload=normalized_metadata_payload,
    )

    with pytest.raises(IngestionExecutionError) as raised:
        service.execute(prepared, confirmation=confirmation or prepared.digest)

    assert raised.value.code is code
    assert blobs.refs == []
    assert catalog.begins == 0


def test_invalid_canonical_metadata_precedes_every_blob_or_catalog_mutation() -> None:
    blobs = MemoryBlobs()
    catalog = Catalog()
    prepared = _prepared()
    service = ExecutePreparedIngestion(
        blobs=blobs,
        catalog=catalog,
        clock=FrozenClock(),
        ids=SequenceIds(),
        metadata_payload=lambda _observation: b"not the canonical metadata",
    )

    with pytest.raises(IngestionExecutionError) as raised:
        service.execute(prepared, confirmation=prepared.digest)

    assert raised.value.code is ErrorCode.ARTIFACT_INVALID
    assert blobs.refs == []
    assert catalog.begins == 0


def test_blob_failure_never_opens_the_snapshot_transaction() -> None:
    blobs = MemoryBlobs(fail_at=0)
    catalog = Catalog()
    prepared = _prepared()

    with pytest.raises(OSError, match="blob publication"):
        _service(blobs, catalog).execute(prepared, confirmation=prepared.digest)

    assert catalog.begins == 0


def test_crash_before_blob_replace_leaves_no_final_blob_or_catalog_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    paths.data_root.mkdir(parents=True)
    _migrate(paths.catalog)
    engine = create_catalog_engine(paths.catalog, busy_timeout_ms=100)
    ids = SequenceIds()
    store = FilesystemBlobStore(paths)

    def fail_before_replace(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected before replace")

    monkeypatch.setattr(store, "_publish_at", fail_before_replace)
    service = ExecutePreparedIngestion(
        blobs=store,
        catalog=SqliteCatalogUnitOfWorkFactory(engine=engine, clock=FrozenClock(), ids=ids),
        clock=FrozenClock(),
        ids=ids,
        metadata_payload=normalized_metadata_payload,
    )
    prepared = _prepared()

    with pytest.raises(OSError, match="unsafe blob path"):
        service.execute(prepared, confirmation=prepared.digest)

    assert tuple(paths.blobs.rglob("*.blob")) == ()
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT count(*) FROM ingestion_runs")).scalar_one() == 0
        assert (
            connection.execute(sa.text("SELECT count(*) FROM source_snapshots")).scalar_one() == 0
        )
    engine.dispose()


def test_snapshot_commit_failure_leaves_only_published_orphan_blobs(tmp_path: Path) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    paths.data_root.mkdir(parents=True)
    _migrate(paths.catalog)
    engine = create_catalog_engine(paths.catalog, busy_timeout_ms=100)
    ids = SequenceIds()
    catalog = FailFirstCommitCatalog(
        SqliteCatalogUnitOfWorkFactory(engine=engine, clock=FrozenClock(), ids=ids)
    )
    prepared = _prepared()
    service = ExecutePreparedIngestion(
        blobs=FilesystemBlobStore(paths),
        catalog=catalog,
        clock=FrozenClock(),
        ids=ids,
        metadata_payload=normalized_metadata_payload,
    )

    with pytest.raises(OSError, match="snapshot commit"):
        service.execute(prepared, confirmation=prepared.digest)

    assert len(tuple(paths.blobs.rglob("*.blob"))) == 3
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT count(*) FROM ingestion_runs")).scalar_one() == 0
        assert (
            connection.execute(sa.text("SELECT count(*) FROM source_snapshots")).scalar_one() == 0
        )
        assert (
            connection.execute(sa.text("SELECT count(*) FROM snapshot_records")).scalar_one() == 0
        )
    engine.dispose()
