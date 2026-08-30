from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from paper_insights.domain.identifiers import (
    CollectionId,
    PaperId,
    PaperVersionId,
    PassageId,
    Sha256,
    SourceId,
    VersionObservationId,
)
from paper_insights.domain.validation import require_tuples


class _Ranked(Protocol):
    @property
    def rank(self) -> int: ...


@dataclass(frozen=True, slots=True, order=True)
class CatalogRevision:
    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("catalog revision cannot be negative")


class CoverageStatus(StrEnum):
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
        if _normalized_text(self.normalized_text) != self.normalized_text:
            raise ValueError("passage text must already be normalized")
        if self.end_offset - self.start_offset != len(self.normalized_text):
            raise ValueError("passage offsets must span the normalized text")


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
    source_id: SourceId
    title: str
    abstract: str | None
    metadata_artifact_sha256: Sha256
    authors: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    language: str | None = None
    submitted_at: datetime | None = None
    collection_ids: tuple[CollectionId, ...] = ()
    collection_slugs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_tuples(
            self,
            "authors",
            "categories",
            "collection_ids",
            "collection_slugs",
        )
        if not self.title.strip():
            raise ValueError("index document title is required")
        if any(not value.strip() for value in (*self.authors, *self.categories)):
            raise ValueError("index document author and category values cannot be blank")
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("index document categories must be unique")
        if self.language is not None and not self.language.strip():
            raise ValueError("index document language cannot be blank")
        if self.submitted_at is not None and self.submitted_at.utcoffset() != timedelta(0):
            raise ValueError("index document submitted_at must use UTC")
        if len(set(self.collection_ids)) != len(self.collection_ids):
            raise ValueError("index document collection IDs must be unique")
        if any(not value.strip() for value in self.collection_slugs):
            raise ValueError("index document collection slugs cannot be blank")
        if len(set(self.collection_slugs)) != len(self.collection_slugs):
            raise ValueError("index document collection slugs must be unique")
        if len(self.collection_ids) != len(self.collection_slugs):
            raise ValueError("index document collection IDs and slugs must have equal cardinality")


@dataclass(frozen=True, slots=True)
class IndexBuildRequest:
    documents: tuple[IndexDocument, ...]
    catalog_revision: CatalogRevision
    chunk_schema_version: str

    def __post_init__(self) -> None:
        require_tuples(self, "documents")
        if not self.chunk_schema_version:
            raise ValueError("chunk schema version is required")
        identities = tuple(document.paper_version_id for document in self.documents)
        if len(set(identities)) != len(identities):
            raise ValueError("index documents cannot duplicate paper versions")


@dataclass(frozen=True, slots=True)
class IndexReceipt:
    index_schema_version: str
    chunk_schema_version: str
    generation: int
    catalog_revision: CatalogRevision
    document_count: int
    passage_count: int
    content_sha256: Sha256

    def __post_init__(self) -> None:
        if not self.index_schema_version or not self.chunk_schema_version:
            raise ValueError("index receipt schema versions are required")
        if min(self.generation, self.document_count, self.passage_count) < 0:
            raise ValueError("index receipt counts cannot be negative")


@dataclass(frozen=True, slots=True)
class IndexCandidate:
    path: Path
    catalog_revision: CatalogRevision
    generation: int
    content_sha256: Sha256
    receipt: IndexReceipt

    def __post_init__(self) -> None:
        if not self.path.is_absolute() or self.generation < 0:
            raise ValueError("index candidate path or generation is invalid")
        if (
            self.receipt.catalog_revision != self.catalog_revision
            or self.receipt.generation != self.generation
            or self.receipt.content_sha256 != self.content_sha256
        ):
            raise ValueError("index candidate differs from its receipt")


@dataclass(frozen=True, slots=True)
class PublishedIndex:
    path: Path
    catalog_revision: CatalogRevision
    generation: int

    def __post_init__(self) -> None:
        if not self.path.is_absolute() or self.generation < 0:
            raise ValueError("published index path or generation is invalid")


@dataclass(frozen=True, slots=True)
class SearchFilters:
    source_id: SourceId | None = None
    category: str | None = None
    author: str | None = None
    language: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    collection: str | None = None

    def __post_init__(self) -> None:
        for text_value in (self.category, self.author, self.language, self.collection):
            if text_value is not None and not text_value.strip():
                raise ValueError("search filter values cannot be blank")
        for date_value in (self.date_from, self.date_to):
            if date_value is not None and date_value.utcoffset() != timedelta(0):
                raise ValueError("search filter dates must use UTC")
        if self.date_from is not None and self.date_to is not None:
            if self.date_from > self.date_to:
                raise ValueError("search date range is inverted")


@dataclass(frozen=True, slots=True)
class PaperSearchQuery:
    query: str
    filters: SearchFilters = SearchFilters()
    limit: int = 10

    def __post_init__(self) -> None:
        if not 1 <= len(self.query) <= 500 or not self.query.strip() or not 1 <= self.limit <= 50:
            raise ValueError("invalid paper search query")


@dataclass(frozen=True, slots=True)
class PassageSearchQuery:
    query: str
    filters: SearchFilters = SearchFilters()
    limit: int = 10

    def __post_init__(self) -> None:
        if not 1 <= len(self.query) <= 500 or not self.query.strip() or not 1 <= self.limit <= 50:
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

    def __post_init__(self) -> None:
        if self.rank < 1 or not self.title:
            raise ValueError("paper search hit rank and title are required")


@dataclass(frozen=True, slots=True)
class PassageView:
    passage_id: PassageId
    identity: PassageIdentity
    paper_id: PaperId
    version_observation_id: VersionObservationId
    text: str

    def __post_init__(self) -> None:
        if self.passage_id != passage_id(self.identity):
            raise ValueError("passage ID differs from its deterministic identity")
        if self.text != self.identity.normalized_text:
            raise ValueError("passage text differs from its deterministic identity")


@dataclass(frozen=True, slots=True)
class PassageSearchHit:
    passage: PassageView
    rank: int
    bm25_score: float
    excerpt: str

    def __post_init__(self) -> None:
        if self.rank < 1:
            raise ValueError("passage search hit rank must be positive")


def _validate_result(
    hits: tuple[_Ranked, ...],
    returned: int,
    available: int | None,
    truncated: bool,
    applied_limit: int,
) -> None:
    if returned != len(hits):
        raise ValueError("returned must equal the number of hits")
    if available is not None and available < returned:
        raise ValueError("available cannot be less than returned")
    if truncated and available is not None and available <= returned:
        raise ValueError("truncated results require undisclosed available hits")
    if not truncated and available is not None and available > returned:
        raise ValueError("unreturned available hits require truncation")
    if returned > applied_limit:
        raise ValueError("returned hits exceed the applied limit")
    ranks = tuple(hit.rank for hit in hits)
    if ranks != tuple(range(1, returned + 1)):
        raise ValueError("result ranks must be positive, unique, and ordered")


@dataclass(frozen=True, slots=True)
class PaperSearchResult:
    hits: tuple[PaperSearchHit, ...]
    coverage: CoverageStatus
    catalog_revision: CatalogRevision
    index_revision: CatalogRevision
    truncated: bool
    returned: int
    available: int | None
    applied_limit: int

    def __post_init__(self) -> None:
        require_tuples(self, "hits")
        if not 1 <= self.applied_limit <= 50:
            raise ValueError("invalid applied paper-search limit")
        _validate_result(
            self.hits,
            self.returned,
            self.available,
            self.truncated,
            self.applied_limit,
        )
        if (
            self.coverage is CoverageStatus.COMPLETE
            and self.catalog_revision != self.index_revision
        ):
            raise ValueError("complete coverage requires matching revisions")
        if self.coverage is CoverageStatus.UNAVAILABLE and self.hits:
            raise ValueError("unavailable coverage cannot contain hits")


@dataclass(frozen=True, slots=True)
class PassageSearchResult:
    hits: tuple[PassageSearchHit, ...]
    coverage: CoverageStatus
    catalog_revision: CatalogRevision
    index_revision: CatalogRevision
    truncated: bool
    returned: int
    available: int | None
    applied_limit: int

    def __post_init__(self) -> None:
        require_tuples(self, "hits")
        if not 1 <= self.applied_limit <= 50:
            raise ValueError("invalid applied passage-search limit")
        _validate_result(
            self.hits,
            self.returned,
            self.available,
            self.truncated,
            self.applied_limit,
        )
        if (
            self.coverage is CoverageStatus.COMPLETE
            and self.catalog_revision != self.index_revision
        ):
            raise ValueError("complete coverage requires matching revisions")
        if self.coverage is CoverageStatus.UNAVAILABLE and self.hits:
            raise ValueError("unavailable coverage cannot contain hits")
