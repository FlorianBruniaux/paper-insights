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
        "applied_limit": result.applied_limit,
        "hits": [
            {
                "paper_id": str(hit.paper_id),
                "paper_version_id": str(hit.paper_version_id),
                "version_observation_id": str(hit.version_observation_id),
                "title": hit.title,
                "rank": hit.rank,
                "bm25_score": hit.bm25_score,
                "artifact_sha256": str(hit.artifact_sha256),
                "source_id": str(hit.source_id),
                "authors": list(hit.authors),
                "identifiers": [
                    {
                        "scheme": identifier.scheme,
                        "canonical_value": identifier.canonical_value,
                        "scope": identifier.scope.value,
                    }
                    for identifier in hit.identifiers
                ],
            }
            for hit in result.hits
        ],
    }


def render_paper_result(result: PaperSearchResult) -> str:
    available = "unknown" if result.available is None else str(result.available)
    lines = [
        "search.papers | "
        f"catalog_revision={result.catalog_revision.value} | "
        f"index_revision={result.index_revision.value} | "
        f"coverage={result.coverage.value} | returned={result.returned} | "
        f"available={available} | truncated={str(result.truncated).lower()} | "
        f"applied_limit={result.applied_limit}"
    ]
    for hit in result.hits:
        authors = ", ".join(hit.authors)
        identifiers = ", ".join(
            f"{item.scheme}:{item.canonical_value} [{item.scope.value}]" for item in hit.identifiers
        )
        lines.append(
            f"{hit.rank}. {hit.title} | paper_id={hit.paper_id} | "
            f"paper_version_id={hit.paper_version_id} | "
            f"version_observation_id={hit.version_observation_id} | "
            f"bm25_score={hit.bm25_score} | artifact_sha256={hit.artifact_sha256} | "
            f"source={hit.source_id} | "
            f"authors=[{authors}] | identifiers=[{identifiers}]"
        )
    return "\n".join(lines) + "\n"


def passage_result_data(result: PassageSearchResult) -> dict[str, object]:
    return {
        "catalog_revision": result.catalog_revision.value,
        "index_revision": result.index_revision.value,
        "applied_limit": result.applied_limit,
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
