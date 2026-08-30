from __future__ import annotations

from paper_insights.domain.retrieval import PublishedIndex


def published_index_data(index: PublishedIndex) -> dict[str, object]:
    return {
        "path": str(index.path),
        "catalog_revision": index.catalog_revision.value,
        "generation": index.generation,
    }
