from __future__ import annotations

from paper_insights.application.ports.clock import Clock
from paper_insights.application.ports.discovery import DiscoveryProvider
from paper_insights.domain.acquisition import MAX_PREVIEW_AGE, DiscoveryQuery, PreparedDiscovery


class PrepareDiscovery:
    def __init__(self, *, provider: DiscoveryProvider, clock: Clock) -> None:
        self._provider = provider
        self._clock = clock

    def prepare(self, query: DiscoveryQuery) -> PreparedDiscovery:
        batch = self._provider.discover(query)
        if batch.source_id != self._provider.source_id or batch.query != query:
            raise ValueError("provider batch differs from the discovery request")
        selected = tuple(
            record.locator
            for page in batch.pages
            for record in page.records
            if record.observation is not None
        )[: query.limit]
        prepared_at = self._clock.now()
        return PreparedDiscovery.prepare(
            batch=batch,
            selected_records=selected,
            prepared_at=prepared_at,
            expires_at=prepared_at + MAX_PREVIEW_AGE,
        )
