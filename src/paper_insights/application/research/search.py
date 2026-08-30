from __future__ import annotations

from dataclasses import dataclass

from paper_insights.application.ports.search import SearchIndexReader
from paper_insights.domain.identifiers import PassageId
from paper_insights.domain.retrieval import (
    PaperSearchQuery,
    PaperSearchResult,
    PassageSearchQuery,
    PassageSearchResult,
    PassageView,
)


@dataclass(frozen=True, slots=True)
class LocalSearch:
    reader: SearchIndexReader

    def search_papers(self, query: PaperSearchQuery) -> PaperSearchResult:
        return self.reader.search_papers(query)

    def search_passages(self, query: PassageSearchQuery) -> PassageSearchResult:
        return self.reader.search_passages(query)

    def get_passage(self, passage_id: PassageId) -> PassageView | None:
        return self.reader.get_passage(passage_id)
