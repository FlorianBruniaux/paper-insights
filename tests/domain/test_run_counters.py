from __future__ import annotations

import pytest

from paper_insights.domain.corpus import IngestionStatus, RunCounters


def test_run_counters_enforce_exact_sum() -> None:
    counters = RunCounters(
        selected_records=5,
        new_papers=1,
        new_versions=2,
        metadata_updates=1,
        unchanged_records=1,
        failed_records=1,
    )

    assert counters.status is IngestionStatus.PARTIAL


def test_zero_selection_is_success() -> None:
    assert RunCounters.zero().status is IngestionStatus.SUCCEEDED


@pytest.mark.parametrize(
    "values",
    [
        dict(selected_records=-1),
        dict(selected_records=1, unchanged_records=0),
        dict(selected_records=1, new_papers=1, new_versions=0, failed_records=1),
    ],
)
def test_invalid_run_counters_are_rejected(values: dict[str, int]) -> None:
    defaults = dict(
        selected_records=0,
        new_papers=0,
        new_versions=0,
        metadata_updates=0,
        unchanged_records=0,
        failed_records=0,
    )
    defaults.update(values)
    with pytest.raises(ValueError):
        RunCounters(**defaults)
