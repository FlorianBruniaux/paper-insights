from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from paper_insights.adapters.artifacts.filesystem.store import BlobStoreError, FilesystemBlobStore
from paper_insights.config import Settings
from paper_insights.domain.identifiers import Sha256


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    status: str
    code: str

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code, "name": self.name, "status": self.status}


@dataclass(frozen=True, slots=True)
class DoctorReport:
    status: str
    checks: tuple[DoctorCheck, ...]
    orphaned_blob_count: int | None

    @property
    def is_invalid(self) -> bool:
        return self.status == "INVALID"

    def as_envelope(self) -> dict[str, object]:
        has_unknown = any(check.status == "UNKNOWN" for check in self.checks)
        coverage = "unknown" if has_unknown else "complete"
        errors: list[dict[str, str]] = []
        if self.is_invalid:
            errors.append({"code": "corpus_invalid"})
        return {
            "coverage": {"status": coverage},
            "data": {
                "checks": [check.as_dict() for check in self.checks],
                "orphaned_blob_count": self.orphaned_blob_count,
                "status": self.status,
            },
            "errors": errors,
            "operation": "doctor",
            "schema_version": "paper-insights.cli.v1",
            "truncated": False,
        }


def inspect_corpus(settings: Settings) -> DoctorReport:
    paths = settings.paths
    if not paths.data_root.exists():
        return DoctorReport(
            status="UNKNOWN",
            checks=(
                DoctorCheck("data_root", "UNKNOWN", "data_root_absent"),
                DoctorCheck("catalog", "UNKNOWN", "catalog_unavailable"),
                DoctorCheck("orphaned_blobs", "UNKNOWN", "orphan_proof_unavailable"),
            ),
            orphaned_blob_count=None,
        )
    if not paths.data_root.is_dir() or paths.data_root.is_symlink():
        return DoctorReport(
            status="INVALID",
            checks=(
                DoctorCheck("data_root", "INVALID", "data_root_invalid"),
                DoctorCheck("catalog", "UNKNOWN", "catalog_unavailable"),
                DoctorCheck("orphaned_blobs", "UNKNOWN", "orphan_proof_unavailable"),
            ),
            orphaned_blob_count=None,
        )

    checks: list[DoctorCheck] = [DoctorCheck("data_root", "OK", "data_root_readable")]
    if not paths.catalog.exists():
        checks.extend(
            (
                DoctorCheck("catalog", "UNKNOWN", "catalog_unavailable"),
                DoctorCheck("orphaned_blobs", "UNKNOWN", "orphan_proof_unavailable"),
            )
        )
        return DoctorReport(status="UNKNOWN", checks=tuple(checks), orphaned_blob_count=None)
    if paths.catalog.is_symlink() or not paths.catalog.is_file():
        return _invalid_report("catalog_path_invalid", first_check=checks[0])

    wal_path = Path(f"{paths.catalog}-wal")
    try:
        wal_size = wal_path.stat(follow_symlinks=False).st_size
    except FileNotFoundError:
        wal_size = 0
    except OSError:
        wal_size = -1
    if wal_size != 0:
        checks.extend(
            (
                DoctorCheck("catalog", "UNKNOWN", "catalog_wal_unchecked"),
                DoctorCheck("orphaned_blobs", "UNKNOWN", "orphan_proof_unavailable"),
            )
        )
        return DoctorReport(status="UNKNOWN", checks=tuple(checks), orphaned_blob_count=None)

    try:
        referenced = _read_referenced_blobs(paths.catalog)
    except (OSError, sqlite3.Error, ValueError):
        return _invalid_report("catalog_read_failed", first_check=checks[0])
    checks.append(DoctorCheck("catalog", "OK", "catalog_read_only_check_passed"))

    try:
        orphans = FilesystemBlobStore(paths).find_orphans(referenced)
    except BlobStoreError:
        checks.append(DoctorCheck("orphaned_blobs", "INVALID", "blob_tree_invalid"))
        return DoctorReport(status="INVALID", checks=tuple(checks), orphaned_blob_count=None)
    code = "orphaned_blobs_found" if orphans else "no_orphaned_blobs"
    checks.append(DoctorCheck("orphaned_blobs", "OK", code))
    return DoctorReport(status="OK", checks=tuple(checks), orphaned_blob_count=len(orphans))


def _invalid_report(code: str, first_check: DoctorCheck | None = None) -> DoctorReport:
    checks = (() if first_check is None else (first_check,)) + (
        DoctorCheck("catalog", "INVALID", code),
        DoctorCheck("orphaned_blobs", "UNKNOWN", "orphan_proof_unavailable"),
    )
    return DoctorReport(status="INVALID", checks=checks, orphaned_blob_count=None)


def _read_referenced_blobs(catalog: Path) -> frozenset[Sha256]:
    uri = f"{catalog.resolve().as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        result = connection.execute("PRAGMA quick_check").fetchone()
        if result != ("ok",):
            raise ValueError("catalog integrity check failed")
        rows = connection.execute("SELECT sha256 FROM stored_blobs").fetchall()
        return frozenset(Sha256(row[0]) for row in rows)
    finally:
        connection.close()
