from __future__ import annotations

from typing import Protocol

from paper_insights.domain.acquisition import DiscoveryBatch, DiscoveryQuery
from paper_insights.domain.identifiers import SourceId


class DiscoveryProvider(Protocol):
    source_id: SourceId

    def discover(self, query: DiscoveryQuery) -> DiscoveryBatch: ...
