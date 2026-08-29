from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from alembic import command
from paper_insights.adapters.catalog.sqlite.models import metadata

ROOT = Path(__file__).resolve().parents[2]


def migrate_to_head(database_path: Path) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path}")
    command.upgrade(config, "head")


EXPECTED_TABLES = {
    "alembic_version",
    "artifacts",
    "author_identifier_evidence",
    "author_identifiers",
    "authors",
    "catalog_meta",
    "collection_errors",
    "collection_papers",
    "collections",
    "ingestion_run_items",
    "ingestion_run_selected_records",
    "ingestion_run_snapshots",
    "ingestion_runs",
    "paper_authors",
    "paper_identifier_evidence",
    "paper_identifiers",
    "paper_version_categories",
    "paper_versions",
    "papers",
    "snapshot_records",
    "source_snapshots",
    "sources",
    "stored_blobs",
    "version_identifier_evidence",
    "version_identifiers",
    "version_observations",
}


def test_zero_to_head_creates_complete_healthy_catalog(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.sqlite3"

    migrate_to_head(database_path)

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            if not row[0].startswith("sqlite_")
        }
        meta = connection.execute(
            "SELECT singleton_id, revision, schema_contract_version FROM catalog_meta"
        ).fetchall()
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        quick_check = connection.execute("PRAGMA quick_check").fetchone()
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()

    assert tables == EXPECTED_TABLES
    assert meta == [(1, 0, "catalog-v1")]
    assert foreign_keys == []
    assert quick_check == ("ok",)
    assert journal_mode == ("wal",)


def test_initial_migration_is_the_only_head() -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))

    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["0001_initial_catalog"]


def test_initial_upgrade_can_downgrade_and_reapply(tmp_path: Path) -> None:
    database_path = tmp_path / "roundtrip.sqlite3"
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path}")

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    with sqlite3.connect(database_path) as connection:
        remaining = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            if not row[0].startswith("sqlite_")
        }
    assert remaining == {"alembic_version"}

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert connection.execute("SELECT revision FROM catalog_meta").fetchone() == (0,)


def test_head_schema_matches_sqlalchemy_metadata(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog.sqlite3"
    migrate_to_head(database_path)
    engine = create_engine(f"sqlite+pysqlite:///{database_path}")
    try:
        with engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection), metadata)
    finally:
        engine.dispose()

    assert differences == []
