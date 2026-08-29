from __future__ import annotations

import sqlite3
from pathlib import Path

from paper_insights.application.diagnostics import CatalogProbe, DoctorCheck
from paper_insights.domain.corpus import StoredBlobRef
from paper_insights.domain.identifiers import Sha256
from paper_insights.paths import CorpusPaths


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
        except (OSError, sqlite3.Error, ValueError):
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
    def _read_references(catalog: Path) -> tuple[StoredBlobRef, ...]:
        uri = f"{catalog.resolve().as_uri()}?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True)
        try:
            connection.execute("PRAGMA query_only=ON")
            result = connection.execute("PRAGMA quick_check").fetchone()
            if result != ("ok",):
                raise ValueError("catalog integrity check failed")
            rows = connection.execute(
                "SELECT sha256, size_bytes, media_type, relative_path "
                "FROM stored_blobs ORDER BY sha256"
            ).fetchall()
            return tuple(
                StoredBlobRef(
                    sha256=Sha256(row[0]),
                    size_bytes=row[1],
                    media_type=row[2],
                    relative_path=Path(row[3]),
                )
                for row in rows
            )
        finally:
            connection.close()
