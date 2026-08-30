from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

from paper_insights.application.diagnostics import CatalogProbe, DoctorCheck
from paper_insights.domain.corpus import StoredBlobRef
from paper_insights.domain.identifiers import Sha256
from paper_insights.paths import CorpusPaths

_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)


class SqliteCatalogDiagnostics:
    def __init__(self, paths: CorpusPaths) -> None:
        self._paths = paths

    def inspect(self) -> CatalogProbe:
        paths = self._paths
        if not paths.data_root.exists():
            return CatalogProbe(
                status="UNKNOWN",
                checks=(
                    DoctorCheck("data_root", "UNKNOWN", "data_root_absent"),
                    DoctorCheck("catalog", "UNKNOWN", "catalog_unavailable"),
                ),
            )
        if not paths.data_root.is_dir() or paths.data_root.is_symlink():
            return CatalogProbe(
                status="INVALID",
                checks=(
                    DoctorCheck("data_root", "INVALID", "data_root_invalid"),
                    DoctorCheck("catalog", "UNKNOWN", "catalog_unavailable"),
                ),
            )

        root_check = DoctorCheck("data_root", "OK", "data_root_readable")
        if not paths.catalog.exists():
            return CatalogProbe(
                status="UNKNOWN",
                checks=(root_check, DoctorCheck("catalog", "UNKNOWN", "catalog_unavailable")),
            )
        if paths.catalog.is_symlink() or not paths.catalog.is_file():
            return self._invalid("catalog_path_invalid", root_check)

        wal_path = Path(f"{paths.catalog}-wal")
        try:
            wal_size = wal_path.stat(follow_symlinks=False).st_size
        except FileNotFoundError:
            wal_size = 0
        except OSError:
            wal_size = -1
        if wal_size != 0:
            return CatalogProbe(
                status="UNKNOWN",
                checks=(root_check, DoctorCheck("catalog", "UNKNOWN", "catalog_wal_unchecked")),
            )

        try:
            references = self._read_references(paths.catalog)
        except (OSError, sqlite3.Error):
            return self._unknown("catalog_read_unavailable", root_check)
        except ValueError:
            return self._invalid("catalog_read_failed", root_check)
        return CatalogProbe(
            status="OK",
            checks=(root_check, DoctorCheck("catalog", "OK", "catalog_read_only_check_passed")),
            referenced_blobs=references,
        )

    @staticmethod
    def _invalid(code: str, root_check: DoctorCheck) -> CatalogProbe:
        return CatalogProbe(
            status="INVALID",
            checks=(root_check, DoctorCheck("catalog", "INVALID", code)),
        )

    @staticmethod
    def _unknown(code: str, root_check: DoctorCheck) -> CatalogProbe:
        return CatalogProbe(
            status="UNKNOWN",
            checks=(root_check, DoctorCheck("catalog", "UNKNOWN", code)),
        )

    @staticmethod
    def _read_references(catalog: Path) -> tuple[StoredBlobRef, ...]:
        descriptor = SqliteCatalogDiagnostics._open_catalog_descriptor(catalog)
        connection: sqlite3.Connection | None = None
        before: tuple[int, int, int, int, int] | None = None
        try:
            before = SqliteCatalogDiagnostics._identity(os.fstat(descriptor))
            if before != SqliteCatalogDiagnostics._catalog_identity(catalog):
                raise OSError("catalog binding changed before inspection")
            descriptor_path = Path("/dev/fd") / str(descriptor)
            uri = f"{descriptor_path.as_uri()}?mode=ro&immutable=1"
            connection = sqlite3.connect(uri, uri=True)
            connection.execute("PRAGMA query_only=ON")
            result = connection.execute("PRAGMA quick_check").fetchone()
            if result != ("ok",):
                raise ValueError("catalog integrity check failed")
            rows = connection.execute(
                "SELECT sha256, size_bytes, media_type, relative_path "
                "FROM stored_blobs ORDER BY sha256"
            ).fetchall()
            references = tuple(
                StoredBlobRef(
                    sha256=Sha256(row[0]),
                    size_bytes=row[1],
                    media_type=row[2],
                    relative_path=Path(row[3]),
                )
                for row in rows
            )
        except sqlite3.Error as exc:
            if SqliteCatalogDiagnostics._sqlite_error_is_unavailable(exc):
                raise
            raise ValueError("catalog contents are invalid") from exc
        finally:
            try:
                if connection is not None:
                    connection.close()
            finally:
                try:
                    after = SqliteCatalogDiagnostics._catalog_identity(catalog)
                    if before is not None and before != after:
                        raise OSError("catalog binding changed during inspection")
                finally:
                    os.close(descriptor)
        return references

    @staticmethod
    def _open_catalog_descriptor(catalog: Path) -> int:
        parent_descriptor = SqliteCatalogDiagnostics._open_absolute_directory(catalog.parent)
        try:
            return os.open(catalog.name, _READ_FLAGS, dir_fd=parent_descriptor)
        finally:
            os.close(parent_descriptor)

    @staticmethod
    def _open_absolute_directory(path: Path) -> int:
        if not path.is_absolute():
            raise OSError("catalog parent must be absolute")
        current = os.open(path.anchor, _DIRECTORY_FLAGS)
        try:
            for part in path.parts[1:]:
                scanned = os.stat(part, dir_fd=current, follow_symlinks=False)
                if not stat.S_ISDIR(scanned.st_mode):
                    raise OSError("catalog parent is not a directory")
                child = -1
                try:
                    child = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
                    opened = os.fstat(child)
                    if (scanned.st_dev, scanned.st_ino) != (opened.st_dev, opened.st_ino):
                        raise OSError("catalog parent binding changed")
                except BaseException:
                    if child >= 0:
                        os.close(child)
                    raise
                os.close(current)
                current = child
            return current
        except BaseException:
            os.close(current)
            raise

    @staticmethod
    def _catalog_identity(catalog: Path) -> tuple[int, int, int, int, int]:
        metadata = catalog.stat(follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError("catalog path is no longer a regular file")
        return SqliteCatalogDiagnostics._identity(metadata)

    @staticmethod
    def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
        return (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )

    @staticmethod
    def _sqlite_error_is_unavailable(error: sqlite3.Error) -> bool:
        code = getattr(error, "sqlite_errorcode", None)
        if code is None:
            return True
        primary = code & 0xFF
        return primary in {
            sqlite3.SQLITE_BUSY,
            sqlite3.SQLITE_CANTOPEN,
            sqlite3.SQLITE_INTERRUPT,
            sqlite3.SQLITE_IOERR,
            sqlite3.SQLITE_LOCKED,
            sqlite3.SQLITE_PERM,
            sqlite3.SQLITE_READONLY,
        }
