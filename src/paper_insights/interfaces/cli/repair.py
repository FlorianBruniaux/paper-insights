from __future__ import annotations

from paper_insights.application.ingestion.repair import InterruptedRunsPreview
from paper_insights.domain.corpus import InterruptedRunRepairResult


def preview_data(preview: InterruptedRunsPreview) -> dict[str, object]:
    return {
        "cutoff": preview.cutoff.isoformat().replace("+00:00", "Z"),
        "candidates": [
            {
                "run_id": str(candidate.run_id),
                "started_at": candidate.started_at.isoformat().replace("+00:00", "Z"),
                "selected_records": candidate.selected_records,
                "recorded_items": candidate.recorded_items,
            }
            for candidate in preview.candidates
        ],
    }


def repair_results_data(
    results: tuple[InterruptedRunRepairResult, ...],
) -> dict[str, object]:
    return {
        "results": [
            {
                "run_id": str(result.run_id),
                "outcome": result.outcome.value,
                "revision": result.revision,
            }
            for result in results
        ]
    }
