from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from paper_insights.application.research.collections import CollectionService
from paper_insights.domain.corpus import CollectionView
from paper_insights.domain.identifiers import CollectionId, PaperId, PaperSelector


def collection_data(collection: CollectionView) -> dict[str, object]:
    return {
        "collection_id": str(collection.collection_id),
        "slug": collection.slug,
        "title": collection.title,
        "paper_count": collection.paper_count,
        "created_at": _utc(collection.created_at),
        "updated_at": _utc(collection.updated_at),
    }


def resolve_collection(service: CollectionService, value: str) -> CollectionId:
    try:
        parsed = UUID(value)
    except ValueError as exc:
        matches = tuple(item for item in service.list() if item.slug == value)
        if len(matches) != 1:
            raise LookupError("collection does not exist") from exc
        return matches[0].collection_id
    return CollectionId(parsed)


def paper_selector(value: str) -> PaperSelector:
    if value.startswith("arxiv:"):
        return PaperSelector.by_arxiv(value.removeprefix("arxiv:"))
    if value.startswith("doi:"):
        return PaperSelector.by_doi(value.removeprefix("doi:").lower())
    try:
        return PaperSelector(paper_id=PaperId(UUID(value)))
    except ValueError:
        return PaperSelector.by_arxiv(value)


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
