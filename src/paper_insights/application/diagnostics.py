from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from paper_insights.domain.corpus import BlobInspection, StoredBlobRef
from paper_insights.domain.identifiers import Sha256

DoctorStatus = Literal["OK", "UNKNOWN", "INVALID"]


class DiagnosticUnavailableError(OSError):
    """A read-only diagnostic could not obtain conclusive local evidence."""


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    status: DoctorStatus
    code: str

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code, "name": self.name, "status": self.status}


@dataclass(frozen=True, slots=True)
class CatalogProbe:
    status: DoctorStatus
    checks: tuple[DoctorCheck, ...]
    referenced_blobs: tuple[StoredBlobRef, ...] = ()


@dataclass(frozen=True, slots=True)
class DoctorReport:
    status: DoctorStatus
    checks: tuple[DoctorCheck, ...]
    orphaned_blob_count: int | None

    @property
    def is_complete(self) -> bool:
        return self.status == "OK"

    def as_envelope(self) -> dict[str, object]:
        has_unknown = any(check.status == "UNKNOWN" for check in self.checks)
        coverage = "unknown" if has_unknown else "complete"
        errors: list[dict[str, str]] = []
        if self.status == "INVALID":
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


class CatalogDiagnosticPort(Protocol):
    def inspect(self) -> CatalogProbe: ...


class BlobDiagnosticPort(Protocol):
    def inspect(self, ref: StoredBlobRef) -> BlobInspection: ...

    def find_orphans(self, referenced: frozenset[Sha256]) -> tuple[Path, ...]: ...


class DoctorService:
    def __init__(self, catalog: CatalogDiagnosticPort, blobs: BlobDiagnosticPort) -> None:
        self._catalog = catalog
        self._blobs = blobs

    def inspect(self) -> DoctorReport:
        catalog = self._catalog.inspect()
        if catalog.status != "OK":
            return DoctorReport(
                status=catalog.status,
                checks=(
                    *catalog.checks,
                    DoctorCheck("orphaned_blobs", "UNKNOWN", "orphan_proof_unavailable"),
                ),
                orphaned_blob_count=None,
            )

        referenced_failure = self._check_referenced_blobs(catalog)
        if referenced_failure is not None:
            return referenced_failure

        referenced = frozenset(ref.sha256 for ref in catalog.referenced_blobs)
        try:
            orphans = self._blobs.find_orphans(referenced)
        except DiagnosticUnavailableError:
            return DoctorReport(
                status="UNKNOWN",
                checks=(
                    *catalog.checks,
                    DoctorCheck("orphaned_blobs", "UNKNOWN", "orphan_proof_unavailable"),
                ),
                orphaned_blob_count=None,
            )
        except OSError:
            return DoctorReport(
                status="INVALID",
                checks=(
                    *catalog.checks,
                    DoctorCheck("orphaned_blobs", "INVALID", "blob_tree_invalid"),
                ),
                orphaned_blob_count=None,
            )
        referenced_failure = self._check_referenced_blobs(catalog)
        if referenced_failure is not None:
            return referenced_failure
        code = "orphaned_blobs_found" if orphans else "no_orphaned_blobs"
        return DoctorReport(
            status="OK",
            checks=(*catalog.checks, DoctorCheck("orphaned_blobs", "OK", code)),
            orphaned_blob_count=len(orphans),
        )

    def _check_referenced_blobs(self, catalog: CatalogProbe) -> DoctorReport | None:
        for ref in catalog.referenced_blobs:
            try:
                inspection = self._blobs.inspect(ref)
            except DiagnosticUnavailableError:
                return self._unknown_blob_report(catalog, "referenced_blob_unavailable")
            if not inspection.exists:
                return self._invalid_blob_report(catalog, "referenced_blob_missing")
            if not inspection.valid:
                return self._invalid_blob_report(catalog, "referenced_blob_corrupt")
        return None

    @staticmethod
    def _invalid_blob_report(catalog: CatalogProbe, code: str) -> DoctorReport:
        return DoctorReport(
            status="INVALID",
            checks=(*catalog.checks, DoctorCheck("referenced_blobs", "INVALID", code)),
            orphaned_blob_count=None,
        )

    @staticmethod
    def _unknown_blob_report(catalog: CatalogProbe, code: str) -> DoctorReport:
        return DoctorReport(
            status="UNKNOWN",
            checks=(*catalog.checks, DoctorCheck("referenced_blobs", "UNKNOWN", code)),
            orphaned_blob_count=None,
        )
