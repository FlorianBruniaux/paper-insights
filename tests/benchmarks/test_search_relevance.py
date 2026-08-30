from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

DATASET = Path(__file__).with_name("search_queries.jsonl")
EXPECTED_KEYS = {
    "schema_version",
    "slot",
    "query",
    "expected_relevant_paper_ids",
    "observed_top_five_paper_ids",
    "p0_relevance_failure",
    "reviewer_id",
    "reviewed_at",
}
PAPER_ID = "01890f3e-3b12-7cc0-98d6-4f6f94748f51"


def _records() -> tuple[dict[str, object], ...]:
    return tuple(json.loads(line) for line in DATASET.read_text().splitlines() if line.strip())


def _is_annotated(record: dict[str, object]) -> bool:
    return all(
        record[field] is not None
        for field in (
            "query",
            "expected_relevant_paper_ids",
            "observed_top_five_paper_ids",
            "p0_relevance_failure",
            "reviewer_id",
            "reviewed_at",
        )
    )


def _validate_uuid_list(
    value: object,
    *,
    field: str,
    require_non_empty: bool,
    maximum: int | None = None,
) -> tuple[str, ...]:
    if type(value) is not list:
        raise ValueError(f"{field} must be a JSON list")
    values = cast(list[object], value)
    if require_non_empty and not values:
        raise ValueError(f"{field} cannot be empty")
    if maximum is not None and len(values) > maximum:
        raise ValueError(f"{field} exceeds its maximum length")
    if any(type(item) is not str or not cast(str, item).strip() for item in values):
        raise ValueError(f"{field} must contain non-empty strings")
    strings = tuple(cast(str, item) for item in values)
    if len(set(strings)) != len(strings):
        raise ValueError(f"{field} cannot contain duplicate IDs")
    for item in strings:
        try:
            parsed = UUID(item)
        except ValueError as exc:
            raise ValueError(f"{field} contains an invalid UUID") from exc
        if parsed.version != 7 or str(parsed) != item:
            raise ValueError(f"{field} requires canonical UUIDv7 paper IDs")
    return strings


def _validate_record(record: dict[str, object]) -> bool:
    if set(record) != EXPECTED_KEYS:
        raise ValueError("human relevance record has unknown or missing fields")
    if record["schema_version"] != "search-relevance-v1":
        raise ValueError("human relevance record schema is unsupported")
    slot = record["slot"]
    if type(slot) is not int or not 1 <= cast(int, slot) <= 30:
        raise ValueError("human relevance slot must be an integer from 1 to 30")
    human_fields = (
        "query",
        "expected_relevant_paper_ids",
        "observed_top_five_paper_ids",
        "p0_relevance_failure",
        "reviewer_id",
        "reviewed_at",
    )
    supplied = tuple(record[field] is not None for field in human_fields)
    if not any(supplied):
        return False
    if not all(supplied):
        raise ValueError("human relevance annotation is partial")
    query = record["query"]
    if type(query) is not str or not cast(str, query).strip() or len(cast(str, query)) > 500:
        raise ValueError("human relevance query must contain 1 to 500 characters")
    _validate_uuid_list(
        record["expected_relevant_paper_ids"],
        field="expected_relevant_paper_ids",
        require_non_empty=True,
    )
    _validate_uuid_list(
        record["observed_top_five_paper_ids"],
        field="observed_top_five_paper_ids",
        require_non_empty=False,
        maximum=5,
    )
    if type(record["p0_relevance_failure"]) is not bool:
        raise ValueError("p0_relevance_failure must be a JSON boolean")
    reviewer = record["reviewer_id"]
    if type(reviewer) is not str or not cast(str, reviewer).strip():
        raise ValueError("reviewer_id must be a non-empty string")
    reviewed_at = record["reviewed_at"]
    if type(reviewed_at) is not str or not cast(str, reviewed_at).strip():
        raise ValueError("reviewed_at must be a non-empty UTC timestamp")
    try:
        parsed_at = datetime.fromisoformat(cast(str, reviewed_at))
    except ValueError as exc:
        raise ValueError("reviewed_at must be an ISO 8601 timestamp") from exc
    if parsed_at.utcoffset() != timedelta(0):
        raise ValueError("reviewed_at must use UTC")
    return True


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
