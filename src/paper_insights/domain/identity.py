from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from paper_insights.domain.identifiers import AuthorId, IdentityEventId, Sha256, SourceId


class IdentityDecisionKind(str, Enum):
    MERGE = "merge"
    SPLIT = "split"
    CONFIRM_LINKEDIN = "confirm_linkedin"


@dataclass(frozen=True, slots=True)
class IdentityQuery:
    author_id: AuthorId
    observed_name: str


@dataclass(frozen=True, slots=True)
class IdentityObservation:
    source_id: SourceId
    source_identifier: str
    observed_name: str
    payload_sha256: Sha256
    retrieved_at: datetime


@dataclass(frozen=True, slots=True)
class IdentityObservationBatch:
    source_id: SourceId
    observations: tuple[IdentityObservation, ...]


@dataclass(frozen=True, slots=True)
class IdentityObservationRef:
    source_id: SourceId
    source_identifier: str


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
        if not self.author_ids or not self.actor or self.expected_state_version < 0:
            raise ValueError("identity decision is incomplete")


@dataclass(frozen=True, slots=True)
class ReverseIdentityDecision:
    event_id: IdentityEventId
    actor: str
    reversed_at: datetime
    expected_state_version: int

    def __post_init__(self) -> None:
        if not self.actor or self.expected_state_version < 0:
            raise ValueError("identity reversal is incomplete")


@dataclass(frozen=True, slots=True)
class IdentityState:
    author_ids: tuple[AuthorId, ...]
    state_version: int
