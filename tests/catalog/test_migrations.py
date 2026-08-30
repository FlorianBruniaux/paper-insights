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


def test_populated_catalog_can_downgrade_and_reapply(tmp_path: Path) -> None:
    database_path = tmp_path / "populated-roundtrip.sqlite3"
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database_path}")
    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO stored_blobs "
            "(id, sha256, size_bytes, media_type, relative_path, created_at) "
            "VALUES ('01890f3d-0000-7000-8000-000000000001', ?, 1, "
            "'application/atom+xml', 'blobs/aa/source', ?)",
            ("a" * 64, "2026-08-29T08:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO source_snapshots "
            "(id, capture_id, source_id, stored_blob_id, request_fingerprint, retrieved_at) "
            "VALUES ('01890f3d-0000-7000-8000-000000000002', "
            "'01890f3d-0000-7000-8000-000000000003', 'arxiv', "
            "'01890f3d-0000-7000-8000-000000000001', ?, ?)",
            ("b" * 64, "2026-08-29T08:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO snapshot_records "
            "(source_snapshot_id, ordinal, source_item_id, source_version_key, "
            "raw_record_sha256) VALUES "
            "('01890f3d-0000-7000-8000-000000000002', 0, '2608.00001', "
            "'2608.00001v1', ?)",
            ("c" * 64,),
        )
        connection.execute(
            "INSERT INTO ingestion_runs "
            "(id, source_id, prepared_digest, query_json, status, started_at, "
            "selected_records, new_papers, new_versions, metadata_updates, "
            "unchanged_records, failed_records) VALUES "
            "('01890f3d-0000-7000-8000-000000000004', 'arxiv', ?, "
            "'{\"schema_version\":\"discovery-query-v1\"}', 'running', ?, 1, 0, 0, 0, 0, 0)",
            ("d" * 64, "2026-08-29T08:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO ingestion_run_snapshots "
            "(run_id, page_ordinal, source_snapshot_id, source_id) VALUES "
            "('01890f3d-0000-7000-8000-000000000004', 0, "
            "'01890f3d-0000-7000-8000-000000000002', 'arxiv')"
        )
        connection.execute(
            "INSERT INTO ingestion_run_selected_records "
            "(run_id, selection_ordinal, source_snapshot_id, record_ordinal) VALUES "
            "('01890f3d-0000-7000-8000-000000000004', 0, "
            "'01890f3d-0000-7000-8000-000000000002', 0)"
        )
        connection.execute(
            "INSERT INTO papers (id, created_at) VALUES "
            "('01890f3d-0000-7000-8000-000000000005', ?)",
            ("2026-08-29T08:00:00+00:00",),
        )
        connection.execute(
            "INSERT INTO paper_versions "
            "(id, paper_id, source_id, source_version_key, is_current, created_at) VALUES "
            "('01890f3d-0000-7000-8000-000000000006', "
            "'01890f3d-0000-7000-8000-000000000005', 'arxiv', '2608.00001v1', 1, ?)",
            ("2026-08-29T08:00:00+00:00",),
        )
        connection.execute(
            "INSERT INTO version_observations "
            "(id, paper_version_id, normalized_sha256, observed_at, origin_source_id, "
            "origin_run_id, origin_source_snapshot_id, origin_record_ordinal, title, "
            "title_normalized) VALUES "
            "('01890f3d-0000-7000-8000-000000000007', "
            "'01890f3d-0000-7000-8000-000000000006', ?, ?, 'arxiv', "
            "'01890f3d-0000-7000-8000-000000000004', "
            "'01890f3d-0000-7000-8000-000000000002', 0, 'Title', 'title')",
            ("e" * 64, "2026-08-29T08:00:00+00:00"),
        )
        connection.execute(
            "UPDATE snapshot_records SET version_observation_id = "
            "'01890f3d-0000-7000-8000-000000000007'"
        )

    command.downgrade(config, "base")
    command.upgrade(config, "head")

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


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
