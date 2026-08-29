from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine

from alembic import command
from paper_insights.adapters.catalog.sqlite.engine import create_catalog_engine

ROOT = Path(__file__).resolve().parents[2]


def migrate_to_head(database_path: Path) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path}")
    command.upgrade(config, "head")


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.sqlite3"
    migrate_to_head(path)
    return path


@pytest.fixture
def engine(database_path: Path) -> Engine:
    catalog_engine = create_catalog_engine(database_path, busy_timeout_ms=100)
    yield catalog_engine
    catalog_engine.dispose()
