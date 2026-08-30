from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from paper_insights.benchmarks.search_relevance import (
    RelevanceRecordState,
    parse_relevance_record,
)

DATASET = Path(__file__).with_name("search_queries.jsonl")
PAPER_ID = "01890f3e-3b12-7cc0-98d6-4f6f94748f51"


def _records() -> tuple[dict[str, object], ...]:
    return tuple(json.loads(line) for line in DATASET.read_text().splitlines() if line.strip())


def _is_annotated(record: dict[str, object]) -> bool:
    return parse_relevance_record(record).state is RelevanceRecordState.REVIEWED


def _validate_record(record: dict[str, object]) -> bool:
    return parse_relevance_record(record).state is RelevanceRecordState.REVIEWED


def _validate_dataset(records: tuple[dict[str, object], ...]) -> None:
    if len(records) != 30:
        raise ValueError("human relevance dataset requires exactly 30 slots")
    slots: list[int] = []
    for record in records:
        _validate_record(record)
        slots.append(cast(int, record["slot"]))
    if tuple(slots) != tuple(range(1, 31)):
        raise ValueError("human relevance dataset slots must be unique and ordered 1..30")


def _complete_record() -> dict[str, object]:
    return {
        "schema_version": "search-relevance-v1",
        "slot": 1,
        "query": "agent evaluation",
        "expected_relevant_paper_ids": [PAPER_ID],
        "observed_top_five_paper_ids": [PAPER_ID],
        "p0_relevance_failure": False,
        "reviewer_id": "human-reviewer",
        "reviewed_at": "2026-08-30T12:00:00+00:00",
    }


def test_relevance_dataset_reserves_exactly_thirty_closed_human_review_slots() -> None:
    records = _records()

    _validate_dataset(records)


@pytest.mark.parametrize(
    ("field", "malformed"),
    [
        ("slot", True),
        ("query", ""),
        ("expected_relevant_paper_ids", []),
        ("expected_relevant_paper_ids", [PAPER_ID, PAPER_ID]),
        ("expected_relevant_paper_ids", ["12345678-1234-4234-9234-123456789abc"]),
        ("observed_top_five_paper_ids", [PAPER_ID] * 6),
        ("p0_relevance_failure", 1),
        ("reviewer_id", "  "),
        ("reviewed_at", "2026-08-30T12:00:00"),
    ],
)
def test_malformed_human_annotation_is_rejected(field: str, malformed: object) -> None:
    record = _complete_record()
    record[field] = malformed

    with pytest.raises(ValueError):
        _validate_record(record)


def test_partial_human_annotation_is_rejected_instead_of_counted_as_pending() -> None:
    record = _complete_record()
    record["reviewed_at"] = None

    with pytest.raises(ValueError, match="partial"):
        _validate_record(record)


def test_prepared_truth_and_machine_observations_do_not_count_as_human_review() -> None:
    prepared = _complete_record()
    prepared["observed_top_five_paper_ids"] = None
    prepared["p0_relevance_failure"] = None
    prepared["reviewer_id"] = None
    prepared["reviewed_at"] = None
    executed = prepared | {"observed_top_five_paper_ids": [PAPER_ID]}

    assert _validate_record(prepared) is False
    assert _validate_record(executed) is False


def test_duplicate_dataset_slots_are_rejected() -> None:
    records = tuple(_complete_record() | {"slot": slot} for slot in range(1, 31))
    duplicate = (*records[:-1], records[-1] | {"slot": 29})

    with pytest.raises(ValueError, match="slots"):
        _validate_dataset(duplicate)


def test_human_search_relevance_gate() -> None:
    records = _records()
    _validate_dataset(records)
    annotated = tuple(record for record in records if _is_annotated(record))
    if len(annotated) != 30:
        pytest.skip(f"human search relevance gate BLOCKED: {len(annotated)}/30 annotated")

    top_five_matches = sum(
        bool(
            set(cast(list[str], record["expected_relevant_paper_ids"]))
            & set(cast(list[str], record["observed_top_five_paper_ids"]))
        )
        for record in annotated
    )
    assert top_five_matches >= 24
    assert not any(record["p0_relevance_failure"] is True for record in annotated)
