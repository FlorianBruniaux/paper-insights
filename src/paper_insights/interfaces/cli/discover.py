from __future__ import annotations

import argparse
from datetime import UTC, datetime

from paper_insights.domain.acquisition import DiscoveryQuery, PreparedDiscovery


def discovery_query(arguments: argparse.Namespace) -> DiscoveryQuery:
    return DiscoveryQuery(
        text=arguments.query,
        categories=tuple(arguments.categories),
        authors=tuple(arguments.authors),
        identifiers=tuple(arguments.identifiers),
        date_from=parse_utc_rfc3339(arguments.date_from),
        date_to=parse_utc_rfc3339(arguments.date_to),
        limit=arguments.limit,
        cursor=arguments.cursor,
    )


def prepared_data(prepared: PreparedDiscovery) -> dict[str, object]:
    preview = prepared.preview
    return {
        "preview": {
            "schema_version": preview.schema_version,
            "source_id": str(preview.source_id),
            "query": preview.query.canonical_data(),
            "requested_records": preview.requested_records,
            "discovered_records": preview.discovered_records,
            "selected_records": preview.selected_records,
            "selected_locators": [
                locator.canonical_data() for locator in preview.selected_locators
            ],
            "issues": [
                {
                    "code": str(issue.code),
                    "message": issue.message,
                    "page_ordinal": issue.page_ordinal,
                    "record_ordinal": issue.record_ordinal,
                }
                for issue in preview.issues
            ],
            "prepared_at": _utc(preview.prepared_at),
            "expires_at": _utc(preview.expires_at),
            "digest": str(preview.digest),
        },
        "records": [
            {
                "source_id": str(record.source_id),
                "source_item_id": record.source_item_id,
                "source_version_key": record.source_version_key,
                "title": record.title,
                "page_ordinal": record.page_ordinal,
                "record_ordinal": record.record_ordinal,
                "source_url": record.source_url,
            }
            for record in prepared.batch.records
        ],
    }


def render_prepared(prepared: PreparedDiscovery, *, as_json: bool) -> str:
    if as_json:
        raise ValueError("JSON envelope rendering belongs to the CLI app")
    preview = prepared.preview
    return (
        f"{preview.source_id}: {preview.selected_records}/{preview.discovered_records} selected\n"
        f"digest: {preview.digest}\n"
    )


def parse_utc_rfc3339(value: str | None) -> datetime | None:
    if value is None:
        return None
    if "T" not in value:
        raise ValueError("date filter requires complete RFC3339 UTC")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("date filter requires UTC")
    return parsed.astimezone(UTC)


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
