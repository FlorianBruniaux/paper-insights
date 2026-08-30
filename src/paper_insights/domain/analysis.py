from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from urllib.parse import urlsplit

from paper_insights.domain.corpus import ArtifactRef
from paper_insights.domain.identifiers import AnalysisId, PaperVersionId, PassageId, Sha256
from paper_insights.domain.validation import require_tuples


class AnalysisState(StrEnum):
    RUNNING = "running"
    COMPLETE = "complete"
    INVALID = "invalid"
    TRUNCATED = "truncated"
    FAILED = "failed"


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field} must use UTC")


@dataclass(frozen=True, slots=True)
class FullTextRequest:
    paper_version_id: PaperVersionId
    source_url: str
    policy_version: str

    def __post_init__(self) -> None:
        parsed = urlsplit(self.source_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("full-text source URL must use HTTPS with a host")
        if not self.policy_version.strip():
            raise ValueError("full-text policy version is required")


@dataclass(frozen=True, slots=True)
class FullTextAcquisition:
    artifact: ArtifactRef
    acquired_at: datetime

    def __post_init__(self) -> None:
        _require_utc(self.acquired_at, "full-text acquisition timestamp")


@dataclass(frozen=True, slots=True)
class VerifiedArtifact:
    artifact: ArtifactRef
    content: bytes

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("verified artifact content is required")
        if Sha256(hashlib.sha256(self.content).hexdigest()) != self.artifact.sha256:
            raise ValueError("verified artifact content differs from its digest")


@dataclass(frozen=True, slots=True)
class ExtractedText:
    text: str
    source_artifact: ArtifactRef
    extractor_name: str
    extractor_version: str

    def __post_init__(self) -> None:
        if not self.text or not self.extractor_name or not self.extractor_version:
            raise ValueError("extracted text and extractor identity are required")


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
        require_tuples(self, "passage_ids")
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
        if not isinstance(parameters, dict):
            raise ValueError("analysis parameters must be a JSON object")
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
        require_tuples(self, "passages")
        if tuple(passage.passage_id for passage in self.passages) != self.key.passage_ids:
            raise ValueError("analysis passages differ from the ordered cache key")


@dataclass(frozen=True, slots=True)
class AnalysisResponse:
    raw_payload: bytes
    stop_reason: str

    def __post_init__(self) -> None:
        if not self.raw_payload or not self.stop_reason.strip():
            raise ValueError("analysis response payload and stop reason are required")


@dataclass(frozen=True, slots=True)
class AnalysisAttempt:
    analysis_id: AnalysisId
    key: AnalysisCacheKey
    response: AnalysisResponse
    validation_state: AnalysisState

    def __post_init__(self) -> None:
        if self.validation_state is AnalysisState.RUNNING:
            raise ValueError("recorded analysis response cannot remain running")


@dataclass(frozen=True, slots=True)
class AnalysisAttemptRef:
    analysis_id: AnalysisId
    validation_state: AnalysisState

    def __post_init__(self) -> None:
        if self.validation_state is AnalysisState.RUNNING:
            raise ValueError("recorded analysis reference cannot remain running")


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    analysis_id: AnalysisId
    key: AnalysisCacheKey
    claim_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        require_tuples(self, "claim_ids")
        if not self.claim_ids or any(not claim.strip() for claim in self.claim_ids):
            raise ValueError("analysis result requires claim identifiers")
        if len(set(self.claim_ids)) != len(self.claim_ids):
            raise ValueError("analysis claim identifiers must be unique")


@dataclass(frozen=True, slots=True)
class PublishAnalysis:
    attempt: AnalysisAttemptRef
    evidence_passage_ids: tuple[PassageId, ...]

    def __post_init__(self) -> None:
        require_tuples(self, "evidence_passage_ids")
        if self.attempt.validation_state is not AnalysisState.COMPLETE:
            raise ValueError("only a complete analysis attempt can be published")
        if not self.evidence_passage_ids:
            raise ValueError("published analysis requires evidence passages")
        if len(set(self.evidence_passage_ids)) != len(self.evidence_passage_ids):
            raise ValueError("analysis evidence passages must be unique")
