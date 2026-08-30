from __future__ import annotations

from typing import Protocol

from paper_insights.application.ports.catalog import CatalogRevisionLease
from paper_insights.domain.identifiers import PassageId
from paper_insights.domain.retrieval import (
    IndexBuildRequest,
    IndexCandidate,
    PaperSearchQuery,
    PaperSearchResult,
    PassageSearchQuery,
    PassageSearchResult,
    PassageView,
    PublishedIndex,
)


class SearchIndexBuilder(Protocol):
    def build_candidate(self, request: IndexBuildRequest) -> IndexCandidate: ...

    def publish(self, candidate: IndexCandidate, lease: CatalogRevisionLease) -> PublishedIndex: ...

    def discard(self, candidate: IndexCandidate) -> None: ...


class SearchIndexReader(Protocol):
    def search_papers(self, query: PaperSearchQuery) -> PaperSearchResult: ...

    def search_passages(self, query: PassageSearchQuery) -> PassageSearchResult: ...

    def get_passage(self, passage_id: PassageId) -> PassageView | None: ...
