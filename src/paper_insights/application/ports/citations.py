from __future__ import annotations

from typing import Protocol

from paper_insights.domain.corpus import CitationFormat, CitationInput, CitationResult


class CitationRenderer(Protocol):
    def render(self, citation: CitationInput, format: CitationFormat) -> CitationResult: ...
