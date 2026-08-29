from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from uuid import UUID

from paper_insights.domain.acquisition import ObservedPaperVersion, RecordLocator
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
from paper_insights.domain.retrieval import CoverageStatus


class IngestionStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class IngestionOutcome(str, Enum):
    NEW_VERSION = "new_version"
    METADATA_UPDATE = "metadata_update"
    UNCHANGED = "unchanged"
    FAILED = "failed"


class ArtifactKind(str, Enum):
    METADATA = "metadata"
    PDF = "pdf"
    TEXT = "text"
    ANALYSIS = "analysis"


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
    kind: ArtifactKind


@dataclass(frozen=True, slots=True)
class PaperView:
    identity: PaperIdentity
    observations: tuple[VersionObservation, ...]
    artifacts: tuple[ArtifactRef, ...]


@dataclass(frozen=True, slots=True)
class RecordObservation:
    run_id: RunId
    snapshot_id: SnapshotId
    record_ordinal: int
    observed: ObservedPaperVersion
    metadata_blob: MetadataBlobRef

    def __post_init__(self) -> None:
        if self.record_ordinal < 0:
            raise ValueError("record ordinal cannot be negative")
        if self.metadata_blob.normalized_sha256 != self.observed.normalized_sha256:
            raise ValueError("metadata blob does not match normalized observation")


@dataclass(frozen=True, slots=True)
class RecordObservationResult:
    paper_id: PaperId
    paper_version_id: PaperVersionId
    version_observation_id: VersionObservationId
    outcome: IngestionOutcome
    created_paper: bool

    def __post_init__(self) -> None:
        if self.created_paper and self.outcome is not IngestionOutcome.NEW_VERSION:
            raise ValueError("created_paper is valid only for a new version")


@dataclass(frozen=True, slots=True)
class AttachPreparedRun:
    run_id: RunId
    source_id: SourceId
    prepared_digest: Sha256
    query_json: str
    pages: tuple[PreparedSnapshotAttachment, ...]
    selected_locators: tuple[RecordLocator, ...]

    def __post_init__(self) -> None:
        try:
            query = json.loads(self.query_json)
        except json.JSONDecodeError as exc:
            raise ValueError("query_json must be valid JSON") from exc
        if not isinstance(query, dict) or not query.get("schema_version"):
            raise ValueError("query_json requires a schema version")
        canonical_query = json.dumps(
            query, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        if canonical_query != self.query_json:
            raise ValueError("query_json must use canonical JSON")
        if tuple(page.page_ordinal for page in self.pages) != tuple(range(len(self.pages))):
            raise ValueError("prepared pages must be contiguous and ordered")
        if len({page.capture_id for page in self.pages}) != len(self.pages):
            raise ValueError("prepared page capture IDs must be unique")
        available = {
            record.locator for page in self.pages for record in page.records
        }
        if len(set(self.selected_locators)) != len(self.selected_locators):
            raise ValueError("selected locators cannot contain duplicates")
        if any(locator not in available for locator in self.selected_locators):
            raise ValueError("selected locator is missing from snapshot attachments")
        ordered = tuple(
            record.locator for page in self.pages for record in page.records
        )
        positions = {locator: index for index, locator in enumerate(ordered)}
        selected_positions = tuple(positions[item] for item in self.selected_locators)
        if selected_positions != tuple(sorted(selected_positions)):
            raise ValueError("selected locators must preserve snapshot order")

    @property
    def selected_records(self) -> int:
        return len(self.selected_locators)


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
    outcome: IngestionOutcome


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

    def __post_init__(self) -> None:
        if not self.content or not self.media_type:
            raise ValueError("blob content and media type are required")


@dataclass(frozen=True, slots=True)
class StoredBlobRef:
    sha256: Sha256
    size_bytes: int
    media_type: str
    relative_path: Path

    def __post_init__(self) -> None:
        if self.size_bytes < 0 or not self.media_type:
            raise ValueError("stored blob size and media type are invalid")
        if self.relative_path.is_absolute() or ".." in self.relative_path.parts:
            raise ValueError("stored blob path must be confined and relative")


@dataclass(frozen=True, slots=True)
class MetadataBlobRef:
    blob: StoredBlobRef
    normalized_sha256: Sha256


@dataclass(frozen=True, slots=True)
class SnapshotRecordAttachment:
    locator: RecordLocator


@dataclass(frozen=True, slots=True)
class PreparedSnapshotAttachment:
    page_ordinal: int
    capture_id: UUID
    blob: StoredBlobRef
    request_fingerprint: Sha256
    retrieved_at: datetime
    next_cursor: str | None
    records: tuple[SnapshotRecordAttachment, ...]

    def __post_init__(self) -> None:
        if self.page_ordinal < 0 or self.capture_id.version != 7:
            raise ValueError("invalid prepared page identity")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() != timedelta(0):
            raise ValueError("prepared page retrieval timestamp must use UTC")
        expected = tuple(range(len(self.records)))
        actual = tuple(record.locator.record_ordinal for record in self.records)
        if actual != expected:
            raise ValueError("snapshot records must be contiguous and ordered")
        if any(record.locator.page_ordinal != self.page_ordinal for record in self.records):
            raise ValueError("snapshot record references another page")


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
    source_id: SourceId
    source_item_id: str
    snapshot_id: SnapshotId
    record_ordinal: int
    retrieved_at: datetime
    coverage: CoverageStatus
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != "citation-v1":
            raise ValueError("unsupported citation schema")
        if not self.media_type or not self.source_item_id or self.record_ordinal < 0:
            raise ValueError("citation content or provenance is invalid")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() != timedelta(0):
            raise ValueError("citation retrieval timestamp must use UTC")
