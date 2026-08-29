from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from paper_insights.domain.corpus import ArtifactRef
from paper_insights.domain.identifiers import AnalysisId, PaperVersionId, PassageId, Sha256


class AnalysisState(str, Enum):
    RUNNING = "running"
    COMPLETE = "complete"
    INVALID = "invalid"
    TRUNCATED = "truncated"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class FullTextRequest:
    paper_version_id: PaperVersionId
    source_url: str
    policy_version: str


@dataclass(frozen=True, slots=True)
class FullTextAcquisition:
    artifact: ArtifactRef
    acquired_at: datetime


@dataclass(frozen=True, slots=True)
class VerifiedArtifact:
    artifact: ArtifactRef
    content: bytes


@dataclass(frozen=True, slots=True)
class ExtractedText:
    text: str
    source_artifact: ArtifactRef
    extractor_name: str
    extractor_version: str


@dataclass(frozen=True, slots=True)
class AnalysisCacheKey:
    paper_version_id: PaperVersionId
    artifact_sha256: Sha256
    passage_ids: tuple[PassageId, ...]
    chunk_schema_version: str
    prompt_version: str
    prompt_sha256: Sha256
    provider: str
    model: str
    parameters_json: str
    result_schema_version: str

    def __post_init__(self) -> None:
        required = (
            self.chunk_schema_version,
            self.prompt_version,
            self.provider,
            self.model,
            self.result_schema_version,
        )
        if not all(required) or not self.passage_ids:
            raise ValueError("analysis cache key is incomplete")
        try:
            parameters = json.loads(self.parameters_json)
        except json.JSONDecodeError as exc:
            raise ValueError("analysis parameters must be valid JSON") from exc
        canonical = json.dumps(
            parameters, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        if canonical != self.parameters_json:
            raise ValueError("analysis parameters must use canonical JSON")


@dataclass(frozen=True, slots=True)
class AnalysisPassage:
    passage_id: PassageId
    text: str

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("analysis passage text is required")


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    key: AnalysisCacheKey
    passages: tuple[AnalysisPassage, ...]

    def __post_init__(self) -> None:
        if tuple(passage.passage_id for passage in self.passages) != self.key.passage_ids:
            raise ValueError("analysis passages differ from the ordered cache key")


@dataclass(frozen=True, slots=True)
class AnalysisResponse:
    raw_payload: bytes
    stop_reason: str


@dataclass(frozen=True, slots=True)
class AnalysisAttempt:
    analysis_id: AnalysisId
    key: AnalysisCacheKey
    response: AnalysisResponse
    validation_state: AnalysisState


@dataclass(frozen=True, slots=True)
class AnalysisAttemptRef:
    analysis_id: AnalysisId
    validation_state: AnalysisState


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    analysis_id: AnalysisId
    key: AnalysisCacheKey
    claim_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PublishAnalysis:
    attempt: AnalysisAttemptRef
    evidence_passage_ids: tuple[PassageId, ...]
