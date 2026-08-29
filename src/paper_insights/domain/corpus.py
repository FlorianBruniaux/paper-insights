from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from paper_insights.domain.acquisition import ObservedPaperVersion
from paper_insights.domain.identifiers import (
    ArtifactId,
    CollectionId,
    PaperId,
    PaperSelector,
    PaperVersionId,
    RunId,
    Sha256,
    SnapshotId,
    SourceId,
    VersionObservationId,
)


class IngestionStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RunCounters:
    selected_records: int
    new_papers: int = 0
    new_versions: int = 0
    metadata_updates: int = 0
    unchanged_records: int = 0
    failed_records: int = 0

    def __post_init__(self) -> None:
        values = (
            self.selected_records,
            self.new_papers,
            self.new_versions,
            self.metadata_updates,
            self.unchanged_records,
            self.failed_records,
        )
        if any(value < 0 for value in values):
            raise ValueError("run counters cannot be negative")
        outcomes = (
            self.new_versions
            + self.metadata_updates
            + self.unchanged_records
            + self.failed_records
        )
        if self.selected_records != outcomes:
            raise ValueError("selected records must equal the sum of item outcomes")
        if self.new_papers > self.new_versions:
            raise ValueError("new papers cannot exceed new versions")

    @classmethod
    def zero(cls) -> RunCounters:
        return cls(selected_records=0)

    @property
    def status(self) -> IngestionStatus:
        successes = self.selected_records - self.failed_records
        if self.failed_records == 0:
            return IngestionStatus.SUCCEEDED
        if successes > 0:
            return IngestionStatus.PARTIAL
        return IngestionStatus.FAILED


@dataclass(frozen=True, slots=True)
class PaperIdentity:
    paper_id: PaperId
    created_at: datetime


@dataclass(frozen=True, slots=True)
class VersionObservation:
    observation_id: VersionObservationId
    paper_version_id: PaperVersionId
    observed: ObservedPaperVersion
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: ArtifactId
    paper_version_id: PaperVersionId
    version_observation_id: VersionObservationId | None
    sha256: Sha256
    kind: str


@dataclass(frozen=True, slots=True)
class PaperView:
    identity: PaperIdentity
    observations: tuple[VersionObservation, ...]
    artifacts: tuple[ArtifactRef, ...]


@dataclass(frozen=True, slots=True)
class RecordObservation:
    snapshot_id: SnapshotId
    record_ordinal: int
    observed: ObservedPaperVersion
    metadata_artifact: ArtifactRef


@dataclass(frozen=True, slots=True)
class RecordObservationResult:
    paper_id: PaperId
    paper_version_id: PaperVersionId
    version_observation_id: VersionObservationId
    outcome: str
    created_paper: bool


@dataclass(frozen=True, slots=True)
class AttachPreparedRun:
    run_id: RunId
    source_id: SourceId
    prepared_digest: Sha256
    selected_records: int


@dataclass(frozen=True, slots=True)
class IngestionRunRef:
    run_id: RunId
    revision: int


@dataclass(frozen=True, slots=True)
class RecordIngestionItem:
    run_id: RunId
    record: RecordObservation


@dataclass(frozen=True, slots=True)
class IngestionItemRef:
    run_id: RunId
    record_ordinal: int
    outcome: str


@dataclass(frozen=True, slots=True)
class IngestionSummary:
    run_id: RunId
    counters: RunCounters


@dataclass(frozen=True, slots=True)
class CreateCollection:
    slug: str
    title: str


@dataclass(frozen=True, slots=True)
class RenameCollection:
    collection_id: CollectionId
    title: str


@dataclass(frozen=True, slots=True)
class AddCollectionPaper:
    collection_id: CollectionId
    selector: PaperSelector
    note: str | None = None


@dataclass(frozen=True, slots=True)
class RemoveCollectionPaper:
    collection_id: CollectionId
    selector: PaperSelector


@dataclass(frozen=True, slots=True)
class CollectionView:
    collection_id: CollectionId
    slug: str
    title: str
    paper_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class BlobWrite:
    content: bytes
    media_type: str


@dataclass(frozen=True, slots=True)
class StoredBlobRef:
    sha256: Sha256
    size_bytes: int
    media_type: str
    relative_path: Path


@dataclass(frozen=True, slots=True)
class BlobInspection:
    exists: bool
    valid: bool
    sha256: Sha256
    size_bytes: int | None


class CitationFormat(str, Enum):
    BIBTEX = "bibtex"
    MARKDOWN = "markdown"
    CSL_JSON = "csl-json"


@dataclass(frozen=True, slots=True)
class CitationSelector:
    paper: PaperSelector
    paper_version_id: PaperVersionId | None = None


@dataclass(frozen=True, slots=True)
class CitationInput:
    paper_id: PaperId
    observation: VersionObservation
    source_id: SourceId
    source_item_id: str
    snapshot_id: SnapshotId
    record_ordinal: int
    retrieved_at: datetime


@dataclass(frozen=True, slots=True)
class CitationResult:
    schema_version: str
    paper_id: PaperId
    paper_version_id: PaperVersionId
    version_observation_id: VersionObservationId
    format: CitationFormat
    media_type: str
    content: str
    missing_fields: tuple[str, ...]
    warnings: tuple[str, ...]
