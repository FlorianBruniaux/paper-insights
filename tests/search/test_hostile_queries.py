from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Literal
from uuid import UUID

import pytest

from paper_insights.adapters.search.sqlite_fts.builder import SqliteFtsIndexBuilder
from paper_insights.adapters.search.sqlite_fts.reader import SqliteFtsSearchReader
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
    IndexBuildRequest,
    IndexDocument,
    PaperSearchQuery,
    SearchFilters,
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


class _Snapshot:
    revision = CatalogRevision(1)

    def __enter__(self) -> _Snapshot:
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
    def snapshot(self) -> _Snapshot:
        return _Snapshot()


def _reader(tmp_path: Path) -> SqliteFtsSearchReader:
    path = tmp_path / "search-v1.sqlite3"
    request = IndexBuildRequest(
        documents=(
            IndexDocument(
                paper_id=PaperId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f51")),
                paper_version_id=PaperVersionId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")),
                version_observation_id=VersionObservationId(
                    UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5b")
                ),
                title="Evidence agents",
                abstract="Safe local search, not biology.",
                metadata_artifact_sha256=Sha256("a" * 64),
            ),
        ),
        catalog_revision=CatalogRevision(1),
        chunk_schema_version="chunk-v1",
    )
    builder = SqliteFtsIndexBuilder(path, corpus_root=tmp_path)
    candidate = builder.build_candidate(request)
    builder.publish(candidate, _Lease(CatalogRevision(1)))
    return SqliteFtsSearchReader(path, _Catalog(), corpus_root=tmp_path)


@pytest.mark.parametrize(
    "hostile_query",
    [
        '"',
        "***",
        "OR",
        "evidence OR biology",
        "NEAR(evidence agents, 999999)",
        "evidence'); DROP TABLE documents; --",
    ],
)
def test_hostile_fts_syntax_is_treated_as_terms_not_as_an_operator_language(
    tmp_path: Path, hostile_query: str
) -> None:
    reader = _reader(tmp_path)

    result = reader.search_papers(PaperSearchQuery(query=hostile_query))
    control = reader.search_papers(PaperSearchQuery(query="evidence"))

    assert result.coverage is CoverageStatus.COMPLETE
    assert control.returned == 1
    if hostile_query == "evidence OR biology":
        assert result.returned == 0


def test_filters_fail_explicitly_until_frozen_index_document_contract_is_extended(
    tmp_path: Path,
) -> None:
    reader = _reader(tmp_path)
    query = PaperSearchQuery(
        query="evidence",
        filters=SearchFilters(source_id=SourceId("arxiv")),
    )

    with pytest.raises(ValueError, match="unsupported by index schema fts-v1"):
        reader.search_papers(query)
