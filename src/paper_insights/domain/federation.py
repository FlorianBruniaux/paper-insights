from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from paper_insights.domain.identifiers import Sha256
from paper_insights.domain.retrieval import CoverageStatus
from paper_insights.domain.validation import require_tuples

_CORPUS_ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


@dataclass(frozen=True, slots=True)
class CorpusId:
    value: str

    def __post_init__(self) -> None:
        if not _CORPUS_ID.fullmatch(self.value):
            raise ValueError("corpus ID must be canonical")


class SourceType(StrEnum):
    PAPER = "paper"
    VIDEO = "video"
    REPOSITORY = "repository"


@dataclass(frozen=True, slots=True)
class CorpusCapabilities:
    source_types: tuple[SourceType, ...]
    supports_passages: bool
    supports_citations: bool

    def __post_init__(self) -> None:
        require_tuples(self, "source_types")
        if not self.source_types or len(set(self.source_types)) != len(self.source_types):
            raise ValueError("corpus capabilities require unique source types")


@dataclass(frozen=True, slots=True)
class FederatedSearchQuery:
    query: str
    limit_per_corpus: int

    def __post_init__(self) -> None:
        if not self.query.strip() or not 1 <= self.limit_per_corpus <= 50:
            raise ValueError("invalid federated search query")


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    corpus_id: CorpusId
    native_id: str

    def __post_init__(self) -> None:
        if not self.native_id.strip():
            raise ValueError("native evidence ID is required")


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    ref: EvidenceRef
    source_type: SourceType
    content: str
    sha256: Sha256

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("evidence content is required")
        actual = Sha256(hashlib.sha256(self.content.encode()).hexdigest())
        if actual != self.sha256:
            raise ValueError("evidence content differs from its digest")


@dataclass(frozen=True, slots=True)
class NativeCorpusHit:
    native_id: str
    source_type: SourceType
    rank: int
    native_score: float | None
    title: str

    def __post_init__(self) -> None:
        if not self.native_id.strip() or not self.title.strip() or self.rank < 1:
            raise ValueError("native corpus hit is incomplete")


@dataclass(frozen=True, slots=True)
class NativeCorpusResult:
    corpus_id: CorpusId
    hits: tuple[NativeCorpusHit, ...]
    coverage: CoverageStatus
    errors: tuple[str, ...]

    def __post_init__(self) -> None:
        require_tuples(self, "hits", "errors")
        ranks = tuple(hit.rank for hit in self.hits)
        if ranks != tuple(range(1, len(self.hits) + 1)):
            raise ValueError("native corpus hit ranks must be ordered")
        if any(not error.strip() for error in self.errors):
            raise ValueError("federated errors cannot be blank")
        if self.coverage is CoverageStatus.COMPLETE and self.errors:
            raise ValueError("complete federation coverage cannot contain errors")


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    items: tuple[EvidenceItem, ...]
    manifest_schema_version: str

    def __post_init__(self) -> None:
        require_tuples(self, "items")
        if self.manifest_schema_version != "evidence-bundle-v1" or not self.items:
            raise ValueError("evidence bundle schema or items are invalid")
        refs = tuple(item.ref for item in self.items)
        if len(set(refs)) != len(refs):
            raise ValueError("evidence bundle items must be unique")


@dataclass(frozen=True, slots=True)
class EvidenceBundleReceipt:
    path: Path
    sha256: Sha256
    item_count: int

    def __post_init__(self) -> None:
        if not self.path.is_absolute() or self.item_count < 0:
            raise ValueError("evidence bundle receipt path or count is invalid")
