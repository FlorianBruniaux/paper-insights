from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from uuid import UUID

from paper_insights.application.ports.catalog import CatalogReader
from paper_insights.domain.identifiers import (
    PaperId,
    PaperVersionId,
    PassageId,
    Sha256,
    VersionObservationId,
)
from paper_insights.domain.retrieval import (
    CatalogRevision,
    CoverageStatus,
    PaperSearchHit,
    PaperSearchQuery,
    PaperSearchResult,
    PassageIdentity,
    PassageSearchHit,
    PassageSearchQuery,
    PassageSearchResult,
    PassageView,
)

from .schema import (
    confined_absolute,
    open_readonly,
    read_index_receipt_from_connection,
    safe_target_exists,
)

_SEARCH_TOKEN = re.compile(r"\w+", re.UNICODE)


class SqliteFtsSearchReader:
    def __init__(
        self,
        index_path: Path,
        catalog: CatalogReader,
        *,
        corpus_root: Path,
        maximum_excerpt_characters: int = 1_500,
    ) -> None:
        if not 1 <= maximum_excerpt_characters <= 1_500:
            raise ValueError("maximum search excerpt must be between 1 and 1500 characters")
        self._corpus_root, self._index_path = confined_absolute(corpus_root, index_path)
        safe_target_exists(self._corpus_root, self._index_path)
        self._catalog = catalog
        self._maximum_excerpt_characters = maximum_excerpt_characters

    def search_papers(self, query: PaperSearchQuery) -> PaperSearchResult:
        self._reject_filters(query.filters)
        catalog_revision = self._catalog_revision()
        if not safe_target_exists(self._corpus_root, self._index_path):
            return PaperSearchResult(
                hits=(),
                coverage=CoverageStatus.UNAVAILABLE,
                catalog_revision=catalog_revision,
                index_revision=CatalogRevision(0),
                truncated=False,
                returned=0,
                available=0,
                applied_limit=query.limit,
            )
        expression = self._fts_expression(query.query)
        with open_readonly(self._index_path, corpus_root=self._corpus_root) as connection:
            receipt = read_index_receipt_from_connection(connection)
            rows: list[sqlite3.Row]
            if expression is None:
                rows = []
                available = 0
            else:
                available = int(
                    connection.execute(
                        "SELECT count(*) FROM paper_fts WHERE paper_fts MATCH ?",
                        (expression,),
                    ).fetchone()[0]
                )
                rows = connection.execute(
                    "SELECT d.paper_id, d.paper_version_id, d.version_observation_id, "
                    "d.title, d.artifact_sha256, bm25(paper_fts, 10.0, 1.0) AS score "
                    "FROM paper_fts JOIN documents AS d "
                    "ON d.paper_version_id = paper_fts.paper_version_id "
                    "WHERE paper_fts MATCH ? "
                    "ORDER BY score, d.paper_id, d.paper_version_id LIMIT ?",
                    (expression, query.limit),
                ).fetchall()
        hits = tuple(
            PaperSearchHit(
                paper_id=PaperId(UUID(str(row["paper_id"]))),
                paper_version_id=PaperVersionId(UUID(str(row["paper_version_id"]))),
                version_observation_id=VersionObservationId(
                    UUID(str(row["version_observation_id"]))
                ),
                title=str(row["title"]),
                rank=rank,
                bm25_score=float(row["score"]),
                artifact_sha256=Sha256(str(row["artifact_sha256"])),
            )
            for rank, row in enumerate(rows, start=1)
        )
        return PaperSearchResult(
            hits=hits,
            coverage=self._coverage(catalog_revision, receipt.catalog_revision),
            catalog_revision=catalog_revision,
            index_revision=receipt.catalog_revision,
            truncated=available > len(hits),
            returned=len(hits),
            available=available,
            applied_limit=query.limit,
        )

    def search_passages(self, query: PassageSearchQuery) -> PassageSearchResult:
        self._reject_filters(query.filters)
        catalog_revision = self._catalog_revision()
        if not safe_target_exists(self._corpus_root, self._index_path):
            return PassageSearchResult(
                hits=(),
                coverage=CoverageStatus.UNAVAILABLE,
                catalog_revision=catalog_revision,
                index_revision=CatalogRevision(0),
                truncated=False,
                returned=0,
                available=0,
                applied_limit=query.limit,
            )
        expression = self._fts_expression(query.query)
        tokens = self._tokens(query.query)
        with open_readonly(self._index_path, corpus_root=self._corpus_root) as connection:
            receipt = read_index_receipt_from_connection(connection)
            rows: list[sqlite3.Row]
            if expression is None:
                rows = []
                available = 0
            else:
                available = int(
                    connection.execute(
                        "SELECT count(*) FROM passage_fts WHERE passage_fts MATCH ?",
                        (expression,),
                    ).fetchone()[0]
                )
                rows = connection.execute(
                    "SELECT p.passage_id, p.paper_id, p.paper_version_id, "
                    "p.version_observation_id, p.artifact_sha256, p.chunk_schema_version, "
                    "p.section, p.ordinal, p.normalized_text, p.start_offset, p.end_offset, "
                    "bm25(passage_fts) AS score "
                    "FROM passage_fts JOIN passages AS p "
                    "ON p.passage_id = passage_fts.passage_id "
                    "WHERE passage_fts MATCH ? "
                    "ORDER BY score, p.passage_id LIMIT ?",
                    (expression, query.limit),
                ).fetchall()
        hits = tuple(
            PassageSearchHit(
                passage=self._passage_from_row(row),
                rank=rank,
                bm25_score=float(row["score"]),
                excerpt=self._excerpt(str(row["normalized_text"]), tokens),
            )
            for rank, row in enumerate(rows, start=1)
        )
        return PassageSearchResult(
            hits=hits,
            coverage=self._coverage(catalog_revision, receipt.catalog_revision),
            catalog_revision=catalog_revision,
            index_revision=receipt.catalog_revision,
            truncated=available > len(hits),
            returned=len(hits),
            available=available,
            applied_limit=query.limit,
        )

    def get_passage(self, passage_id: PassageId) -> PassageView | None:
        if not safe_target_exists(self._corpus_root, self._index_path):
            return None
        with open_readonly(self._index_path, corpus_root=self._corpus_root) as connection:
            read_index_receipt_from_connection(connection)
            row = connection.execute(
                "SELECT passage_id, paper_id, paper_version_id, version_observation_id, "
                "artifact_sha256, chunk_schema_version, section, ordinal, normalized_text, "
                "start_offset, end_offset FROM passages WHERE passage_id = ?",
                (str(passage_id),),
            ).fetchone()
        return None if row is None else self._passage_from_row(row)

    def _catalog_revision(self) -> CatalogRevision:
        with self._catalog.snapshot() as snapshot:
            revision = snapshot.revision
        return revision

    @staticmethod
    def _tokens(query: str) -> tuple[str, ...]:
        return tuple(_SEARCH_TOKEN.findall(query))

    @classmethod
    def _fts_expression(cls, query: str) -> str | None:
        tokens = cls._tokens(query)
        if not tokens:
            return None
        return " AND ".join(f'"{token}"' for token in tokens)

    @staticmethod
    def _reject_filters(filters: object) -> None:
        from paper_insights.domain.retrieval import SearchFilters

        if filters != SearchFilters():
            raise ValueError("search filters are unsupported by index schema fts-v1")

    @staticmethod
    def _coverage(
        catalog_revision: CatalogRevision, index_revision: CatalogRevision
    ) -> CoverageStatus:
        if catalog_revision == index_revision:
            return CoverageStatus.COMPLETE
        return CoverageStatus.PARTIAL

    @staticmethod
    def _passage_from_row(row: sqlite3.Row) -> PassageView:
        identity = PassageIdentity(
            paper_version_id=PaperVersionId(UUID(str(row["paper_version_id"]))),
            artifact_sha256=Sha256(str(row["artifact_sha256"])),
            chunk_schema_version=str(row["chunk_schema_version"]),
            section=str(row["section"]) if row["section"] is not None else None,
            ordinal=int(row["ordinal"]),
            normalized_text=str(row["normalized_text"]),
            start_offset=int(row["start_offset"]),
            end_offset=int(row["end_offset"]),
        )
        return PassageView(
            passage_id=PassageId(str(row["passage_id"])),
            identity=identity,
            paper_id=PaperId(UUID(str(row["paper_id"]))),
            version_observation_id=VersionObservationId(UUID(str(row["version_observation_id"]))),
            text=identity.normalized_text,
        )

    def _excerpt(self, text: str, tokens: tuple[str, ...]) -> str:
        limit = self._maximum_excerpt_characters
        if len(text) <= limit:
            return text
        folded = text.casefold()
        positions = tuple(
            position for token in tokens if (position := folded.find(token.casefold())) >= 0
        )
        anchor = min(positions, default=0)
        start = max(0, min(anchor - limit // 3, len(text) - limit))
        return text[start : start + limit]
