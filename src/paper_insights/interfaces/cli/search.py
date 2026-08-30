from __future__ import annotations

import argparse

from paper_insights.domain.identifiers import SourceId
from paper_insights.domain.retrieval import (
    PaperSearchQuery,
    PaperSearchResult,
    PassageSearchQuery,
    PassageSearchResult,
    SearchFilters,
)
from paper_insights.interfaces.cli.discover import parse_utc_date


def paper_query(arguments: argparse.Namespace) -> PaperSearchQuery:
    return PaperSearchQuery(
        query=arguments.query,
        filters=_filters(arguments),
        limit=arguments.limit,
    )


def passage_query(arguments: argparse.Namespace) -> PassageSearchQuery:
    return PassageSearchQuery(
        query=arguments.query,
        filters=_filters(arguments),
        limit=arguments.limit,
    )


def paper_result_data(result: PaperSearchResult) -> dict[str, object]:
    return {
        "catalog_revision": result.catalog_revision.value,
        "index_revision": result.index_revision.value,
        "hits": [
            {
                "paper_id": str(hit.paper_id),
                "paper_version_id": str(hit.paper_version_id),
                "version_observation_id": str(hit.version_observation_id),
                "title": hit.title,
                "rank": hit.rank,
                "bm25_score": hit.bm25_score,
                "artifact_sha256": str(hit.artifact_sha256),
            }
            for hit in result.hits
        ],
    }


def passage_result_data(result: PassageSearchResult) -> dict[str, object]:
    return {
        "catalog_revision": result.catalog_revision.value,
        "index_revision": result.index_revision.value,
        "hits": [
            {
                "passage_id": str(hit.passage.passage_id),
                "paper_id": str(hit.passage.paper_id),
                "paper_version_id": str(hit.passage.identity.paper_version_id),
                "version_observation_id": str(hit.passage.version_observation_id),
                "rank": hit.rank,
                "bm25_score": hit.bm25_score,
                "excerpt": hit.excerpt,
                "section": hit.passage.identity.section,
                "ordinal": hit.passage.identity.ordinal,
            }
            for hit in result.hits
        ],
    }


def _filters(arguments: argparse.Namespace) -> SearchFilters:
    return SearchFilters(
        source_id=SourceId(arguments.source) if arguments.source else None,
        category=arguments.category,
        author=arguments.author,
        language=arguments.language,
        date_from=parse_utc_date(arguments.date_from),
        date_to=parse_utc_date(arguments.date_to, inclusive_end=True),
        collection=arguments.collection,
    )
