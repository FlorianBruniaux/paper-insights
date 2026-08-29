from __future__ import annotations

from uuid import UUID

import pytest

from paper_insights.domain.corpus import (
    IngestionItemRef,
    IngestionOutcome,
    IngestionStatus,
    RunCounters,
)
from paper_insights.domain.identifiers import (
    PaperId,
    PaperVersionId,
    RunId,
    SnapshotId,
    VersionObservationId,
)

UUID7 = UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")


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


def test_ingestion_outcomes_are_closed_and_created_paper_is_consistent() -> None:
    with pytest.raises(ValueError):
        IngestionItemRef(
            run_id=RunId(UUID7),
            snapshot_id=SnapshotId(UUID7),
            record_ordinal=0,
            paper_id=PaperId(UUID7),
            paper_version_id=PaperVersionId(UUID7),
            version_observation_id=VersionObservationId(UUID7),
            outcome=IngestionOutcome.UNCHANGED,
            created_paper=True,
        )
