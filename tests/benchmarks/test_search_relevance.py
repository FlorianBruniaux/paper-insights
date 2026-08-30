from __future__ import annotations

import json
from pathlib import Path

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


def test_relevance_dataset_reserves_exactly_thirty_closed_human_review_slots() -> None:
    records = _records()

    assert len(records) == 30
    assert tuple(record["slot"] for record in records) == tuple(range(1, 31))
    assert all(set(record) == EXPECTED_KEYS for record in records)
    assert all(record["schema_version"] == "search-relevance-v1" for record in records)


def test_human_search_relevance_gate() -> None:
    records = _records()
    annotated = tuple(record for record in records if _is_annotated(record))
    if len(annotated) != 30:
        pytest.skip(f"human search relevance gate BLOCKED: {len(annotated)}/30 annotated")

    top_five_matches = sum(
        bool(
            set(record["expected_relevant_paper_ids"])  # type: ignore[arg-type]
            & set(record["observed_top_five_paper_ids"])  # type: ignore[arg-type]
        )
        for record in annotated
    )
    assert top_five_matches >= 24
    assert not any(record["p0_relevance_failure"] is True for record in annotated)
