from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from paper_insights.domain.identifiers import Sha256, SourceId


PREVIEW_SCHEMA_VERSION = "discovery-preview-v1"
PREPARED_SCHEMA_VERSION = "prepared-discovery-v1"
MAX_PREVIEW_AGE = timedelta(minutes=15)


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field} must use UTC")


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class DiscoveryQuery:
    text: str | None = None
    categories: tuple[str, ...] = ()
    authors: tuple[str, ...] = ()
    identifiers: tuple[str, ...] = ()
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int = 20
    cursor: str | None = None

    def __post_init__(self) -> None:
        if not any((self.text, self.categories, self.authors, self.identifiers)):
            raise ValueError("discovery query requires at least one selector")
        if not 1 <= self.limit <= 100:
            raise ValueError("discovery query limit must be between 1 and 100")
        if self.text is not None and not self.text.strip():
            raise ValueError("query text cannot be blank")
        if self.date_from is not None:
            _require_utc(self.date_from, "date_from")
        if self.date_to is not None:
            _require_utc(self.date_to, "date_to")
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("date_from must not exceed date_to")

    def canonical_data(self) -> dict[str, object]:
        return {
            "authors": list(self.authors),
            "categories": list(self.categories),
            "cursor": self.cursor,
            "date_from": _utc_text(self.date_from) if self.date_from else None,
            "date_to": _utc_text(self.date_to) if self.date_to else None,
            "identifiers": list(self.identifiers),
            "limit": self.limit,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class RecordLocator:
    page_ordinal: int
    record_ordinal: int
    source_item_id: str | None
    source_version_key: str | None
    raw_record_sha256: Sha256

    def __post_init__(self) -> None:
        if self.page_ordinal < 0 or self.record_ordinal < 0:
            raise ValueError("record locator ordinals must be non-negative")

    def canonical_data(self) -> dict[str, object]:
        return {
            "page_ordinal": self.page_ordinal,
            "raw_record_sha256": str(self.raw_record_sha256),
            "record_ordinal": self.record_ordinal,
            "source_item_id": self.source_item_id,
            "source_version_key": self.source_version_key,
        }


@dataclass(frozen=True, slots=True)
class ObservedPaperVersion:
    source_id: SourceId
    source_item_id: str
    source_version_key: str
    title: str
    abstract: str | None
    page_ordinal: int
    record_ordinal: int
    normalized_sha256: Sha256
    authors: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_item_id or not self.source_version_key or not self.title:
            raise ValueError("observed paper version requires source identity and title")
        if self.page_ordinal < 0 or self.record_ordinal < 0:
            raise ValueError("observation ordinals must be non-negative")


@dataclass(frozen=True, slots=True)
class DiscoveryRecord:
    locator: RecordLocator
    observation: ObservedPaperVersion | None

    def __post_init__(self) -> None:
        observation = self.observation
        if observation is None:
            return
        if (observation.page_ordinal, observation.record_ordinal) != (
            self.locator.page_ordinal,
            self.locator.record_ordinal,
        ):
            raise ValueError("record locator and observation ordinals differ")
        if observation.source_item_id != self.locator.source_item_id:
            raise ValueError("record locator and observation paper identifiers differ")
        if observation.source_version_key != self.locator.source_version_key:
            raise ValueError("record locator and observation version identifiers differ")


@dataclass(frozen=True, slots=True)
class DiscoveryPage:
    capture_id: UUID
    records: tuple[DiscoveryRecord, ...]
    raw_payload: bytes
    media_type: str
    retrieved_at: datetime
    request_fingerprint: Sha256
    next_cursor: str | None

    def __post_init__(self) -> None:
        if self.capture_id.version != 7:
            raise ValueError("capture ID must be UUIDv7")
        if not self.media_type:
            raise ValueError("media type is required")
        _require_utc(self.retrieved_at, "retrieved_at")

    @property
    def payload_sha256(self) -> Sha256:
        return Sha256(hashlib.sha256(self.raw_payload).hexdigest())


@dataclass(frozen=True, slots=True)
class DiscoveryIssue:
    code: str
    message: str
    page_ordinal: int | None = None
    record_ordinal: int | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryBatch:
    source_id: SourceId
    query: DiscoveryQuery
    pages: tuple[DiscoveryPage, ...]
    records: tuple[ObservedPaperVersion, ...]
    issues: tuple[DiscoveryIssue, ...]

    def __post_init__(self) -> None:
        flattened = tuple(
            record.observation
            for page in self.pages
            for record in page.records
            if record.observation is not None
        )
        if flattened != self.records:
            raise ValueError("batch records must equal ordered page observations")
        for page_ordinal, page in enumerate(self.pages):
            for record_ordinal, record in enumerate(page.records):
                if record.locator.page_ordinal != page_ordinal:
                    raise ValueError("record references the wrong page ordinal")
                if record.locator.record_ordinal != record_ordinal:
                    raise ValueError("record ordinal does not match page order")
        if any(observation.source_id != self.source_id for observation in self.records):
            raise ValueError("batch observations must belong to the batch source")


@dataclass(frozen=True, slots=True)
class DiscoveryPreview:
    schema_version: str
    source_id: SourceId
    query: DiscoveryQuery
    requested_records: int
    discovered_records: int
    selected_records: int
    selected_locators: tuple[RecordLocator, ...]
    issues: tuple[DiscoveryIssue, ...]
    prepared_at: datetime
    expires_at: datetime
    digest: Sha256

    def __post_init__(self) -> None:
        if self.schema_version != PREVIEW_SCHEMA_VERSION:
            raise ValueError("unsupported discovery preview schema")
        if min(self.requested_records, self.discovered_records, self.selected_records) < 0:
            raise ValueError("preview counts cannot be negative")
        if self.selected_records != len(self.selected_locators):
            raise ValueError("preview selected count differs from locators")
        _require_utc(self.prepared_at, "prepared_at")
        _require_utc(self.expires_at, "expires_at")


def _validate_selected_records(
    batch: DiscoveryBatch, selected_records: tuple[RecordLocator, ...]
) -> None:
    ordered = tuple(record.locator for page in batch.pages for record in page.records)
    if len(set(selected_records)) != len(selected_records):
        raise ValueError("selected records cannot contain duplicates")
    positions = {locator: position for position, locator in enumerate(ordered)}
    if any(locator not in positions for locator in selected_records):
        raise ValueError("selected record is not present in the batch")
    selected_positions = tuple(positions[locator] for locator in selected_records)
    if selected_positions != tuple(sorted(selected_positions)):
        raise ValueError("selected records must preserve page and record order")


def prepared_discovery_digest(
    batch: DiscoveryBatch, selected_records: tuple[RecordLocator, ...]
) -> Sha256:
    payload = {
        "pages": [
            {
                "capture_id": str(page.capture_id),
                "page_ordinal": ordinal,
                "request_fingerprint": str(page.request_fingerprint),
                "retrieved_at": _utc_text(page.retrieved_at),
                "sha256": str(page.payload_sha256),
            }
            for ordinal, page in enumerate(batch.pages)
        ],
        "query": batch.query.canonical_data(),
        "schema_version": PREPARED_SCHEMA_VERSION,
        "selected_records": [record.canonical_data() for record in selected_records],
        "source_id": str(batch.source_id),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return Sha256(hashlib.sha256(canonical.encode()).hexdigest())


@dataclass(frozen=True, slots=True)
class PreparedDiscovery:
    batch: DiscoveryBatch
    preview: DiscoveryPreview
    digest: Sha256
    prepared_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _require_utc(self.prepared_at, "prepared_at")
        _require_utc(self.expires_at, "expires_at")
        if not self.prepared_at < self.expires_at <= self.prepared_at + MAX_PREVIEW_AGE:
            raise ValueError("prepared discovery expiry must be within 15 minutes")
        if self.preview.source_id != self.batch.source_id or self.preview.query != self.batch.query:
            raise ValueError("preview source or query differs from batch")
        if self.preview.schema_version != PREVIEW_SCHEMA_VERSION:
            raise ValueError("unsupported discovery preview schema")
        if self.preview.requested_records != self.batch.query.limit:
            raise ValueError("preview requested count differs from query limit")
        if self.preview.discovered_records != len(self.batch.records):
            raise ValueError("preview discovered count differs from batch")
        if self.preview.selected_records != len(self.preview.selected_locators):
            raise ValueError("preview selected count differs from locators")
        if (
            self.preview.prepared_at != self.prepared_at
            or self.preview.expires_at != self.expires_at
        ):
            raise ValueError("preview timestamps differ from prepared discovery")
        _validate_selected_records(self.batch, self.preview.selected_locators)
        expected = prepared_discovery_digest(self.batch, self.preview.selected_locators)
        if self.digest != expected or self.preview.digest != expected:
            raise ValueError("prepared discovery digest mismatch")

    @classmethod
    def prepare(
        cls,
        *,
        batch: DiscoveryBatch,
        selected_records: tuple[RecordLocator, ...],
        prepared_at: datetime,
        expires_at: datetime,
    ) -> PreparedDiscovery:
        _validate_selected_records(batch, selected_records)
        digest = prepared_discovery_digest(batch, selected_records)
        preview = DiscoveryPreview(
            schema_version=PREVIEW_SCHEMA_VERSION,
            source_id=batch.source_id,
            query=batch.query,
            requested_records=batch.query.limit,
            discovered_records=len(batch.records),
            selected_records=len(selected_records),
            selected_locators=selected_records,
            issues=batch.issues,
            prepared_at=prepared_at,
            expires_at=expires_at,
            digest=digest,
        )
        return cls(
            batch=batch,
            preview=preview,
            digest=digest,
            prepared_at=prepared_at,
            expires_at=expires_at,
        )
