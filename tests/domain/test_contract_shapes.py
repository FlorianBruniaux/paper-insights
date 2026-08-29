from __future__ import annotations

import inspect
import pkgutil
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import get_type_hints
from uuid import UUID

import pytest

from paper_insights import domain
from paper_insights.application import ports
from paper_insights.domain.acquisition import DiscoveryQuery
from paper_insights.domain.identifiers import (
    PaperId,
    PaperVersionId,
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
    SearchFilters,
)


def make_result(**changes: object) -> PaperSearchResult:
    hit = PaperSearchHit(
        paper_id=PaperId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")),
        paper_version_id=PaperVersionId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")),
        version_observation_id=VersionObservationId(
            UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")
        ),
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
        path=Path("candidate.sqlite3"),
        catalog_revision=CatalogRevision(2),
        generation=1,
        content_sha256=Sha256("f" * 64),
        receipt=receipt,
    )

    assert query.filters.category == "cs.AI"
    assert candidate.receipt.catalog_revision == candidate.catalog_revision


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
                str(hint).startswith(("list[", "dict[", "set["))
                for hint in hints.values()
            ), name


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
            "list_collections",
            "list_index_documents",
        },
        "CatalogUnitOfWork": {"commit", "rollback"},
        "CatalogUnitOfWorkFactory": {"begin"},
        "CitationRenderer": {"render"},
        "Clock": {"now"},
        "CollectionRepository": {"add", "create", "remove", "rename"},
        "CorpusRepository": {"record_observation", "resolve_paper"},
        "DiscoveryProvider": {"discover"},
        "EvidenceBundleWriter": {"write"},
        "FederatedCorpus": {"capabilities", "resolve_evidence", "search"},
        "FullTextProvider": {"acquire"},
        "IdentityProvider": {"observe"},
        "IdentityUnitOfWork": {"apply", "commit", "record_observations", "reverse", "rollback"},
        "IdentityUnitOfWorkFactory": {"begin"},
        "IdGenerator": {"new"},
        "IngestionRepository": {"attach_prepared_run", "finalize_run", "record_item"},
        "SearchIndexBuilder": {"build_candidate", "discard", "publish"},
        "SearchIndexReader": {"get_passage", "search_papers", "search_passages"},
        "TextExtractor": {"extract"},
        "WatchlistUnitOfWork": {"commit", "create", "finalize", "load", "rollback", "update"},
        "WatchlistUnitOfWorkFactory": {"begin"},
    }
    assert set(ports.__all__) == set(expected_methods)
    exported = {name: getattr(ports, name) for name in ports.__all__}

    for name, protocol in exported.items():
        assert getattr(protocol, "_is_protocol", False), name
        methods = {
            method_name: method
            for method_name, method in inspect.getmembers(protocol, inspect.isfunction)
            if not method_name.startswith("_")
        }
        assert set(methods) == expected_methods[name]
        for method_name, method in methods.items():
            assert not inspect.iscoroutinefunction(method), f"{name}.{method_name}"
            hints = get_type_hints(method)
            assert "return" in hints, f"{name}.{method_name}"
            assert "Any" not in repr(hints), f"{name}.{method_name}"
            assert not any(
                token in repr(hints).lower()
                for token in ("sqlalchemy", "httpx", "pydantic", "adapter")
            )


def test_datetime_contract_uses_aware_utc_values() -> None:
    assert datetime(2026, 8, 29, tzinfo=UTC).utcoffset() is not None
