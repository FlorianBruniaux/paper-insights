from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID

import pytest

from paper_insights.application.research.citations import (
    AmbiguousCitationMetadataError,
    CitationNotFoundError,
    CitationService,
    SourceBackedCitationRenderer,
)
from paper_insights.domain.acquisition import (
    IdentifierScope,
    ObservedAuthor,
    ObservedIdentifier,
    ObservedPaperVersion,
)
from paper_insights.domain.corpus import (
    CitationFormat,
    CitationInput,
    CitationSelector,
    VersionObservation,
)
from paper_insights.domain.identifiers import (
    PaperId,
    PaperSelector,
    PaperVersionId,
    Sha256,
    SnapshotId,
    SourceId,
    VersionObservationId,
)
from paper_insights.domain.retrieval import CatalogRevision

PAPER_ID = PaperId(UUID("01890f3d-0000-7000-8000-000000000001"))
VERSION_ID = PaperVersionId(UUID("01890f3d-0000-7000-8000-000000000002"))
OBSERVATION_ID = VersionObservationId(UUID("01890f3d-0000-7000-8000-000000000003"))
SNAPSHOT_ID = SnapshotId(UUID("01890f3d-0000-7000-8000-000000000004"))
RETRIEVED_AT = datetime(2026, 8, 29, 7, 30, tzinfo=UTC)
SUBMITTED_AT = datetime(2026, 8, 28, 11, 45, tzinfo=UTC)


def make_citation_input(
    *,
    title: str = "Agents & {Evidence} \\ Systems_",
    authors: tuple[ObservedAuthor, ...] = (
        ObservedAuthor(raw_name="Ada Lovelace", given_name="Ada", family_name="Lovelace"),
        ObservedAuthor(raw_name="Research Group"),
    ),
    identifiers: tuple[ObservedIdentifier, ...] = (
        ObservedIdentifier(
            scheme="doi",
            canonical_value="10.1000/agents_evidence",
            scope=IdentifierScope.VERSION,
        ),
    ),
    source_url: str | None = "https://arxiv.org/abs/2608.01234v2",
    submitted_at: datetime | None = SUBMITTED_AT,
) -> CitationInput:
    observed = ObservedPaperVersion(
        source_id=SourceId("arxiv"),
        source_item_id="2608.01234",
        source_version_key="2608.01234v2",
        title=title,
        abstract="Observed abstract",
        page_ordinal=0,
        record_ordinal=1,
        normalized_sha256=Sha256("a" * 64),
        authors=authors,
        identifiers=identifiers,
        source_url=source_url,
        submitted_at=submitted_at,
    )
    return CitationInput(
        paper_id=PAPER_ID,
        observation=VersionObservation(
            observation_id=OBSERVATION_ID,
            paper_version_id=VERSION_ID,
            observed=observed,
            observed_at=RETRIEVED_AT,
        ),
        source_id=SourceId("arxiv"),
        source_item_id="2608.01234",
        snapshot_id=SNAPSHOT_ID,
        record_ordinal=1,
        retrieved_at=RETRIEVED_AT,
    )


class ExactSnapshot:
    revision = CatalogRevision(9)

    def __init__(self, citations: dict[CitationSelector, CitationInput]) -> None:
        self._citations = citations

    def __enter__(self) -> ExactSnapshot:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc_type, exc, traceback
        return False

    def get_citation_input(self, selector: CitationSelector) -> CitationInput | None:
        return self._citations.get(selector)


class ExactReader:
    def __init__(self, citations: dict[CitationSelector, CitationInput]) -> None:
        self._citations = citations

    def snapshot(self) -> ExactSnapshot:
        return ExactSnapshot(self._citations)


@pytest.mark.parametrize(
    "paper",
    (
        PaperSelector(paper_id=PAPER_ID),
        PaperSelector.by_arxiv("2608.01234"),
        PaperSelector.by_doi("10.1000/agents_evidence"),
    ),
)
def test_citation_service_resolves_only_the_exact_supported_identifier(
    paper: PaperSelector,
) -> None:
    citation = make_citation_input()
    selector = CitationSelector(paper=paper, paper_version_id=VERSION_ID)
    service = CitationService(ExactReader({selector: citation}), SourceBackedCitationRenderer())

    result = service.render(
        paper,
        CitationFormat.CSL_JSON,
        paper_version_id=VERSION_ID,
    )

    assert result.paper_id == PAPER_ID
    assert result.paper_version_id == VERSION_ID
    assert result.source_item_id == "2608.01234"


def test_citation_service_does_not_guess_when_an_exact_identifier_is_absent() -> None:
    service = CitationService(ExactReader({}), SourceBackedCitationRenderer())

    with pytest.raises(CitationNotFoundError, match="exact paper or version was not found"):
        service.render(PaperSelector.by_arxiv("2608.99999"), CitationFormat.BIBTEX)


def test_renderer_fails_closed_when_observed_doi_values_are_ambiguous() -> None:
    citation = make_citation_input(
        identifiers=(
            ObservedIdentifier(
                scheme="doi",
                canonical_value="10.1000/first",
                scope=IdentifierScope.VERSION,
            ),
            ObservedIdentifier(
                scheme="doi",
                canonical_value="10.1000/second",
                scope=IdentifierScope.VERSION,
            ),
        )
    )

    with pytest.raises(AmbiguousCitationMetadataError, match="observed DOI is ambiguous"):
        SourceBackedCitationRenderer().render(citation, CitationFormat.CSL_JSON)
