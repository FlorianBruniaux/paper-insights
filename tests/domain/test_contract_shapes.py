from __future__ import annotations

import inspect
import pkgutil
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import get_origin, get_type_hints
from uuid import UUID

import pytest

from paper_insights import domain
from paper_insights.application import ports
from paper_insights.domain.acquisition import DiscoveryQuery
from paper_insights.domain.identifiers import (
    PaperId,
    PaperVersionId,
    PassageId,
    Sha256,
    SourceId,
    VersionObservationId,
)
from paper_insights.domain.retrieval import (
    CatalogRevision,
    CoverageStatus,
    IndexCandidate,
    IndexReceipt,
    PaperSearchHit,
    PaperSearchQuery,
    PaperSearchResult,
    PassageIdentity,
    PassageView,
    SearchFilters,
    passage_id,
)


def make_result(**changes: object) -> PaperSearchResult:
    hit = PaperSearchHit(
        paper_id=PaperId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")),
        paper_version_id=PaperVersionId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")),
        version_observation_id=VersionObservationId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")),
        title="Paper",
        rank=1,
        bm25_score=-1.0,
        artifact_sha256=Sha256("a" * 64),
    )
    values: dict[str, object] = {
        "hits": (hit,),
        "coverage": CoverageStatus.COMPLETE,
        "catalog_revision": CatalogRevision(2),
        "index_revision": CatalogRevision(2),
        "truncated": False,
        "returned": 1,
        "available": 1,
        "applied_limit": 10,
    }
    values.update(changes)
    return PaperSearchResult(**values)


def test_search_result_requires_consistent_coverage_and_counts() -> None:
    assert make_result().returned == 1
    assert get_type_hints(PaperSearchHit)["version_observation_id"] is VersionObservationId
    assert {field.name for field in fields(PaperSearchResult)} >= {
        "hits",
        "coverage",
        "catalog_revision",
        "index_revision",
        "truncated",
        "returned",
        "available",
        "applied_limit",
    }
    with pytest.raises(ValueError):
        make_result(returned=0)
    with pytest.raises(ValueError):
        make_result(available=0)
    with pytest.raises(ValueError):
        make_result(truncated=True, available=1)
    with pytest.raises(ValueError):
        make_result(index_revision=CatalogRevision(1))


def test_search_query_has_closed_filters_and_index_candidate_has_receipt() -> None:
    query = PaperSearchQuery(
        query="agents",
        filters=SearchFilters(source_id=SourceId("arxiv"), category="cs.AI"),
        limit=10,
    )
    receipt = IndexReceipt(
        index_schema_version="search-v1",
        chunk_schema_version="chunk-v1",
        generation=1,
        catalog_revision=CatalogRevision(2),
        document_count=1,
        passage_count=2,
        content_sha256=Sha256("f" * 64),
    )
    candidate = IndexCandidate(
        path=Path("/private/tmp/candidate.sqlite3"),
        catalog_revision=CatalogRevision(2),
        generation=1,
        content_sha256=Sha256("f" * 64),
        receipt=receipt,
    )

    assert query.filters.category == "cs.AI"
    assert candidate.receipt.catalog_revision == candidate.catalog_revision


def test_search_rejects_blank_query_excess_hits_and_bad_rank_order() -> None:
    with pytest.raises(ValueError):
        PaperSearchQuery(query="   ")
    with pytest.raises(ValueError):
        make_result(applied_limit=0)

    first = make_result().hits[0]
    second = type(first)(
        paper_id=first.paper_id,
        paper_version_id=first.paper_version_id,
        version_observation_id=first.version_observation_id,
        title="Second",
        rank=2,
        bm25_score=first.bm25_score,
        artifact_sha256=first.artifact_sha256,
    )
    with pytest.raises(ValueError):
        make_result(hits=(first, second), returned=2, available=2, applied_limit=1)

    duplicate = type(first)(
        paper_id=first.paper_id,
        paper_version_id=first.paper_version_id,
        version_observation_id=first.version_observation_id,
        title="Duplicate",
        rank=first.rank,
        bm25_score=first.bm25_score,
        artifact_sha256=first.artifact_sha256,
    )
    with pytest.raises(ValueError):
        make_result(hits=(first, duplicate), returned=2, available=2, applied_limit=2)


def test_search_filters_and_passage_views_reject_incoherent_values() -> None:
    with pytest.raises(ValueError):
        SearchFilters(category="   ")

    identity = PassageIdentity(
        paper_version_id=PaperVersionId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")),
        artifact_sha256=Sha256("b" * 64),
        chunk_schema_version="chunk-v1",
        section=None,
        ordinal=0,
        normalized_text="evidence",
        start_offset=0,
        end_offset=8,
    )
    kwargs = {
        "identity": identity,
        "paper_id": PaperId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")),
        "version_observation_id": VersionObservationId(
            UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")
        ),
    }
    with pytest.raises(ValueError):
        PassageView(passage_id=PassageId("f" * 64), text="evidence", **kwargs)
    with pytest.raises(ValueError):
        PassageView(passage_id=passage_id(identity), text="different", **kwargs)


def test_public_domain_dataclasses_are_frozen_slotted_and_tuple_based() -> None:
    query = DiscoveryQuery(text="agents", categories=("cs.AI",), limit=5)

    assert is_dataclass(query)
    assert hasattr(type(query), "__slots__")
    assert isinstance(query.categories, tuple)
    with pytest.raises(FrozenInstanceError):
        query.limit = 6  # type: ignore[misc]


def test_every_public_domain_dataclass_is_frozen_slotted_and_has_no_mutable_collection() -> None:
    modules = []
    for info in pkgutil.iter_modules(domain.__path__, f"{domain.__name__}."):
        modules.append(__import__(info.name, fromlist=["*"]))

    for module in modules:
        for name, candidate in inspect.getmembers(module, inspect.isclass):
            if (
                name.startswith("_")
                or candidate.__module__ != module.__name__
                or not is_dataclass(candidate)
            ):
                continue
            assert candidate.__dataclass_params__.frozen, name
            assert hasattr(candidate, "__slots__"), name
            hints = get_type_hints(candidate)
            assert not any(
                str(hint).startswith(("list[", "dict[", "set[")) for hint in hints.values()
            ), name


def test_every_tuple_field_has_a_runtime_immutability_guard() -> None:
    for info in pkgutil.iter_modules(domain.__path__, f"{domain.__name__}."):
        module = __import__(info.name, fromlist=["*"])
        for name, candidate in inspect.getmembers(module, inspect.isclass):
            if candidate.__module__ != module.__name__ or not is_dataclass(candidate):
                continue
            hints = get_type_hints(candidate)
            tuple_fields = {
                field.name
                for field in fields(candidate)
                if get_origin(hints.get(field.name)) is tuple
            }
            if not tuple_fields:
                continue
            post_init = candidate.__dict__.get("__post_init__")
            assert post_init is not None, name
            source = inspect.getsource(post_init)
            assert "require_tuples" in source, name
            assert all(f'"{field_name}"' in source for field_name in tuple_fields), name


def test_all_announced_ports_are_protocols_sync_annotated_and_framework_free() -> None:
    expected_methods = {
        "AnalysisBackend": {"analyze"},
        "AnalysisUnitOfWork": {
            "commit",
            "find_complete",
            "publish_complete",
            "record_attempt",
            "rollback",
        },
        "AnalysisUnitOfWorkFactory": {"begin"},
        "BlobStore": {"inspect", "open_verified", "put"},
        "CatalogReader": {"snapshot"},
        "CatalogRevisionGuard": {"hold_if_current"},
        "CatalogRevisionLease": set(),
        "CatalogSnapshot": {
            "get_citation_input",
            "get_paper",
            "list_interrupted_runs",
            "list_collections",
            "list_index_documents",
        },
        "CatalogUnitOfWork": {"commit", "rollback"},
        "CatalogUnitOfWorkFactory": {"begin"},
        "CitationRenderer": {"render"},
        "Clock": {"now"},
        "CollectionRepository": {"add", "create", "remove", "rename"},
        "CorpusRepository": {"resolve_paper"},
        "DiscoveryProvider": {"discover"},
        "EvidenceBundleWriter": {"write"},
        "FederatedCorpus": {"capabilities", "resolve_evidence", "search"},
        "FullTextProvider": {"acquire"},
        "IdentityProvider": {"observe"},
        "IdentityUnitOfWork": {"apply", "commit", "record_observations", "reverse", "rollback"},
        "IdentityUnitOfWorkFactory": {"begin"},
        "IdGenerator": {"new"},
        "IngestionRepository": {
            "attach_prepared_run",
            "finalize_run",
            "record_failure",
            "record_item",
            "repair_interrupted_run",
        },
        "SearchIndexBuilder": {"build_candidate", "discard", "publish"},
        "SearchIndexReader": {"get_passage", "search_papers", "search_passages"},
        "TextExtractor": {"extract"},
        "WatchlistUnitOfWork": {"commit", "create", "finalize", "load", "rollback", "update"},
        "WatchlistUnitOfWorkFactory": {"begin"},
    }
    assert set(ports.__all__) == set(expected_methods)
    expected_signatures = {
        "AnalysisBackend.analyze": "(self, request: 'AnalysisRequest') -> 'AnalysisResponse'",
        "AnalysisUnitOfWork.commit": "(self) -> 'None'",
        "AnalysisUnitOfWork.find_complete": (
            "(self, key: 'AnalysisCacheKey') -> 'AnalysisResult | None'"
        ),
        "AnalysisUnitOfWork.publish_complete": (
            "(self, command: 'PublishAnalysis') -> 'AnalysisResult'"
        ),
        "AnalysisUnitOfWork.record_attempt": (
            "(self, attempt: 'AnalysisAttempt') -> 'AnalysisAttemptRef'"
        ),
        "AnalysisUnitOfWork.rollback": "(self) -> 'None'",
        "AnalysisUnitOfWorkFactory.begin": "(self) -> 'AnalysisUnitOfWork'",
        "BlobStore.inspect": "(self, ref: 'StoredBlobRef') -> 'BlobInspection'",
        "BlobStore.open_verified": "(self, ref: 'StoredBlobRef') -> 'BinaryIO'",
        "BlobStore.put": "(self, blob: 'BlobWrite') -> 'StoredBlobRef'",
        "CatalogReader.snapshot": "(self) -> 'CatalogSnapshot'",
        "CatalogRevisionGuard.hold_if_current": (
            "(self, expected: 'CatalogRevision') -> 'CatalogRevisionLease'"
        ),
        "CatalogSnapshot.get_citation_input": (
            "(self, selector: 'CitationSelector') -> 'CitationInput | None'"
        ),
        "CatalogSnapshot.get_paper": "(self, selector: 'PaperSelector') -> 'PaperView | None'",
        "CatalogSnapshot.list_collections": "(self) -> 'tuple[CollectionView, ...]'",
        "CatalogSnapshot.list_index_documents": "(self) -> 'tuple[IndexDocument, ...]'",
        "CatalogSnapshot.list_interrupted_runs": (
            "(self, cutoff: 'datetime') -> 'tuple[InterruptedRunCandidate, ...]'"
        ),
        "CatalogUnitOfWork.commit": "(self) -> 'None'",
        "CatalogUnitOfWork.rollback": "(self) -> 'None'",
        "CatalogUnitOfWorkFactory.begin": "(self) -> 'CatalogUnitOfWork'",
        "CitationRenderer.render": (
            "(self, citation: 'CitationInput', format: 'CitationFormat') -> 'CitationResult'"
        ),
        "Clock.now": "(self) -> 'datetime'",
        "CollectionRepository.add": "(self, command: 'AddCollectionPaper') -> 'CollectionView'",
        "CollectionRepository.create": "(self, command: 'CreateCollection') -> 'CollectionView'",
        "CollectionRepository.remove": (
            "(self, command: 'RemoveCollectionPaper') -> 'CollectionView'"
        ),
        "CollectionRepository.rename": "(self, command: 'RenameCollection') -> 'CollectionView'",
        "CorpusRepository.resolve_paper": (
            "(self, selector: 'PaperSelector') -> 'PaperIdentity | None'"
        ),
        "DiscoveryProvider.discover": "(self, query: 'DiscoveryQuery') -> 'DiscoveryBatch'",
        "EvidenceBundleWriter.write": "(self, bundle: 'EvidenceBundle') -> 'EvidenceBundleReceipt'",
        "FederatedCorpus.capabilities": "(self) -> 'CorpusCapabilities'",
        "FederatedCorpus.resolve_evidence": "(self, ref: 'EvidenceRef') -> 'EvidenceItem | None'",
        "FederatedCorpus.search": "(self, query: 'FederatedSearchQuery') -> 'NativeCorpusResult'",
        "FullTextProvider.acquire": "(self, request: 'FullTextRequest') -> 'FullTextAcquisition'",
        "IdentityProvider.observe": "(self, query: 'IdentityQuery') -> 'IdentityObservationBatch'",
        "IdentityUnitOfWork.apply": "(self, decision: 'IdentityDecision') -> 'IdentityState'",
        "IdentityUnitOfWork.commit": "(self) -> 'None'",
        "IdentityUnitOfWork.record_observations": (
            "(self, batch: 'IdentityObservationBatch') -> 'tuple[IdentityObservationRef, ...]'"
        ),
        "IdentityUnitOfWork.reverse": (
            "(self, command: 'ReverseIdentityDecision') -> 'IdentityState'"
        ),
        "IdentityUnitOfWork.rollback": "(self) -> 'None'",
        "IdentityUnitOfWorkFactory.begin": "(self) -> 'IdentityUnitOfWork'",
        "IdGenerator.new": "(self) -> 'UUID'",
        "IngestionRepository.attach_prepared_run": (
            "(self, command: 'AttachPreparedRun') -> 'IngestionRunRef'"
        ),
        "IngestionRepository.finalize_run": "(self, run_id: 'RunId') -> 'IngestionSummary'",
        "IngestionRepository.record_failure": (
            "(self, command: 'RecordIngestionFailure') -> 'IngestionItemRef'"
        ),
        "IngestionRepository.record_item": (
            "(self, command: 'RecordIngestionItem') -> 'IngestionItemRef'"
        ),
        "IngestionRepository.repair_interrupted_run": (
            "(self, command: 'RepairInterruptedRun') -> 'InterruptedRunRepairResult'"
        ),
        "SearchIndexBuilder.build_candidate": (
            "(self, request: 'IndexBuildRequest') -> 'IndexCandidate'"
        ),
        "SearchIndexBuilder.discard": "(self, candidate: 'IndexCandidate') -> 'None'",
        "SearchIndexBuilder.publish": (
            "(self, candidate: 'IndexCandidate', lease: 'CatalogRevisionLease') -> 'PublishedIndex'"
        ),
        "SearchIndexReader.get_passage": "(self, passage_id: 'PassageId') -> 'PassageView | None'",
        "SearchIndexReader.search_papers": (
            "(self, query: 'PaperSearchQuery') -> 'PaperSearchResult'"
        ),
        "SearchIndexReader.search_passages": (
            "(self, query: 'PassageSearchQuery') -> 'PassageSearchResult'"
        ),
        "TextExtractor.extract": "(self, artifact: 'VerifiedArtifact') -> 'ExtractedText'",
        "WatchlistUnitOfWork.commit": "(self) -> 'None'",
        "WatchlistUnitOfWork.create": "(self, command: 'CreateWatchlist') -> 'WatchlistState'",
        "WatchlistUnitOfWork.finalize": (
            "(self, command: 'FinalizeWatchlistRun') -> 'WatchlistRunResult'"
        ),
        "WatchlistUnitOfWork.load": "(self, slug: 'WatchlistSlug') -> 'WatchlistState | None'",
        "WatchlistUnitOfWork.rollback": "(self) -> 'None'",
        "WatchlistUnitOfWork.update": "(self, command: 'UpdateWatchlist') -> 'WatchlistState'",
        "WatchlistUnitOfWorkFactory.begin": "(self) -> 'WatchlistUnitOfWork'",
    }
    expected_attributes = {
        "AnalysisBackend": {"provider": "str", "model": "str"},
        "CatalogRevisionLease": {"revision": "CatalogRevision"},
        "CatalogSnapshot": {"revision": "CatalogRevision"},
        "CatalogUnitOfWork": {
            "corpus": "CorpusRepository",
            "ingestion": "IngestionRepository",
            "collections": "CollectionRepository",
        },
        "DiscoveryProvider": {"source_id": "SourceId"},
        "FederatedCorpus": {"corpus_id": "CorpusId"},
        "IdentityProvider": {"source_id": "SourceId"},
        "TextExtractor": {"name": "str", "version": "str"},
    }
    context_protocols = {
        "AnalysisUnitOfWork",
        "CatalogRevisionLease",
        "CatalogSnapshot",
        "CatalogUnitOfWork",
        "IdentityUnitOfWork",
        "WatchlistUnitOfWork",
    }
    exported = {name: getattr(ports, name) for name in ports.__all__}

    for name, protocol in exported.items():
        assert getattr(protocol, "_is_protocol", False), name
        attributes = {key: value.__name__ for key, value in get_type_hints(protocol).items()}
        assert attributes == expected_attributes.get(name, {})
        methods = {
            method_name: method
            for method_name, method in inspect.getmembers(protocol, inspect.isfunction)
            if not method_name.startswith("_")
        }
        assert set(methods) == expected_methods[name]
        for method_name, method in methods.items():
            qualified = f"{name}.{method_name}"
            assert str(inspect.signature(method)) == expected_signatures[qualified]
            assert not inspect.iscoroutinefunction(method), f"{name}.{method_name}"
            hints = get_type_hints(method)
            assert "return" in hints, f"{name}.{method_name}"
            assert "Any" not in repr(hints), f"{name}.{method_name}"
            assert not any(
                token in repr(hints).lower()
                for token in ("sqlalchemy", "httpx", "pydantic", "adapter")
            )
        if name in context_protocols:
            enter = protocol.__dict__["__enter__"]
            exit_method = protocol.__dict__["__exit__"]
            assert str(inspect.signature(enter)) == f"(self) -> '{name}'"
            assert str(inspect.signature(exit_method)) == (
                "(self, exc_type: 'type[BaseException] | None', "
                "exc: 'BaseException | None', traceback: 'TracebackType | None') -> 'bool'"
            )


def test_datetime_contract_uses_aware_utc_values() -> None:
    assert datetime(2026, 8, 29, tzinfo=UTC).utcoffset() is not None
