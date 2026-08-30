from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Literal
from uuid import UUID

import pytest

import paper_insights.adapters.search.sqlite_fts.schema as schema_module
from paper_insights.adapters.search.sqlite_fts.builder import SqliteFtsIndexBuilder
from paper_insights.adapters.search.sqlite_fts.reader import SqliteFtsSearchReader
from paper_insights.adapters.search.sqlite_fts.schema import open_readonly
from paper_insights.application.research.search import LocalSearch
from paper_insights.domain.acquisition import IdentifierScope
from paper_insights.domain.identifiers import (
    CollectionId,
    PaperId,
    PaperVersionId,
    Sha256,
    SourceId,
    VersionObservationId,
)
from paper_insights.domain.retrieval import (
    CatalogRevision,
    CoverageStatus,
    IndexBuildRequest,
    IndexDocument,
    PaperSearchQuery,
    PassageSearchQuery,
    SearchFilters,
    SearchIdentifier,
)

_ARXIV_SOURCE = SourceId("arxiv")


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


def _document(
    index: int,
    title: str,
    abstract: str,
    *,
    source_id: SourceId = _ARXIV_SOURCE,
    authors: tuple[str, ...] = (),
    categories: tuple[str, ...] = (),
    language: str | None = None,
    submitted_at: datetime | None = None,
    collection_ids: tuple[CollectionId, ...] = (),
    collection_slugs: tuple[str, ...] = (),
    identifiers: tuple[SearchIdentifier, ...] = (),
) -> IndexDocument:
    suffix = f"{index:02x}"
    return IndexDocument(
        paper_id=PaperId(UUID(f"01890f3e-3b12-7cc0-98d6-4f6f94748f{suffix}")),
        paper_version_id=PaperVersionId(UUID(f"01890f3e-3b12-7cc0-98d6-4f6f94749f{suffix}")),
        version_observation_id=VersionObservationId(
            UUID(f"01890f3e-3b12-7cc0-98d6-4f6f94750f{suffix}")
        ),
        source_id=source_id,
        title=title,
        abstract=abstract,
        metadata_artifact_sha256=Sha256(f"{index:x}" * 64),
        authors=authors,
        categories=categories,
        language=language,
        submitted_at=submitted_at,
        collection_ids=collection_ids,
        collection_slugs=collection_slugs,
        identifiers=identifiers,
    )


def _published_index(tmp_path: Path, *, revision: int = 5) -> Path:
    path = tmp_path / "search-v1.sqlite3"
    request = IndexBuildRequest(
        documents=(
            _document(1, "Agent evaluation", "Benchmark evidence for local agents."),
            _document(
                2,
                "Agent evidence",
                "Evaluation methods with provenance.",
                authors=("Alice Example", "Bob Researcher"),
                identifiers=(
                    SearchIdentifier("arxiv", "2608.05678", IdentifierScope.PAPER),
                    SearchIdentifier("doi", "10.1234/example.2", IdentifierScope.PAPER),
                ),
            ),
            _document(3, "Protein structure", "A biology result."),
        ),
        catalog_revision=CatalogRevision(revision),
        chunk_schema_version="chunk-v1",
    )
    builder = SqliteFtsIndexBuilder(path, corpus_root=tmp_path)
    candidate = builder.build_candidate(request)
    builder.publish(candidate, _Lease(CatalogRevision(revision)))
    return path


def _published_filter_index(tmp_path: Path) -> Path:
    path = tmp_path / "search-v2.sqlite3"
    reading_id = CollectionId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94751f01"))
    research_id = CollectionId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94751f02"))
    request = IndexBuildRequest(
        documents=(
            _document(
                1,
                "Shared evidence one",
                "Shared evidence from the first paper.",
                authors=("Alice Example",),
                categories=("cs.AI",),
                language="en",
                submitted_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
                collection_ids=(reading_id,),
                collection_slugs=("reading",),
            ),
            _document(
                2,
                "Shared evidence two",
                "Shared evidence from the second paper.",
                authors=("Bob Example",),
                categories=("cs.CL",),
                language="fr",
                submitted_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
                collection_ids=(research_id,),
                collection_slugs=("research",),
            ),
            _document(
                3,
                "Shared evidence three",
                "Shared evidence from the third paper.",
                source_id=SourceId("crossref"),
                authors=("Alice Example", "Carol Example"),
                categories=("biology",),
                language="en",
                submitted_at=datetime(2026, 9, 1, 12, tzinfo=UTC),
            ),
        ),
        catalog_revision=CatalogRevision(5),
        chunk_schema_version="chunk-v1",
    )
    builder = SqliteFtsIndexBuilder(path, corpus_root=tmp_path)
    candidate = builder.build_candidate(request)
    builder.publish(candidate, _Lease(CatalogRevision(5)))
    return path


def test_paper_search_returns_stable_rank_raw_score_revisions_and_counts(
    tmp_path: Path,
) -> None:
    path = _published_index(tmp_path)
    reader = SqliteFtsSearchReader(path, _Catalog(5), corpus_root=tmp_path)
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
    assert first.hits[0].source_id == SourceId("arxiv")
    assert first.hits[0].authors == ("Alice Example", "Bob Researcher")
    assert first.hits[0].identifiers == (
        SearchIdentifier("arxiv", "2608.05678", IdentifierScope.PAPER),
        SearchIdentifier("doi", "10.1234/example.2", IdentifierScope.PAPER),
    )


@pytest.mark.parametrize(
    ("filters", "expected_titles"),
    [
        (SearchFilters(source_id=SourceId("crossref")), {"Shared evidence three"}),
        (SearchFilters(category="cs.AI"), {"Shared evidence one"}),
        (SearchFilters(author="ALICE EXAMPLE"), {"Shared evidence one", "Shared evidence three"}),
        (SearchFilters(language="EN"), {"Shared evidence one", "Shared evidence three"}),
        (
            SearchFilters(date_from=datetime(2026, 8, 15, 12, tzinfo=UTC)),
            {"Shared evidence two", "Shared evidence three"},
        ),
        (
            SearchFilters(date_to=datetime(2026, 8, 15, 12, tzinfo=UTC)),
            {"Shared evidence one", "Shared evidence two"},
        ),
        (SearchFilters(collection="reading"), {"Shared evidence one"}),
        (
            SearchFilters(collection="01890f3e-3b12-7cc0-98d6-4f6f94751f02"),
            {"Shared evidence two"},
        ),
        (
            SearchFilters(
                source_id=SourceId("arxiv"),
                author="bob example",
                language="FR",
                date_from=datetime(2026, 8, 15, 12, tzinfo=UTC),
                date_to=datetime(2026, 8, 15, 12, tzinfo=UTC),
                collection="research",
            ),
            {"Shared evidence two"},
        ),
    ],
)
def test_paper_and_passage_search_apply_closed_filters(
    tmp_path: Path,
    filters: SearchFilters,
    expected_titles: set[str],
) -> None:
    path = _published_filter_index(tmp_path)
    reader = SqliteFtsSearchReader(path, _Catalog(5), corpus_root=tmp_path)

    papers = reader.search_papers(PaperSearchQuery(query="shared evidence", filters=filters))
    passages = reader.search_passages(
        PassageSearchQuery(query="shared evidence", filters=filters, limit=50)
    )

    assert {hit.title for hit in papers.hits} == expected_titles
    assert {str(hit.passage.paper_id) for hit in passages.hits} == {
        str(hit.paper_id) for hit in papers.hits
    }
    assert papers.available == len(expected_titles)
    assert passages.available == 2 * len(expected_titles)


def test_passage_search_and_lookup_preserve_exact_identity_with_bounded_excerpt(
    tmp_path: Path,
) -> None:
    path = _published_index(tmp_path)
    reader = SqliteFtsSearchReader(
        path,
        _Catalog(5),
        corpus_root=tmp_path,
        maximum_excerpt_characters=24,
    )

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
    reader = SqliteFtsSearchReader(path, _Catalog(6), corpus_root=tmp_path)

    result = reader.search_papers(PaperSearchQuery(query="biology"))

    assert result.coverage is CoverageStatus.PARTIAL
    assert result.catalog_revision == CatalogRevision(6)
    assert result.index_revision == CatalogRevision(5)
    assert result.returned == 1


def test_missing_index_is_unavailable_and_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "missing.sqlite3"
    reader = SqliteFtsSearchReader(path, _Catalog(4), corpus_root=tmp_path)

    result = reader.search_papers(PaperSearchQuery(query="evidence"))

    assert result.coverage is CoverageStatus.UNAVAILABLE
    assert result.catalog_revision == CatalogRevision(4)
    assert result.index_revision == CatalogRevision(0)
    assert result.hits == ()
    assert not path.exists()


def test_reader_refuses_outside_root_and_symlink_index_paths(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    outside = tmp_path / "outside.sqlite3"
    corpus_root.mkdir()
    outside.write_bytes(b"not an index")
    linked_index = corpus_root / "linked.sqlite3"
    linked_index.symlink_to(outside)

    with pytest.raises(ValueError, match="confined"):
        SqliteFtsSearchReader(outside, _Catalog(4), corpus_root=corpus_root)
    with pytest.raises(ValueError, match="symbolic"):
        SqliteFtsSearchReader(linked_index, _Catalog(4), corpus_root=corpus_root)


def test_search_database_connection_is_read_only_and_query_only(tmp_path: Path) -> None:
    path = _published_index(tmp_path)

    with open_readonly(path, corpus_root=tmp_path) as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("CREATE TABLE forbidden (id INTEGER)")


def test_reader_uses_validated_descriptor_during_connect_path_aba(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _published_index(tmp_path)
    original_bytes = path.read_bytes()
    attacker_root = tmp_path / "attacker"
    attacker_root.mkdir()
    attacker_path = attacker_root / "search-v1.sqlite3"
    attacker_request = IndexBuildRequest(
        documents=(_document(4, "Injected biology", "This index must never be read."),),
        catalog_revision=CatalogRevision(5),
        chunk_schema_version="chunk-v1",
    )
    attacker_builder = SqliteFtsIndexBuilder(attacker_path, corpus_root=attacker_root)
    attacker_candidate = attacker_builder.build_candidate(attacker_request)
    attacker_builder.publish(attacker_candidate, _Lease(CatalogRevision(5)))
    displaced = tmp_path / "validated.sqlite3"
    real_connect = schema_module.sqlite3.connect
    injected = False

    def connect_during_path_aba(
        database: str | bytes | Path,
        *args: object,
        **kwargs: object,
    ) -> sqlite3.Connection:
        nonlocal injected
        if injected:
            return real_connect(database, *args, **kwargs)  # type: ignore[arg-type]
        injected = True
        path.rename(displaced)
        attacker_path.rename(path)
        try:
            return real_connect(database, *args, **kwargs)  # type: ignore[arg-type]
        finally:
            path.rename(attacker_path)
            displaced.rename(path)

    monkeypatch.setattr(schema_module.sqlite3, "connect", connect_during_path_aba)
    reader = SqliteFtsSearchReader(path, _Catalog(5), corpus_root=tmp_path)

    result = reader.search_papers(PaperSearchQuery(query="biology"))

    assert injected is True
    assert result.returned == 1
    assert result.hits[0].title == "Protein structure"
    assert path.read_bytes() == original_bytes


def test_reader_rejects_an_index_with_an_unknown_self_described_schema(tmp_path: Path) -> None:
    path = _published_index(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute("UPDATE index_meta SET index_schema_version = 'future-v9'")
        connection.commit()
    finally:
        connection.close()

    reader = SqliteFtsSearchReader(path, _Catalog(5), corpus_root=tmp_path)

    with pytest.raises(ValueError, match="unsupported search index schema"):
        reader.search_papers(PaperSearchQuery(query="evidence"))


def test_application_search_service_preserves_reader_results_and_passage_ids(
    tmp_path: Path,
) -> None:
    path = _published_index(tmp_path)
    service = LocalSearch(SqliteFtsSearchReader(path, _Catalog(5), corpus_root=tmp_path))

    papers = service.search_papers(PaperSearchQuery(query="provenance"))
    passages = service.search_passages(PassageSearchQuery(query="provenance"))

    assert papers.returned == 1
    assert passages.returned == 1
    assert service.get_passage(passages.hits[0].passage.passage_id) == passages.hits[0].passage
