from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Literal
from uuid import UUID

import pytest

from paper_insights.adapters.search.sqlite_fts.builder import SqliteFtsIndexBuilder
from paper_insights.adapters.search.sqlite_fts.reader import SqliteFtsSearchReader
from paper_insights.adapters.search.sqlite_fts.schema import open_readonly
from paper_insights.application.research.search import LocalSearch
from paper_insights.domain.identifiers import (
    PaperId,
    PaperVersionId,
    Sha256,
    VersionObservationId,
)
from paper_insights.domain.retrieval import (
    CatalogRevision,
    CoverageStatus,
    IndexBuildRequest,
    IndexDocument,
    PaperSearchQuery,
    PassageSearchQuery,
)


@dataclass
class _Lease:
    revision: CatalogRevision

    def __enter__(self) -> _Lease:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc_type, exc, traceback
        return False


class _RevisionSnapshot:
    def __init__(self, revision: int) -> None:
        self.revision = CatalogRevision(revision)

    def __enter__(self) -> _RevisionSnapshot:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc_type, exc, traceback
        return False


class _Catalog:
    def __init__(self, revision: int) -> None:
        self.revision = revision

    def snapshot(self) -> _RevisionSnapshot:
        return _RevisionSnapshot(self.revision)


def _document(index: int, title: str, abstract: str) -> IndexDocument:
    suffix = f"{index:02x}"
    return IndexDocument(
        paper_id=PaperId(UUID(f"01890f3e-3b12-7cc0-98d6-4f6f94748f{suffix}")),
        paper_version_id=PaperVersionId(UUID(f"01890f3e-3b12-7cc0-98d6-4f6f94749f{suffix}")),
        version_observation_id=VersionObservationId(
            UUID(f"01890f3e-3b12-7cc0-98d6-4f6f94750f{suffix}")
        ),
        title=title,
        abstract=abstract,
        metadata_artifact_sha256=Sha256(f"{index:x}" * 64),
    )


def _published_index(tmp_path: Path, *, revision: int = 5) -> Path:
    path = tmp_path / "search-v1.sqlite3"
    request = IndexBuildRequest(
        documents=(
            _document(1, "Agent evaluation", "Benchmark evidence for local agents."),
            _document(2, "Agent evidence", "Evaluation methods with provenance."),
            _document(3, "Protein structure", "A biology result."),
        ),
        catalog_revision=CatalogRevision(revision),
        chunk_schema_version="chunk-v1",
    )
    builder = SqliteFtsIndexBuilder(path)
    candidate = builder.build_candidate(request)
    builder.publish(candidate, _Lease(CatalogRevision(revision)))
    return path


def test_paper_search_returns_stable_rank_raw_score_revisions_and_counts(
    tmp_path: Path,
) -> None:
    path = _published_index(tmp_path)
    reader = SqliteFtsSearchReader(path, _Catalog(5))
    query = PaperSearchQuery(query="evaluation evidence", limit=1)

    first = reader.search_papers(query)
    second = reader.search_papers(query)

    assert first == second
    assert first.coverage is CoverageStatus.COMPLETE
    assert first.catalog_revision == CatalogRevision(5)
    assert first.index_revision == CatalogRevision(5)
    assert first.returned == 1
    assert first.available == 2
    assert first.truncated is True
    assert first.applied_limit == 1
    assert first.hits[0].rank == 1
    assert isinstance(first.hits[0].bm25_score, float)
    assert first.hits[0].title == "Agent evidence"
    assert first.hits[0].artifact_sha256 == Sha256("2" * 64)


def test_passage_search_and_lookup_preserve_exact_identity_with_bounded_excerpt(
    tmp_path: Path,
) -> None:
    path = _published_index(tmp_path)
    reader = SqliteFtsSearchReader(path, _Catalog(5), maximum_excerpt_characters=24)

    result = reader.search_passages(PassageSearchQuery(query="provenance", limit=10))

    assert result.coverage is CoverageStatus.COMPLETE
    assert result.returned == 1
    assert result.available == 1
    assert result.truncated is False
    hit = result.hits[0]
    assert hit.rank == 1
    assert len(hit.excerpt) <= 24
    assert hit.passage.identity.section == "abstract"
    assert reader.get_passage(hit.passage.passage_id) == hit.passage


def test_stale_index_reports_partial_coverage_without_hiding_hits(tmp_path: Path) -> None:
    path = _published_index(tmp_path, revision=5)
    reader = SqliteFtsSearchReader(path, _Catalog(6))

    result = reader.search_papers(PaperSearchQuery(query="biology"))

    assert result.coverage is CoverageStatus.PARTIAL
    assert result.catalog_revision == CatalogRevision(6)
    assert result.index_revision == CatalogRevision(5)
    assert result.returned == 1


def test_missing_index_is_unavailable_and_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    reader = SqliteFtsSearchReader(path, _Catalog(4))

    result = reader.search_papers(PaperSearchQuery(query="evidence"))

    assert result.coverage is CoverageStatus.UNAVAILABLE
    assert result.catalog_revision == CatalogRevision(4)
    assert result.index_revision == CatalogRevision(0)
    assert result.hits == ()
    assert not path.exists()


def test_search_database_connection_is_read_only_and_query_only(tmp_path: Path) -> None:
    path = _published_index(tmp_path)

    with open_readonly(path) as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("CREATE TABLE forbidden (id INTEGER)")


def test_reader_rejects_an_index_with_an_unknown_self_described_schema(tmp_path: Path) -> None:
    path = _published_index(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE index_meta SET index_schema_version = 'future-v9'")
        connection.commit()
    finally:
        connection.close()

    reader = SqliteFtsSearchReader(path, _Catalog(5))

    with pytest.raises(ValueError, match="unsupported search index schema"):
        reader.search_papers(PaperSearchQuery(query="evidence"))


def test_application_search_service_preserves_reader_results_and_passage_ids(
    tmp_path: Path,
) -> None:
    path = _published_index(tmp_path)
    service = LocalSearch(SqliteFtsSearchReader(path, _Catalog(5)))

    papers = service.search_papers(PaperSearchQuery(query="provenance"))
    passages = service.search_passages(PassageSearchQuery(query="provenance"))

    assert papers.returned == 1
    assert passages.returned == 1
    assert service.get_passage(passages.hits[0].passage.passage_id) == passages.hits[0].passage
