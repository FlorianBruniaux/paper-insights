from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from paper_insights.adapters.catalog.sqlite.uow import SqliteCatalogUnitOfWorkFactory
from paper_insights.domain.corpus import (
    AddCollectionPaper,
    CreateCollection,
    RemoveCollectionPaper,
    RenameCollection,
)
from paper_insights.domain.identifiers import CollectionId, PaperId, PaperSelector

NOW = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
IDS = tuple(UUID(f"01890f3a-0000-7000-8000-{value:012d}") for value in range(1, 20))


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


def _revision(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                sa.text("SELECT revision FROM catalog_meta WHERE singleton_id = 1")
            ).scalar_one()
        )


def _collection_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(sa.text("SELECT count(*) FROM collections")).scalar_one())


def test_connection_enforces_catalog_pragmas(engine: Engine) -> None:
    with engine.connect() as connection:
        pragmas = {
            "foreign_keys": connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one(),
            "busy_timeout": connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one(),
            "journal_mode": connection.exec_driver_sql("PRAGMA journal_mode").scalar_one(),
            "synchronous": connection.exec_driver_sql("PRAGMA synchronous").scalar_one(),
        }

    assert pragmas == {
        "foreign_keys": 1,
        "busy_timeout": 100,
        "journal_mode": "wal",
        "synchronous": 2,
    }


def test_visible_mutations_increment_revision_once_per_transaction(engine: Engine) -> None:
    factory = _factory(engine, *IDS[:2])

    with factory.begin() as uow:
        first = uow.collections.create(CreateCollection(slug="reading", title="Reading"))
        second = uow.collections.create(CreateCollection(slug="writing", title="Writing"))
        uow.commit()

    assert first.paper_count == second.paper_count == 0
    assert _collection_count(engine) == 2
    assert _revision(engine) == 1

    with factory.begin() as uow:
        uow.commit()

    assert _revision(engine) == 1


def test_rollback_removes_rows_and_does_not_increment_revision(engine: Engine) -> None:
    factory = _factory(engine, IDS[2])

    with factory.begin() as uow:
        uow.collections.create(CreateCollection(slug="discarded", title="Discarded"))
        uow.rollback()

    assert _collection_count(engine) == 0
    assert _revision(engine) == 0


def test_context_exception_rolls_back_without_revision(engine: Engine) -> None:
    factory = _factory(engine, IDS[3])

    with pytest.raises(RuntimeError, match="injected"):
        with factory.begin() as uow:
            uow.collections.create(CreateCollection(slug="broken", title="Broken"))
            raise RuntimeError("injected")

    assert _collection_count(engine) == 0
    assert _revision(engine) == 0


def test_second_writer_respects_busy_timeout_without_corrupting_counts(engine: Engine) -> None:
    first_factory = _factory(engine, IDS[4])
    second_factory = _factory(engine, IDS[5])

    first = first_factory.begin()
    first.__enter__()
    first.collections.create(CreateCollection(slug="first", title="First"))
    started = monotonic()
    try:
        with pytest.raises(OperationalError, match="database is locked"):
            with second_factory.begin():
                pass
        elapsed = monotonic() - started
        first.commit()
    finally:
        first.__exit__(None, None, None)

    assert elapsed >= 0.08
    assert _collection_count(engine) == 1
    assert _revision(engine) == 1


def test_collection_mutations_change_revision_only_when_state_changes(engine: Engine) -> None:
    paper_id = PaperId(IDS[6])
    with engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO papers (id, created_at) VALUES (:id, :created_at)"),
            {"id": str(paper_id), "created_at": NOW.isoformat()},
        )
        connection.execute(
            sa.text(
                "INSERT INTO paper_identifiers (paper_id, scheme, canonical_value) "
                "VALUES (:paper_id, 'doi', '10.1000/catalog-test')"
            ),
            {"paper_id": str(paper_id)},
        )
    factory = _factory(engine, IDS[7])

    with factory.begin() as uow:
        created = uow.collections.create(CreateCollection(slug="queue", title="Queue"))
        uow.commit()
    collection_id = CollectionId(created.collection_id.value)

    with factory.begin() as uow:
        renamed = uow.collections.rename(
            RenameCollection(collection_id=collection_id, title="Priority queue")
        )
        added = uow.collections.add(
            AddCollectionPaper(
                collection_id=collection_id,
                selector=PaperSelector.by_doi("10.1000/catalog-test"),
                note="read next",
            )
        )
        uow.commit()

    assert renamed.title == "Priority queue"
    assert added.paper_count == 1
    assert _revision(engine) == 2

    with factory.begin() as uow:
        same_title = uow.collections.rename(
            RenameCollection(collection_id=collection_id, title="Priority queue")
        )
        same_paper = uow.collections.add(
            AddCollectionPaper(
                collection_id=collection_id,
                selector=PaperSelector.by_doi("10.1000/catalog-test"),
                note="read next",
            )
        )
        uow.commit()

    assert same_title.title == renamed.title
    assert same_title.paper_count == 1
    assert same_paper == added
    assert _revision(engine) == 2

    with factory.begin() as uow:
        removed = uow.collections.remove(
            RemoveCollectionPaper(
                collection_id=collection_id,
                selector=PaperSelector(paper_id=paper_id),
            )
        )
        uow.commit()

    assert removed.paper_count == 0
    assert _revision(engine) == 3
