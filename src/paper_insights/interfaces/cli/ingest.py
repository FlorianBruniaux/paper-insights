from __future__ import annotations

from paper_insights.domain.corpus import IngestionSummary


def ingestion_data(summary: IngestionSummary) -> dict[str, object]:
    counters = summary.counters
    return {
        "run_id": str(summary.run_id),
        "counters": {
            "selected_records": counters.selected_records,
            "new_papers": counters.new_papers,
            "new_versions": counters.new_versions,
            "metadata_updates": counters.metadata_updates,
            "unchanged_records": counters.unchanged_records,
            "failed_records": counters.failed_records,
            "status": str(counters.status),
        },
    }
