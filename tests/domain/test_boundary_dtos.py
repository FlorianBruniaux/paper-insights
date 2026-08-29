from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from paper_insights.domain.acquisition import (
    DiscoveryIssue,
    DiscoveryQuery,
    ObservedAuthor,
    ObservedCategory,
    ObservedIdentifier,
    ObservedPaperVersion,
    RecordLocator,
)
from paper_insights.domain.analysis import (
    AnalysisCacheKey,
    AnalysisPassage,
    AnalysisRequest,
    AnalysisState,
)
from paper_insights.domain.corpus import (
    AttachPreparedRun,
    BlobWrite,
    CitationFormat,
    CitationResult,
    MetadataBlobRef,
    PreparedSnapshotAttachment,
    RecordObservation,
    SnapshotRecordAttachment,
    StoredBlobRef,
)
from paper_insights.domain.errors import ErrorCode
from paper_insights.domain.federation import FederatedSearchQuery
from paper_insights.domain.identifiers import (
    PaperId,
    PaperVersionId,
    PassageId,
    RunId,
    Sha256,
    SnapshotId,
    SourceId,
    VersionObservationId,
)
from paper_insights.domain.monitoring import CreateWatchlist, WatchlistSlug
from paper_insights.domain.retrieval import CoverageStatus


ID = UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")
NOW = datetime(2026, 8, 29, tzinfo=UTC)


def stored_blob(seed: str = "a") -> StoredBlobRef:
    return StoredBlobRef(
        sha256=Sha256(seed * 64),
        size_bytes=4,
        media_type="application/json",
        relative_path=Path(f"blobs/{seed * 2}"),
    )


def observed() -> ObservedPaperVersion:
    return ObservedPaperVersion(
        source_id=SourceId("arxiv"),
        source_item_id="2608.01234",
        source_version_key="2608.01234v1",
        title="Title",
        abstract="Abstract",
        page_ordinal=0,
        record_ordinal=0,
        normalized_sha256=Sha256("b" * 64),
        authors=(ObservedAuthor(raw_name="Ada Lovelace", affiliation_raw="Institute"),),
        categories=(ObservedCategory(value="cs.AI", is_primary=True),),
        identifiers=(ObservedIdentifier(scheme="doi", canonical_value="10.1000/example"),),
        comment="Comment",
        journal_reference="Journal 1",
        language="en",
        source_url="https://arxiv.org/abs/2608.01234v1",
        submitted_at=NOW,
        announced_at=NOW,
    )


def test_attach_prepared_run_carries_complete_snapshot_graph() -> None:
    locator = RecordLocator(0, 0, "2608.01234", "2608.01234v1", Sha256("c" * 64))
    page = PreparedSnapshotAttachment(
        page_ordinal=0,
        capture_id=ID,
        blob=stored_blob(),
        request_fingerprint=Sha256("d" * 64),
        retrieved_at=NOW,
        next_cursor=None,
        records=(SnapshotRecordAttachment(locator=locator),),
    )
    command = AttachPreparedRun(
        run_id=RunId(ID),
        source_id=SourceId("arxiv"),
        prepared_digest=Sha256("e" * 64),
        query_json='{"schema_version":"discovery-query-v1"}',
        pages=(page,),
        selected_locators=(locator,),
    )

    assert command.pages[0].records[0].locator == locator
    assert command.selected_records == 1


def test_record_observation_uses_unattached_metadata_blob() -> None:
    command = RecordObservation(
        run_id=RunId(ID),
        snapshot_id=SnapshotId(ID),
        record_ordinal=0,
        observed=observed(),
        metadata_blob=MetadataBlobRef(blob=stored_blob("f"), normalized_sha256=Sha256("b" * 64)),
    )

    assert command.metadata_blob.normalized_sha256 == command.observed.normalized_sha256


@pytest.mark.parametrize(
    "factory",
    [
        lambda: DiscoveryIssue(code=ErrorCode.RECORD_INVALID, message=""),
        lambda: BlobWrite(content=b"", media_type=""),
        lambda: StoredBlobRef(Sha256("a" * 64), -1, "text/plain", Path("/absolute")),
        lambda: FederatedSearchQuery(query="", limit_per_corpus=0),
        lambda: CreateWatchlist(
            slug=WatchlistSlug("weekly"),
            source_id=SourceId("arxiv"),
            query=DiscoveryQuery(text="x"),
            overlap_seconds=-1,
        ),
    ],
)
def test_boundary_dtos_reject_invalid_values(factory: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        factory()


def test_analysis_key_and_request_are_closed_and_ordered() -> None:
    passage = PassageId("a" * 64)
    key = AnalysisCacheKey(
        paper_version_id=PaperVersionId(ID),
        artifact_sha256=Sha256("b" * 64),
        passage_ids=(passage,),
        chunk_schema_version="chunk-v1",
        prompt_version="prompt-v1",
        prompt_sha256=Sha256("c" * 64),
        provider="fixture",
        model="fixture-v1",
        parameters_json="{}",
        result_schema_version="analysis-v1",
    )
    assert AnalysisState.COMPLETE.value == "complete"
    with pytest.raises(ValueError):
        AnalysisRequest(
            key=key,
            passages=(AnalysisPassage(passage_id=PassageId("d" * 64), text="evidence"),),
        )


def test_citation_result_requires_exact_schema_and_provenance() -> None:
    kwargs = dict(
        schema_version="citation-v1",
        paper_id=PaperId(ID),
        paper_version_id=PaperVersionId(ID),
        version_observation_id=VersionObservationId(ID),
        format=CitationFormat.CSL_JSON,
        media_type="application/vnd.citationstyles.csl+json",
        content="{}",
        missing_fields=(),
        source_id=SourceId("arxiv"),
        source_item_id="2608.01234",
        snapshot_id=SnapshotId(ID),
        record_ordinal=0,
        retrieved_at=NOW,
        coverage=CoverageStatus.COMPLETE,
        warnings=(),
    )
    assert CitationResult(**kwargs).source_item_id == "2608.01234"
    with pytest.raises(ValueError):
        CitationResult(**{**kwargs, "schema_version": "future-v2"})
