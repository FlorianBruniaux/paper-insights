from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from paper_insights.domain.identifiers import (
    PaperId,
    PaperVersionId,
    PassageId,
    Sha256,
    VersionObservationId,
)


@dataclass(frozen=True, slots=True, order=True)
class CatalogRevision:
    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("catalog revision cannot be negative")


class CoverageStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PassageIdentity:
    paper_version_id: PaperVersionId
    artifact_sha256: Sha256
    chunk_schema_version: str
    section: str | None
    ordinal: int
    normalized_text: str
    start_offset: int
    end_offset: int

    def __post_init__(self) -> None:
        if not self.chunk_schema_version:
            raise ValueError("chunk schema version is required")
        if self.ordinal < 0 or self.start_offset < 0 or self.end_offset < self.start_offset:
            raise ValueError("invalid passage ordinal or offsets")


def _normalized_text(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


def passage_id(identity: PassageIdentity) -> PassageId:
    payload = {
        "artifact_sha256": str(identity.artifact_sha256),
        "chunk_schema_version": identity.chunk_schema_version,
        "end_offset": identity.end_offset,
        "normalized_text": _normalized_text(identity.normalized_text),
        "ordinal": identity.ordinal,
        "paper_version_id": str(identity.paper_version_id),
        "section": identity.section,
        "start_offset": identity.start_offset,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return PassageId(hashlib.sha256(canonical.encode()).hexdigest())


@dataclass(frozen=True, slots=True)
class IndexDocument:
    paper_id: PaperId
    paper_version_id: PaperVersionId
    version_observation_id: VersionObservationId
    title: str
    abstract: str | None
    metadata_artifact_sha256: Sha256


@dataclass(frozen=True, slots=True)
class IndexBuildRequest:
    documents: tuple[IndexDocument, ...]
    catalog_revision: CatalogRevision
    chunk_schema_version: str


@dataclass(frozen=True, slots=True)
class IndexCandidate:
    path: Path
    catalog_revision: CatalogRevision
    generation: int
    content_sha256: Sha256


@dataclass(frozen=True, slots=True)
class PublishedIndex:
    path: Path
    catalog_revision: CatalogRevision
    generation: int


@dataclass(frozen=True, slots=True)
class PaperSearchQuery:
    query: str
    limit: int = 10

    def __post_init__(self) -> None:
        if not 1 <= len(self.query) <= 500 or not 1 <= self.limit <= 50:
            raise ValueError("invalid paper search query")


@dataclass(frozen=True, slots=True)
class PassageSearchQuery:
    query: str
    limit: int = 10

    def __post_init__(self) -> None:
        if not 1 <= len(self.query) <= 500 or not 1 <= self.limit <= 50:
            raise ValueError("invalid passage search query")


@dataclass(frozen=True, slots=True)
class PaperSearchHit:
    paper_id: PaperId
    paper_version_id: PaperVersionId
    version_observation_id: VersionObservationId
    title: str
    rank: int
    bm25_score: float
    artifact_sha256: Sha256


@dataclass(frozen=True, slots=True)
class PassageView:
    passage_id: PassageId
    identity: PassageIdentity
    paper_id: PaperId
    version_observation_id: VersionObservationId
    text: str


@dataclass(frozen=True, slots=True)
class PassageSearchHit:
    passage: PassageView
    rank: int
    bm25_score: float
    excerpt: str


def _validate_result(
    hits: tuple[object, ...], returned: int, available: int | None, truncated: bool
) -> None:
    if returned != len(hits):
        raise ValueError("returned must equal the number of hits")
    if available is not None and available < returned:
        raise ValueError("available cannot be less than returned")
    if truncated and available is not None and available <= returned:
        raise ValueError("truncated results require undisclosed available hits")


@dataclass(frozen=True, slots=True)
class PaperSearchResult:
    hits: tuple[PaperSearchHit, ...]
    coverage: CoverageStatus
    catalog_revision: CatalogRevision
    index_revision: CatalogRevision
    truncated: bool
    returned: int
    available: int | None

    def __post_init__(self) -> None:
        _validate_result(self.hits, self.returned, self.available, self.truncated)


@dataclass(frozen=True, slots=True)
class PassageSearchResult:
    hits: tuple[PassageSearchHit, ...]
    coverage: CoverageStatus
    catalog_revision: CatalogRevision
    index_revision: CatalogRevision
    truncated: bool
    returned: int
    available: int | None

    def __post_init__(self) -> None:
        _validate_result(self.hits, self.returned, self.available, self.truncated)
