from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from paper_insights.domain.identifiers import AuthorId, IdentityEventId, Sha256, SourceId
from paper_insights.domain.validation import require_tuples


class IdentityDecisionKind(StrEnum):
    MERGE = "merge"
    SPLIT = "split"
    CONFIRM_LINKEDIN = "confirm_linkedin"


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field} must use UTC")


@dataclass(frozen=True, slots=True)
class IdentityQuery:
    author_id: AuthorId
    observed_name: str

    def __post_init__(self) -> None:
        if not self.observed_name.strip():
            raise ValueError("observed author name is required")


@dataclass(frozen=True, slots=True)
class IdentityObservation:
    source_id: SourceId
    source_identifier: str
    observed_name: str
    payload_sha256: Sha256
    retrieved_at: datetime

    def __post_init__(self) -> None:
        if not self.source_identifier.strip() or not self.observed_name.strip():
            raise ValueError("identity observation is incomplete")
        _require_utc(self.retrieved_at, "identity retrieval timestamp")


@dataclass(frozen=True, slots=True)
class IdentityObservationBatch:
    source_id: SourceId
    observations: tuple[IdentityObservation, ...]

    def __post_init__(self) -> None:
        require_tuples(self, "observations")
        if any(item.source_id != self.source_id for item in self.observations):
            raise ValueError("identity observations belong to another source")


@dataclass(frozen=True, slots=True)
class IdentityObservationRef:
    source_id: SourceId
    source_identifier: str

    def __post_init__(self) -> None:
        if not self.source_identifier.strip():
            raise ValueError("identity source identifier is required")


@dataclass(frozen=True, slots=True)
class IdentityDecision:
    event_id: IdentityEventId
    kind: IdentityDecisionKind
    author_ids: tuple[AuthorId, ...]
    evidence: tuple[IdentityObservationRef, ...]
    actor: str
    decided_at: datetime
    expected_state_version: int

    def __post_init__(self) -> None:
        require_tuples(self, "author_ids", "evidence")
        if not self.author_ids or not self.actor.strip() or self.expected_state_version < 0:
            raise ValueError("identity decision is incomplete")
        if len(set(self.author_ids)) != len(self.author_ids):
            raise ValueError("identity decision authors must be unique")
        if not self.evidence:
            raise ValueError("identity decision requires evidence")
        _require_utc(self.decided_at, "identity decision timestamp")


@dataclass(frozen=True, slots=True)
class ReverseIdentityDecision:
    event_id: IdentityEventId
    actor: str
    reversed_at: datetime
    expected_state_version: int

    def __post_init__(self) -> None:
        if not self.actor.strip() or self.expected_state_version < 0:
            raise ValueError("identity reversal is incomplete")
        _require_utc(self.reversed_at, "identity reversal timestamp")


@dataclass(frozen=True, slots=True)
class IdentityState:
    author_ids: tuple[AuthorId, ...]
    state_version: int

    def __post_init__(self) -> None:
        require_tuples(self, "author_ids")
        if not self.author_ids or self.state_version < 0:
            raise ValueError("identity state is incomplete")
        if len(set(self.author_ids)) != len(self.author_ids):
            raise ValueError("identity state authors must be unique")
