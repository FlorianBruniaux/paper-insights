from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TextIO

from paper_insights.adapters.artifacts.filesystem.store import FilesystemBlobStore
from paper_insights.adapters.diagnostics.sqlite import SqliteCatalogDiagnostics
from paper_insights.application.diagnostics import DoctorService
from paper_insights.config import Settings
from paper_insights.interfaces.cli.app import run


def build_doctor_service(settings: Settings) -> DoctorService:
    paths = settings.paths
    return DoctorService(SqliteCatalogDiagnostics(paths), FilesystemBlobStore(paths))


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    return run(
        argv,
        doctor_service_factory=build_doctor_service,
        environ=environ,
        stdout=stdout,
        stderr=stderr,
    )
