from __future__ import annotations

import re
import sqlite3
import unicodedata
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
    SearchFilters,
)

from .schema import (
    confined_absolute,
    open_readonly,
    read_index_receipt_from_connection,
    safe_target_exists,
)

_SEARCH_TOKEN = re.compile(r"\w+", re.UNICODE)
_DOCUMENT_FILTER_SQL = (
    " AND (? IS NULL OR d.source_id = ?)"
    " AND (? IS NULL OR EXISTS (SELECT 1 FROM document_categories AS dc "
    "WHERE dc.paper_version_id = d.paper_version_id AND dc.category = ?))"
    " AND (? IS NULL OR EXISTS (SELECT 1 FROM document_authors AS da "
    "WHERE da.paper_version_id = d.paper_version_id AND da.name_folded = ?))"
    " AND (? IS NULL OR d.language_folded = ?)"
    " AND (? IS NULL OR d.submitted_at >= ?)"
    " AND (? IS NULL OR d.submitted_at <= ?)"
    " AND (? IS NULL OR EXISTS (SELECT 1 FROM document_collections AS dco_id "
    "WHERE dco_id.paper_version_id = d.paper_version_id AND dco_id.collection_id = ?))"
    " AND (? IS NULL OR EXISTS (SELECT 1 FROM document_collections AS dco_slug "
    "WHERE dco_slug.paper_version_id = d.paper_version_id AND dco_slug.slug = ?))"
)
_PAPER_COUNT_SQL = (
    "SELECT count(*) FROM paper_fts JOIN documents AS d "  # noqa: S608
    "ON d.paper_version_id = paper_fts.paper_version_id "
    "WHERE paper_fts MATCH ?" + _DOCUMENT_FILTER_SQL
)
_PAPER_SEARCH_SQL = (
    "SELECT d.paper_id, d.paper_version_id, d.version_observation_id, "
    "d.title, d.artifact_sha256, bm25(paper_fts, 10.0, 1.0) AS score "
    "FROM paper_fts JOIN documents AS d "
    "ON d.paper_version_id = paper_fts.paper_version_id "
    "WHERE paper_fts MATCH ?"
    + _DOCUMENT_FILTER_SQL
    + " ORDER BY score, d.paper_id, d.paper_version_id LIMIT ?"
)
_PASSAGE_COUNT_SQL = (
    "SELECT count(*) FROM passage_fts JOIN passages AS p "  # noqa: S608
    "ON p.passage_id = passage_fts.passage_id "
    "JOIN documents AS d ON d.paper_version_id = p.paper_version_id "
    "WHERE passage_fts MATCH ?" + _DOCUMENT_FILTER_SQL
)
_PASSAGE_SEARCH_SQL = (
    "SELECT p.passage_id, p.paper_id, p.paper_version_id, "
    "p.version_observation_id, p.artifact_sha256, p.chunk_schema_version, "
    "p.section, p.ordinal, p.normalized_text, p.start_offset, p.end_offset, "
    "bm25(passage_fts) AS score "
    "FROM passage_fts JOIN passages AS p "
    "ON p.passage_id = passage_fts.passage_id "
    "JOIN documents AS d ON d.paper_version_id = p.paper_version_id "
    "WHERE passage_fts MATCH ?" + _DOCUMENT_FILTER_SQL + " ORDER BY score, p.passage_id LIMIT ?"
)


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
        filter_parameters = self._document_filter_parameters(query.filters)
        with open_readonly(self._index_path, corpus_root=self._corpus_root) as connection:
            receipt = read_index_receipt_from_connection(connection)
            rows: list[sqlite3.Row]
            if expression is None:
                rows = []
                available = 0
            else:
                available = int(
                    connection.execute(
                        _PAPER_COUNT_SQL,
                        (expression, *filter_parameters),
                    ).fetchone()[0]
                )
                rows = connection.execute(
                    _PAPER_SEARCH_SQL,
                    (expression, *filter_parameters, query.limit),
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
        filter_parameters = self._document_filter_parameters(query.filters)
        with open_readonly(self._index_path, corpus_root=self._corpus_root) as connection:
            receipt = read_index_receipt_from_connection(connection)
            rows: list[sqlite3.Row]
            if expression is None:
                rows = []
                available = 0
            else:
                available = int(
                    connection.execute(
                        _PASSAGE_COUNT_SQL,
                        (expression, *filter_parameters),
                    ).fetchone()[0]
                )
                rows = connection.execute(
                    _PASSAGE_SEARCH_SQL,
                    (expression, *filter_parameters, query.limit),
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
    def _document_filter_parameters(filters: SearchFilters) -> tuple[str | None, ...]:
        source = str(filters.source_id) if filters.source_id is not None else None
        author = (
            unicodedata.normalize("NFC", filters.author).casefold()
            if filters.author is not None
            else None
        )
        language = (
            unicodedata.normalize("NFC", filters.language).casefold()
            if filters.language is not None
            else None
        )
        date_from = filters.date_from.isoformat() if filters.date_from is not None else None
        date_to = filters.date_to.isoformat() if filters.date_to is not None else None
        collection_id, collection_slug = SqliteFtsSearchReader._collection_selector(
            filters.collection
        )
        return (
            source,
            source,
            filters.category,
            filters.category,
            author,
            author,
            language,
            language,
            date_from,
            date_from,
            date_to,
            date_to,
            collection_id,
            collection_id,
            collection_slug,
            collection_slug,
        )

    @staticmethod
    def _collection_selector(value: str | None) -> tuple[str | None, str | None]:
        if value is None:
            return None, None
        try:
            collection_id = str(UUID(value))
        except ValueError:
            return None, value
        return collection_id, None

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
