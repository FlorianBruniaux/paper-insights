from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.pool import NullPool


def create_catalog_engine(database_path: Path, *, busy_timeout_ms: int = 5_000) -> Engine:
    """Create a catalogue engine whose connections enforce the SQLite contract."""
    if not database_path.is_absolute():
        raise ValueError("catalog database path must be absolute")
    if busy_timeout_ms < 0:
        raise ValueError("busy timeout cannot be negative")

    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"timeout": busy_timeout_ms / 1_000},
        poolclass=NullPool,
    )

    @event.listens_for(engine, "connect")
    def _configure_connection(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute(f"PRAGMA busy_timeout = {busy_timeout_ms:d}")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = FULL")
        finally:
            cursor.close()

    return engine
