from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.pool import NullPool


def create_catalog_engine(database_path: Path, *, busy_timeout_ms: int = 5_000) -> Engine:
    """Create a catalogue engine whose connections enforce the SQLite contract."""
    if not database_path.is_absolute():
        raise ValueError("catalog database path must be absolute")
    if busy_timeout_ms < 0:
        raise ValueError("busy timeout cannot be negative")
    try:
        expected = os.lstat(database_path)
    except FileNotFoundError:
        expected_identity = None
    except OSError as exc:
        raise ValueError("catalog database is unavailable") from exc
    else:
        if stat.S_ISLNK(expected.st_mode) or not stat.S_ISREG(expected.st_mode):
            raise ValueError("catalog database must be a regular file")
        expected_identity = (expected.st_dev, expected.st_ino)
    encoded_path = quote(str(database_path), safe="/")

    def _open_existing() -> sqlite3.Connection:
        return sqlite3.connect(
            f"file:{encoded_path}?mode=rw",
            uri=True,
            timeout=busy_timeout_ms / 1_000,
            check_same_thread=False,
        )

    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        creator=_open_existing,
        poolclass=NullPool,
    )

    @event.listens_for(engine, "connect")
    def _configure_connection(dbapi_connection: object, _record: object) -> None:
        _assert_catalog_binding(database_path, expected_identity)
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute(f"PRAGMA busy_timeout = {busy_timeout_ms:d}")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = FULL")
            _assert_catalog_binding(database_path, expected_identity)
        finally:
            cursor.close()

    return engine


def _assert_catalog_binding(
    database_path: Path,
    expected_identity: tuple[int, int] | None,
) -> None:
    try:
        current = os.lstat(database_path)
    except OSError as exc:
        raise sqlite3.OperationalError("catalog database binding is unavailable") from exc
    if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode):
        raise sqlite3.OperationalError("catalog database binding is symbolic or unsafe")
    if expected_identity is None or (current.st_dev, current.st_ino) != expected_identity:
        raise sqlite3.OperationalError("catalog database binding changed")
