from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from paper_insights.adapters.catalog.sqlite.engine import create_catalog_engine
from paper_insights.adapters.catalog.sqlite.readers import SqliteCatalogReader
from paper_insights.adapters.catalog.sqlite.uow import SqliteCatalogUnitOfWorkFactory
from paper_insights.application.research.collections import CollectionService
from paper_insights.domain.identifiers import PaperSelector

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)
COLLECTION_ID = UUID("01890f3c-0000-7000-8000-000000000001")
PAPER_ID = UUID("01890f3c-0000-7000-8000-000000000002")


class FrozenClock:
    def now(self) -> datetime:
        return NOW


class SequenceIds:
    def __init__(self, *values: UUID) -> None:
        self._values = deque(values)

    def new(self) -> UUID:
        return self._values.popleft()


def _service(database_path: Path) -> tuple[CollectionService, sa.Engine]:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path}")
    command.upgrade(config, "head")
    engine = create_catalog_engine(database_path)
    with engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO papers (id, created_at) VALUES (:id, :created_at)"),
            {"id": str(PAPER_ID), "created_at": NOW.isoformat()},
        )
        connection.execute(
            sa.text(
                "INSERT INTO paper_identifiers (paper_id, scheme, canonical_value) "
                "VALUES (:paper_id, 'doi', '10.1000/collection-service')"
            ),
            {"paper_id": str(PAPER_ID)},
        )
    factory = SqliteCatalogUnitOfWorkFactory(
        engine=engine,
        clock=FrozenClock(),
        ids=SequenceIds(COLLECTION_ID),
    )
    return CollectionService(factory, SqliteCatalogReader(engine)), engine


def test_collection_service_preserves_empty_collections_and_stable_counts(tmp_path: Path) -> None:
    service, engine = _service(tmp_path / "catalog.sqlite3")
    try:
        created = service.create(slug="reading", title="Reading")

        assert created.paper_count == 0
        assert service.list() == (created,)

        renamed = service.rename(created.collection_id, title="Priority reading")
        added = service.add(
            created.collection_id,
            PaperSelector.by_doi("10.1000/collection-service"),
            note="Read next",
        )
        repeated = service.add(
            created.collection_id,
            PaperSelector.by_doi("10.1000/collection-service"),
            note="Read next",
        )

        assert renamed.title == "Priority reading"
        assert added.paper_count == repeated.paper_count == 1
        assert service.list()[0].paper_count == 1

        removed = service.remove(
            created.collection_id,
            PaperSelector.by_doi("10.1000/collection-service"),
        )

        assert removed.paper_count == 0
        assert service.list()[0].title == "Priority reading"
        assert service.list()[0].paper_count == 0
    finally:
        engine.dispose()
