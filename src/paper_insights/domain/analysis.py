from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from paper_insights.domain.corpus import ArtifactRef
from paper_insights.domain.identifiers import AnalysisId, PaperVersionId, PassageId, Sha256


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
    prompt_sha256: Sha256
    provider: str
    model: str
    parameters_json: str
    result_schema_version: str


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    key: AnalysisCacheKey
    passages: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnalysisResponse:
    raw_payload: bytes
    stop_reason: str


@dataclass(frozen=True, slots=True)
class AnalysisAttempt:
    analysis_id: AnalysisId
    key: AnalysisCacheKey
    response: AnalysisResponse
    validation_state: str


@dataclass(frozen=True, slots=True)
class AnalysisAttemptRef:
    analysis_id: AnalysisId
    validation_state: str


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    analysis_id: AnalysisId
    key: AnalysisCacheKey
    claim_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PublishAnalysis:
    attempt: AnalysisAttemptRef
    evidence_passage_ids: tuple[PassageId, ...]
