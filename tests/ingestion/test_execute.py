from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from paper_insights.adapters.artifacts.filesystem.store import FilesystemBlobStore
from paper_insights.adapters.catalog.sqlite.engine import create_catalog_engine
from paper_insights.adapters.catalog.sqlite.uow import SqliteCatalogUnitOfWorkFactory
from paper_insights.adapters.providers.arxiv.normalizer import normalized_metadata_payload
from paper_insights.adapters.providers.arxiv.parser import parse_arxiv_feed
from paper_insights.application.ingestion.execute import ExecutePreparedIngestion
from paper_insights.domain.acquisition import (
    DiscoveryBatch,
    DiscoveryPage,
    DiscoveryQuery,
    PreparedDiscovery,
)
from paper_insights.domain.corpus import IngestionStatus
from paper_insights.domain.identifiers import Sha256, SourceId
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


def _migrate(database: Path) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")


def _prepared() -> PreparedDiscovery:
    payload = (FIXTURES / "page-1.xml").read_bytes()
    parsed = parse_arxiv_feed(payload, page_ordinal=0)
    observations = tuple(
        record.observation for record in parsed.records if record.observation is not None
    )
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
        records=observations,
        issues=parsed.issues,
    )
    return PreparedDiscovery.prepare(
        batch=batch,
        selected_records=tuple(record.locator for record in parsed.records),
        prepared_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )


def test_execute_persists_the_confirmed_batch_and_replay_is_unchanged(tmp_path: Path) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    paths.data_root.mkdir(parents=True)
    _migrate(paths.catalog)
    engine = create_catalog_engine(paths.catalog, busy_timeout_ms=100)
    ids = SequenceIds()
    service = ExecutePreparedIngestion(
        blobs=FilesystemBlobStore(paths),
        catalog=SqliteCatalogUnitOfWorkFactory(engine=engine, clock=FrozenClock(), ids=ids),
        clock=FrozenClock(),
        ids=ids,
        metadata_payload=normalized_metadata_payload,
    )
    prepared = _prepared()

    first = service.execute(prepared, confirmation=prepared.digest)
    replay = service.execute(prepared, confirmation=prepared.digest)

    assert first.counters.status is IngestionStatus.SUCCEEDED
    assert first.counters.new_papers == 2
    assert first.counters.new_versions == 2
    assert replay.counters.status is IngestionStatus.SUCCEEDED
    assert replay.counters.unchanged_records == 2
    with engine.connect() as connection:
        assert (
            connection.execute(sa.text("SELECT count(*) FROM source_snapshots")).scalar_one() == 1
        )
        assert connection.execute(sa.text("SELECT count(*) FROM papers")).scalar_one() == 2
        assert (
            connection.execute(sa.text("SELECT count(*) FROM version_observations")).scalar_one()
            == 2
        )
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert connection.exec_driver_sql("PRAGMA quick_check").scalar_one() == "ok"
    assert len(tuple(paths.blobs.rglob("*.blob"))) == 3
    engine.dispose()
