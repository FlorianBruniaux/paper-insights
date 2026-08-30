from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy.exc import DBAPIError

from paper_insights.adapters.catalog.sqlite.engine import create_catalog_engine


def _database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO marker VALUES ('unchanged')")
        connection.commit()
    finally:
        connection.close()


def test_catalog_engine_rejects_a_symlink_swap_before_connection(tmp_path: Path) -> None:
    catalog = tmp_path / "corpus" / "catalog.sqlite3"
    outside = tmp_path / "outside.sqlite3"
    catalog.parent.mkdir()
    _database(catalog)
    _database(outside)
    engine = create_catalog_engine(catalog)
    catalog.unlink()
    catalog.symlink_to(outside)

    with pytest.raises(DBAPIError, match=r"binding|symbolic"):
        with engine.connect():
            pass

    connection = sqlite3.connect(f"file:{outside}?mode=ro", uri=True)
    try:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("unchanged",)
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    finally:
        connection.close()
        engine.dispose()


def test_catalog_engine_requires_an_existing_regular_database(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    engine = create_catalog_engine(missing)

    with pytest.raises(DBAPIError):
        with engine.connect():
            pass

    assert not missing.exists()
    engine.dispose()
