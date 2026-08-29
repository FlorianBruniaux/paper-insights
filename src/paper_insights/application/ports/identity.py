from __future__ import annotations

from types import TracebackType
from typing import Protocol

from paper_insights.domain.identifiers import SourceId
from paper_insights.domain.identity import (
    IdentityDecision,
    IdentityObservationBatch,
    IdentityObservationRef,
    IdentityQuery,
    IdentityState,
    ReverseIdentityDecision,
)


class IdentityProvider(Protocol):
    source_id: SourceId

    def observe(self, query: IdentityQuery) -> IdentityObservationBatch: ...


class IdentityUnitOfWork(Protocol):
    def __enter__(self) -> IdentityUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...

    def record_observations(
        self, batch: IdentityObservationBatch
    ) -> tuple[IdentityObservationRef, ...]: ...

    def apply(self, decision: IdentityDecision) -> IdentityState: ...

    def reverse(self, command: ReverseIdentityDecision) -> IdentityState: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class IdentityUnitOfWorkFactory(Protocol):
    def begin(self) -> IdentityUnitOfWork: ...
