from __future__ import annotations

from uuid import UUID

from paper_insights.domain.corpus import CitationFormat, CitationResult
from paper_insights.domain.identifiers import PaperVersionId


def citation_format(value: str) -> CitationFormat:
    return CitationFormat(value)


def paper_version_id(value: str | None) -> PaperVersionId | None:
    return None if value is None else PaperVersionId(UUID(value))


def citation_data(result: CitationResult) -> dict[str, object]:
    return {
        "schema_version": result.schema_version,
        "paper_id": str(result.paper_id),
        "paper_version_id": str(result.paper_version_id),
        "version_observation_id": str(result.version_observation_id),
        "format": result.format.value,
        "media_type": result.media_type,
        "content": result.content,
        "missing_fields": list(result.missing_fields),
        "source_id": str(result.source_id),
        "source_item_id": result.source_item_id,
        "snapshot_id": str(result.snapshot_id),
        "record_ordinal": result.record_ordinal,
        "retrieved_at": result.retrieved_at.isoformat().replace("+00:00", "Z"),
        "coverage": result.coverage.value,
        "warnings": [warning.value for warning in result.warnings],
    }
