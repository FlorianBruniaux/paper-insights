from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from paper_insights.domain.identifiers import Sha256
from paper_insights.domain.retrieval import CoverageStatus


_CORPUS_ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


@dataclass(frozen=True, slots=True)
class CorpusId:
    value: str

    def __post_init__(self) -> None:
        if not _CORPUS_ID.fullmatch(self.value):
            raise ValueError("corpus ID must be canonical")


class SourceType(str, Enum):
    PAPER = "paper"
    VIDEO = "video"
    REPOSITORY = "repository"


@dataclass(frozen=True, slots=True)
class CorpusCapabilities:
    source_types: tuple[SourceType, ...]
    supports_passages: bool
    supports_citations: bool


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


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    ref: EvidenceRef
    source_type: SourceType
    content: str
    sha256: Sha256


@dataclass(frozen=True, slots=True)
class NativeCorpusHit:
    native_id: str
    source_type: SourceType
    rank: int
    native_score: float | None
    title: str


@dataclass(frozen=True, slots=True)
class NativeCorpusResult:
    corpus_id: CorpusId
    hits: tuple[NativeCorpusHit, ...]
    coverage: CoverageStatus
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    items: tuple[EvidenceItem, ...]
    manifest_schema_version: str


@dataclass(frozen=True, slots=True)
class EvidenceBundleReceipt:
    path: Path
    sha256: Sha256
    item_count: int
