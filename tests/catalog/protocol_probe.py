from __future__ import annotations

from typing import cast

from sqlalchemy import Engine

from paper_insights.adapters.catalog.sqlite.uow import (
    SqliteCatalogUnitOfWork,
    SqliteCatalogUnitOfWorkFactory,
)
from paper_insights.application.ports.catalog import (
    CatalogUnitOfWork,
    CatalogUnitOfWorkFactory,
)
from paper_insights.application.ports.clock import Clock
from paper_insights.application.ports.ids import IdGenerator

engine = cast(Engine, None)
clock = cast(Clock, None)
ids = cast(IdGenerator, None)

uow: CatalogUnitOfWork = SqliteCatalogUnitOfWork(engine, clock, ids)
factory: CatalogUnitOfWorkFactory = SqliteCatalogUnitOfWorkFactory(
    engine=engine,
    clock=clock,
    ids=ids,
)
