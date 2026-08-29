from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from uuid import UUID

from paper_insights.domain.acquisition import (
    ObservedPaperVersion,
    PreparedDiscovery,
    RecordLocator,
)
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
from paper_insights.domain.validation import require_tuples


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


_COLLECTION_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field} must use UTC")


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

    def __post_init__(self) -> None:
        _require_utc(self.created_at, "paper creation timestamp")


@dataclass(frozen=True, slots=True)
class VersionObservation:
    observation_id: VersionObservationId
    paper_version_id: PaperVersionId
    observed: ObservedPaperVersion
    observed_at: datetime

    def __post_init__(self) -> None:
        _require_utc(self.observed_at, "observation timestamp")


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: ArtifactId
    paper_version_id: PaperVersionId
    version_observation_id: VersionObservationId | None
    sha256: Sha256
    kind: ArtifactKind

    def __post_init__(self) -> None:
        if self.kind is ArtifactKind.METADATA and self.version_observation_id is None:
            raise ValueError("metadata artifacts require an observation")


@dataclass(frozen=True, slots=True)
class PaperView:
    identity: PaperIdentity
    observations: tuple[VersionObservation, ...]
    artifacts: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        require_tuples(self, "observations", "artifacts")
        if not self.observations:
            raise ValueError("paper view requires at least one observation")
        versions = {item.paper_version_id for item in self.observations}
        if any(artifact.paper_version_id not in versions for artifact in self.artifacts):
            raise ValueError("paper artifact has no matching observation")


@dataclass(frozen=True, slots=True)
class RecordObservation:
    snapshot_id: SnapshotId
    record_ordinal: int
    observed: ObservedPaperVersion
    metadata_blob: MetadataBlobRef

    def __post_init__(self) -> None:
        if self.record_ordinal < 0:
            raise ValueError("record ordinal cannot be negative")
        if self.record_ordinal != self.observed.record_ordinal:
            raise ValueError("record ordinal differs from the observation")
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
    prepared: PreparedDiscovery
    pages: tuple[PreparedSnapshotAttachment, ...]

    def __post_init__(self) -> None:
        require_tuples(self, "pages")
        batch_pages = self.prepared.batch.pages
        if len(self.pages) != len(batch_pages):
            raise ValueError("attached pages differ from the prepared manifest")
        for ordinal, (attached, source) in enumerate(zip(self.pages, batch_pages, strict=True)):
            expected_records = tuple(
                SnapshotRecordAttachment(record.locator) for record in source.records
            )
            if (
                attached.page_ordinal != ordinal
                or attached.capture_id != source.capture_id
                or attached.blob.sha256 != source.payload_sha256
                or attached.blob.size_bytes != len(source.raw_payload)
                or attached.blob.media_type != source.media_type
                or attached.request_fingerprint != source.request_fingerprint
                or attached.retrieved_at != source.retrieved_at
                or attached.next_cursor != source.next_cursor
                or attached.records != expected_records
            ):
                raise ValueError("attached page differs from the prepared manifest")

    @property
    def source_id(self) -> SourceId:
        return self.prepared.batch.source_id

    @property
    def prepared_digest(self) -> Sha256:
        return self.prepared.digest

    @property
    def query_json(self) -> str:
        payload = {
            "query": self.prepared.batch.query.canonical_data(),
            "schema_version": "discovery-query-v1",
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @property
    def selected_locators(self) -> tuple[RecordLocator, ...]:
        return self.prepared.preview.selected_locators

    @property
    def selected_records(self) -> int:
        return len(self.selected_locators)


@dataclass(frozen=True, slots=True)
class IngestionRunRef:
    run_id: RunId
    revision: int

    def __post_init__(self) -> None:
        if self.revision < 0:
            raise ValueError("catalog revision cannot be negative")


@dataclass(frozen=True, slots=True)
class RecordIngestionItem:
    run_id: RunId
    record: RecordObservation


@dataclass(frozen=True, slots=True)
class IngestionItemRef:
    run_id: RunId
    record_ordinal: int
    outcome: IngestionOutcome

    def __post_init__(self) -> None:
        if self.record_ordinal < 0:
            raise ValueError("record ordinal cannot be negative")


@dataclass(frozen=True, slots=True)
class IngestionSummary:
    run_id: RunId
    counters: RunCounters


@dataclass(frozen=True, slots=True)
class CreateCollection:
    slug: str
    title: str

    def __post_init__(self) -> None:
        if not _COLLECTION_SLUG.fullmatch(self.slug) or not self.title.strip():
            raise ValueError("collection slug and title are required")


@dataclass(frozen=True, slots=True)
class RenameCollection:
    collection_id: CollectionId
    title: str

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("collection title is required")


@dataclass(frozen=True, slots=True)
class AddCollectionPaper:
    collection_id: CollectionId
    selector: PaperSelector
    note: str | None = None

    def __post_init__(self) -> None:
        if self.note is not None and not self.note.strip():
            raise ValueError("collection note cannot be blank")


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

    def __post_init__(self) -> None:
        if not _COLLECTION_SLUG.fullmatch(self.slug) or not self.title.strip():
            raise ValueError("collection slug and title are required")
        if self.paper_count < 0:
            raise ValueError("collection paper count cannot be negative")
        _require_utc(self.created_at, "collection creation timestamp")
        _require_utc(self.updated_at, "collection update timestamp")
        if self.updated_at < self.created_at:
            raise ValueError("collection update precedes creation")


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

    def __post_init__(self) -> None:
        if self.blob.sha256 != self.normalized_sha256:
            raise ValueError("metadata blob differs from its normalized digest")


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
        require_tuples(self, "records")
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

    def __post_init__(self) -> None:
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("blob size cannot be negative")
        if not self.exists and (self.valid or self.size_bytes is not None):
            raise ValueError("missing blob cannot be valid or have a size")
        if self.valid and not self.exists:
            raise ValueError("valid blob must exist")


class CitationFormat(str, Enum):
    BIBTEX = "bibtex"
    MARKDOWN = "markdown"
    CSL_JSON = "csl-json"


class CitationWarning(str, Enum):
    LITERAL_AUTHOR = "literal-author"
    MISSING_REQUIRED_FIELD = "missing-required-field"
    PARTIAL_DATE = "partial-date"
    PARTIAL_PROVENANCE = "partial-provenance"


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

    def __post_init__(self) -> None:
        observed = self.observation.observed
        if (
            observed.source_id != self.source_id
            or observed.source_item_id != self.source_item_id
            or observed.record_ordinal != self.record_ordinal
        ):
            raise ValueError("citation provenance is invalid")
        if not self.source_item_id or self.record_ordinal < 0:
            raise ValueError("citation provenance is invalid")
        _require_utc(self.retrieved_at, "citation retrieval timestamp")


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
    warnings: tuple[CitationWarning, ...]

    def __post_init__(self) -> None:
        require_tuples(self, "missing_fields", "warnings")
        if self.schema_version != "citation-v1":
            raise ValueError("unsupported citation schema")
        if not self.media_type or not self.source_item_id or self.record_ordinal < 0:
            raise ValueError("citation content or provenance is invalid")
        if self.missing_fields != tuple(sorted(set(self.missing_fields))):
            raise ValueError("missing citation fields must be sorted and unique")
        if any(not field.strip() for field in self.missing_fields):
            raise ValueError("missing citation fields cannot be blank")
        if any(not isinstance(warning, CitationWarning) for warning in self.warnings):
            raise ValueError("unsupported citation warning")
        warning_values = tuple(warning.value for warning in self.warnings)
        if warning_values != tuple(sorted(set(warning_values))):
            raise ValueError("citation warnings must be sorted and unique")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() != timedelta(0):
            raise ValueError("citation retrieval timestamp must use UTC")
