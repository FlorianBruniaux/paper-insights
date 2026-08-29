from __future__ import annotations

from types import TracebackType
from typing import Protocol

from paper_insights.domain.monitoring import (
    CreateWatchlist,
    FinalizeWatchlistRun,
    UpdateWatchlist,
    WatchlistRunResult,
    WatchlistSlug,
    WatchlistState,
)


class WatchlistUnitOfWork(Protocol):
    def __enter__(self) -> WatchlistUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...

    def create(self, command: CreateWatchlist) -> WatchlistState: ...

    def update(self, command: UpdateWatchlist) -> WatchlistState: ...

    def load(self, slug: WatchlistSlug) -> WatchlistState | None: ...

    def finalize(self, command: FinalizeWatchlistRun) -> WatchlistRunResult: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class WatchlistUnitOfWorkFactory(Protocol):
    def begin(self) -> WatchlistUnitOfWork: ...
