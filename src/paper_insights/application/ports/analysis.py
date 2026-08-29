from __future__ import annotations

from types import TracebackType
from typing import Protocol

from paper_insights.domain.analysis import (
    AnalysisAttempt,
    AnalysisAttemptRef,
    AnalysisCacheKey,
    AnalysisRequest,
    AnalysisResponse,
    AnalysisResult,
    ExtractedText,
    FullTextAcquisition,
    FullTextRequest,
    PublishAnalysis,
    VerifiedArtifact,
)


class FullTextProvider(Protocol):
    def acquire(self, request: FullTextRequest) -> FullTextAcquisition: ...


class TextExtractor(Protocol):
    name: str
    version: str

    def extract(self, artifact: VerifiedArtifact) -> ExtractedText: ...


class AnalysisBackend(Protocol):
    provider: str
    model: str

    def analyze(self, request: AnalysisRequest) -> AnalysisResponse: ...


class AnalysisUnitOfWork(Protocol):
    def __enter__(self) -> AnalysisUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...

    def find_complete(self, key: AnalysisCacheKey) -> AnalysisResult | None: ...

    def record_attempt(self, attempt: AnalysisAttempt) -> AnalysisAttemptRef: ...

    def publish_complete(self, command: PublishAnalysis) -> AnalysisResult: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class AnalysisUnitOfWorkFactory(Protocol):
    def begin(self) -> AnalysisUnitOfWork: ...
