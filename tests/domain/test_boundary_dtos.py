from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from paper_insights.domain.acquisition import (
    DiscoveryBatch,
    DiscoveryIssue,
    DiscoveryPage,
    DiscoveryQuery,
    DiscoveryRecord,
    IdentifierScope,
    ObservedAuthor,
    ObservedCategory,
    ObservedIdentifier,
    ObservedPaperVersion,
    PreparedDiscovery,
    RecordLocator,
)
from paper_insights.domain.analysis import (
    AnalysisCacheKey,
    AnalysisPassage,
    AnalysisRequest,
    AnalysisResponse,
    AnalysisState,
    FullTextRequest,
)
from paper_insights.domain.corpus import (
    AttachedSnapshotRef,
    AttachPreparedRun,
    BlobInspection,
    BlobWrite,
    CitationFormat,
    CitationResult,
    CitationWarning,
    CreateCollection,
    IngestionFailureStage,
    IngestionItemRef,
    IngestionOutcome,
    IngestionRunRef,
    IngestionSummary,
    InterruptedRunCandidate,
    InterruptedRunRepairOutcome,
    InterruptedRunRepairResult,
    MetadataBlobRef,
    PaperIdentity,
    PreparedSnapshotAttachment,
    RecordIngestionFailure,
    RecordObservation,
    RepairInterruptedRun,
    RunCounters,
    SnapshotRecordAttachment,
    StoredBlobRef,
)
from paper_insights.domain.errors import ErrorCode
from paper_insights.domain.federation import (
    CorpusCapabilities,
    CorpusId,
    EvidenceBundle,
    EvidenceBundleReceipt,
    EvidenceItem,
    EvidenceRef,
    FederatedSearchQuery,
    NativeCorpusHit,
    SourceType,
)
from paper_insights.domain.identifiers import (
    AuthorId,
    PaperId,
    PaperVersionId,
    PassageId,
    RunId,
    Sha256,
    SnapshotId,
    SourceId,
    VersionObservationId,
    WatchlistId,
)
from paper_insights.domain.identity import (
    IdentityObservation,
    IdentityObservationBatch,
    IdentityQuery,
    IdentityState,
)
from paper_insights.domain.monitoring import CreateWatchlist, FinalizeWatchlistRun, WatchlistSlug
from paper_insights.domain.retrieval import CatalogRevision, CoverageStatus, PublishedIndex

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
        identifiers=(
            ObservedIdentifier(
                scheme="doi",
                canonical_value="10.1000/example",
                scope=IdentifierScope.VERSION,
            ),
        ),
        comment="Comment",
        journal_reference="Journal 1",
        language="en",
        source_url="https://arxiv.org/abs/2608.01234v1",
        submitted_at=NOW,
        announced_at=NOW,
    )


def prepared() -> PreparedDiscovery:
    item = observed()
    locator = RecordLocator(0, 0, item.source_item_id, item.source_version_key, Sha256("c" * 64))
    page = DiscoveryPage(
        capture_id=ID,
        records=(DiscoveryRecord(locator=locator, observation=item),),
        raw_payload=b"fixture page",
        media_type="application/json",
        retrieved_at=NOW,
        request_fingerprint=Sha256("d" * 64),
        next_cursor=None,
    )
    batch = DiscoveryBatch(
        source_id=SourceId("arxiv"),
        query=DiscoveryQuery(text="agents", limit=1),
        pages=(page,),
        records=(item,),
        issues=(),
    )
    return PreparedDiscovery.prepare(
        batch=batch,
        selected_records=(locator,),
        prepared_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )


def attached_page(value: PreparedDiscovery) -> PreparedSnapshotAttachment:
    page = value.batch.pages[0]
    return PreparedSnapshotAttachment(
        page_ordinal=0,
        capture_id=page.capture_id,
        blob=StoredBlobRef(
            sha256=page.payload_sha256,
            size_bytes=len(page.raw_payload),
            media_type=page.media_type,
            relative_path=Path("blobs/fixture"),
        ),
        request_fingerprint=page.request_fingerprint,
        retrieved_at=page.retrieved_at,
        next_cursor=page.next_cursor,
        records=(SnapshotRecordAttachment(locator=page.records[0].locator),),
    )


def test_attach_prepared_run_carries_complete_snapshot_graph() -> None:
    value = prepared()
    command = AttachPreparedRun(
        run_id=RunId(ID),
        prepared=value,
        pages=(attached_page(value),),
    )

    assert command.pages[0].records[0].locator == value.preview.selected_locators[0]
    assert command.prepared_digest == value.digest
    assert command.selected_records == 1


def test_attach_prepared_run_rejects_page_not_bound_to_prepared_manifest() -> None:
    value = prepared()
    page = attached_page(value)
    bad_page = PreparedSnapshotAttachment(
        page_ordinal=page.page_ordinal,
        capture_id=page.capture_id,
        blob=StoredBlobRef(
            sha256=Sha256("f" * 64),
            size_bytes=page.blob.size_bytes,
            media_type=page.blob.media_type,
            relative_path=page.blob.relative_path,
        ),
        request_fingerprint=page.request_fingerprint,
        retrieved_at=page.retrieved_at,
        next_cursor=page.next_cursor,
        records=page.records,
    )
    with pytest.raises(ValueError):
        AttachPreparedRun(run_id=RunId(ID), prepared=value, pages=(bad_page,))


def test_record_observation_uses_unattached_metadata_blob() -> None:
    command = RecordObservation(
        snapshot_id=SnapshotId(ID),
        record_ordinal=0,
        observed=observed(),
        metadata_blob=MetadataBlobRef(blob=stored_blob("b"), normalized_sha256=Sha256("b" * 64)),
    )

    assert command.metadata_blob.normalized_sha256 == command.observed.normalized_sha256


def test_record_observation_rejects_ordinal_mismatch() -> None:
    with pytest.raises(ValueError):
        RecordObservation(
            snapshot_id=SnapshotId(ID),
            record_ordinal=1,
            observed=observed(),
            metadata_blob=MetadataBlobRef(
                blob=stored_blob("b"), normalized_sha256=Sha256("b" * 64)
            ),
        )


def test_ingestion_failure_is_closed_sanitized_and_source_backed() -> None:
    failure = RecordIngestionFailure(
        run_id=RunId(ID),
        snapshot_id=SnapshotId(ID),
        record_ordinal=0,
        stage=IngestionFailureStage.CATALOG_WRITE,
        code=ErrorCode.CATALOG_CONFLICT,
        occurred_at=NOW,
    )
    assert failure.stage is IngestionFailureStage.CATALOG_WRITE
    with pytest.raises(ValueError):
        replace(failure, occurred_at=datetime(2026, 8, 29))
    with pytest.raises(ValueError):
        replace(failure, stage="catalog_write")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        replace(failure, code="catalog_conflict")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        replace(failure, code=ErrorCode.SOURCE_CONNECTION_FAILED)

    interrupted = RecordIngestionFailure.from_code(
        run_id=RunId(ID),
        snapshot_id=SnapshotId(ID),
        record_ordinal=1,
        stage=IngestionFailureStage.RECOVERY,
        code=ErrorCode.INTERRUPTED,
        occurred_at=NOW,
    )
    assert interrupted.message == "record interrupted before completion"


def test_ingestion_item_ref_identifies_snapshot_and_record() -> None:
    result = IngestionItemRef(
        run_id=RunId(ID),
        snapshot_id=SnapshotId(ID),
        record_ordinal=0,
        outcome=IngestionOutcome.UNCHANGED,
        paper_id=PaperId(ID),
        paper_version_id=PaperVersionId(ID),
        version_observation_id=VersionObservationId(ID),
        created_paper=False,
    )
    assert result.snapshot_id == SnapshotId(ID)
    with pytest.raises(ValueError):
        replace(result, outcome="unchanged")  # type: ignore[arg-type]


def test_ingestion_run_ref_returns_stable_ordered_snapshot_mapping() -> None:
    snapshots = (AttachedSnapshotRef(page_ordinal=0, snapshot_id=SnapshotId(ID)),)
    result = IngestionRunRef(run_id=RunId(ID), revision=1, snapshots=snapshots)

    assert result.snapshot_id_for(0) == SnapshotId(ID)
    with pytest.raises(ValueError):
        replace(result, snapshots=[*snapshots])  # type: ignore[arg-type]


def test_interrupted_run_repair_contract_is_closed_and_time_bounded() -> None:
    candidate = InterruptedRunCandidate(
        run_id=RunId(ID),
        started_at=NOW - timedelta(hours=2),
        selected_records=2,
        recorded_items=1,
    )
    command = RepairInterruptedRun(
        run_id=candidate.run_id,
        cutoff=NOW - timedelta(hours=1),
        occurred_at=NOW,
    )
    summary = IngestionSummary(
        run_id=RunId(ID),
        counters=RunCounters(selected_records=2, unchanged_records=1, failed_records=1),
    )
    mutated = InterruptedRunRepairResult(
        run_id=RunId(ID),
        outcome=InterruptedRunRepairOutcome.REPAIRED,
        summary=summary,
        revision=3,
    )
    no_op = InterruptedRunRepairResult(
        run_id=RunId(ID),
        outcome=InterruptedRunRepairOutcome.NOT_ELIGIBLE,
        summary=None,
        revision=3,
    )

    assert command.cutoff < command.occurred_at
    assert candidate.missing_records == 1
    assert mutated.summary is summary
    assert no_op.summary is None
    with pytest.raises(ValueError):
        replace(candidate, recorded_items=3)
    with pytest.raises(ValueError):
        replace(command, cutoff=datetime(2026, 8, 29))
    with pytest.raises(ValueError):
        replace(command, occurred_at=command.cutoff - timedelta(seconds=1))
    with pytest.raises(ValueError):
        replace(mutated, summary=None)
    with pytest.raises(ValueError):
        replace(no_op, summary=summary)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: DiscoveryIssue(code="record_invalid"),
        lambda: DiscoveryIssue(code=ErrorCode.INTERRUPTED),
        lambda: ObservedIdentifier("doi", "10.1000/example", "version"),
        lambda: BlobWrite(content=b"", media_type=""),
        lambda: StoredBlobRef(Sha256("a" * 64), -1, "text/plain", Path("/absolute")),
        lambda: FederatedSearchQuery(query="", limit_per_corpus=0),
        lambda: CreateWatchlist(
            slug=WatchlistSlug("weekly"),
            source_id=SourceId("arxiv"),
            query=DiscoveryQuery(text="x"),
            overlap_seconds=-1,
        ),
        lambda: CreateCollection("", ""),
        lambda: CreateCollection(str(ID), "Ambiguous collection slug"),
        lambda: IngestionRunRef(RunId(ID), revision=-1),
        lambda: PaperIdentity(PaperId(ID), datetime(2026, 8, 29)),
        lambda: BlobInspection(False, True, Sha256("a" * 64), 1),
        lambda: PublishedIndex(Path("relative.sqlite3"), CatalogRevision(0), 0),
        lambda: MetadataBlobRef(stored_blob("f"), Sha256("b" * 64)),
        lambda: FinalizeWatchlistRun(
            watchlist_id=WatchlistId(ID),
            ingestion_run_id=RunId(ID),
            expected_state_version=0,
            candidate_cursor=None,
            completed_at=datetime(2026, 8, 29, tzinfo=timezone(timedelta(hours=2))),
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
        replace(key, parameters_json="[]")
    with pytest.raises(ValueError):
        AnalysisRequest(
            key=key,
            passages=(AnalysisPassage(passage_id=PassageId("d" * 64), text="evidence"),),
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: FullTextRequest(PaperVersionId(ID), " ", "policy-v1"),
        lambda: FullTextRequest(PaperVersionId(ID), "http://example.test/paper.pdf", "v1"),
        lambda: FullTextRequest(PaperVersionId(ID), "https://", "v1"),
        lambda: AnalysisResponse(b"", ""),
        lambda: IdentityQuery(AuthorId(ID), " "),
        lambda: IdentityObservation(
            SourceId("orcid"), "", "Ada", Sha256("a" * 64), datetime(2026, 8, 29)
        ),
        lambda: IdentityObservationBatch(
            SourceId("orcid"),
            (IdentityObservation(SourceId("openalex"), "A1", "Ada", Sha256("a" * 64), NOW),),
        ),
        lambda: IdentityState((AuthorId(ID),), -1),
        lambda: CorpusCapabilities((), False, False),
        lambda: EvidenceRef(CorpusId("papers"), ""),
        lambda: EvidenceItem(
            EvidenceRef(CorpusId("papers"), "item-1"),
            SourceType.PAPER,
            "evidence",
            Sha256("a" * 64),
        ),
        lambda: NativeCorpusHit("", SourceType.PAPER, 0, None, ""),
        lambda: EvidenceBundle((), "unknown-v9"),
        lambda: EvidenceBundleReceipt(Path("relative.json"), Sha256("a" * 64), -1),
    ],
)
def test_later_wave_dtos_reject_invalid_values(factory: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        factory()


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
    rendered = CitationResult(**{**kwargs, "warnings": (CitationWarning.LITERAL_AUTHOR,)})
    assert json.dumps(rendered.warnings) == '["literal-author"]'
    with pytest.raises(ValueError):
        CitationResult(**{**kwargs, "schema_version": "future-v2"})
    with pytest.raises(ValueError):
        CitationResult(**{**kwargs, "missing_fields": ("title", "author")})
    with pytest.raises(ValueError):
        CitationResult(**{**kwargs, "warnings": ("arbitrary",)})


def test_domain_dtos_reject_mutable_collection_aliases() -> None:
    warnings = [CitationWarning.LITERAL_AUTHOR]
    with pytest.raises(ValueError):
        CitationResult(**{**_citation_kwargs(), "warnings": warnings})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        DiscoveryQuery(text="agents", categories=["cs.AI"])  # type: ignore[arg-type]


def _citation_kwargs() -> dict[str, object]:
    return {
        "schema_version": "citation-v1",
        "paper_id": PaperId(ID),
        "paper_version_id": PaperVersionId(ID),
        "version_observation_id": VersionObservationId(ID),
        "format": CitationFormat.CSL_JSON,
        "media_type": "application/vnd.citationstyles.csl+json",
        "content": "{}",
        "missing_fields": (),
        "source_id": SourceId("arxiv"),
        "source_item_id": "2608.01234",
        "snapshot_id": SnapshotId(ID),
        "record_ordinal": 0,
        "retrieved_at": NOW,
        "coverage": CoverageStatus.COMPLETE,
        "warnings": (),
    }
