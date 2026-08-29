from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from paper_insights.domain.acquisition import DiscoveryQuery
from paper_insights.domain.corpus import IngestionSummary
from paper_insights.domain.identifiers import RunId, SourceId, WatchlistId


_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class WatchlistSlug:
    value: str

    def __post_init__(self) -> None:
        if not _SLUG.fullmatch(self.value):
            raise ValueError("watchlist slug must be canonical")


@dataclass(frozen=True, slots=True)
class WatchlistState:
    watchlist_id: WatchlistId
    slug: WatchlistSlug
    source_id: SourceId
    query: DiscoveryQuery
    validated_cursor: str | None
    overlap_seconds: int
    enabled: bool
    state_version: int

    def __post_init__(self) -> None:
        if self.overlap_seconds < 0 or self.state_version < 0:
            raise ValueError("watchlist overlap and state version cannot be negative")


@dataclass(frozen=True, slots=True)
class CreateWatchlist:
    slug: WatchlistSlug
    source_id: SourceId
    query: DiscoveryQuery
    overlap_seconds: int = 0

    def __post_init__(self) -> None:
        if self.overlap_seconds < 0:
            raise ValueError("watchlist overlap cannot be negative")


@dataclass(frozen=True, slots=True)
class UpdateWatchlist:
    watchlist_id: WatchlistId
    expected_state_version: int
    query: DiscoveryQuery
    overlap_seconds: int
    enabled: bool

    def __post_init__(self) -> None:
        if self.expected_state_version < 0 or self.overlap_seconds < 0:
            raise ValueError("watchlist versions and overlap cannot be negative")


@dataclass(frozen=True, slots=True)
class FinalizeWatchlistRun:
    watchlist_id: WatchlistId
    ingestion_run_id: RunId
    expected_state_version: int
    candidate_cursor: str | None
    completed_at: datetime

    def __post_init__(self) -> None:
        if self.expected_state_version < 0:
            raise ValueError("watchlist state version cannot be negative")
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() != timedelta(0):
            raise ValueError("watchlist completion timestamp must use UTC")


@dataclass(frozen=True, slots=True)
class WatchlistRunResult:
    state: WatchlistState
    ingestion: IngestionSummary
