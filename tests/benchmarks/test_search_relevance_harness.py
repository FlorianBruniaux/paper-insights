from __future__ import annotations

import io
import json
import sqlite3
from collections import deque
from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from alembic.config import Config

from alembic import command
from paper_insights.benchmarks.search_relevance import (
    IncompleteHumanReview,
    RelevanceRecordState,
    evaluate_relevance_gate,
    load_relevance_dataset,
    main,
    parse_relevance_record,
)
from paper_insights.bootstrap import discover_service, index_service, ingestion_service
from paper_insights.interfaces.cli.app import run

PAPER_ID = "01890f3e-3b12-7cc0-98d6-4f6f94748f51"
OTHER_PAPER_ID = "01890f3e-3b12-7cc0-98d6-4f6f94748f52"
ROOT = Path(__file__).resolve().parents[2]
ARXIV_FIXTURE = ROOT / "tests" / "fixtures" / "arxiv" / "page-1.xml"


@dataclass(frozen=True, slots=True)
class _Corpus:
    root: Path
    catalog: Path
    index: Path
    agents_paper_id: str
    search_paper_id: str


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 8, 30, 8, 0, tzinfo=UTC)


class _Ids:
    def __init__(self) -> None:
        self._values = deque(
            UUID(f"01890f3c-0000-7000-8000-{value:012d}") for value in range(1, 100)
        )

    def new(self) -> UUID:
        return self._values.popleft()


def _migrate(database: Path) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")


@pytest.fixture
def corpus(tmp_path: Path) -> _Corpus:
    root = tmp_path / "corpus"
    root.mkdir()
    catalog = root / "catalog.sqlite3"
    _migrate(catalog)
    clock = _Clock()
    ids = _Ids()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            content=ARXIV_FIXTURE.read_bytes(),
            request=request,
        )
    )

    def invoke(arguments: list[str]) -> int:
        return run(
            arguments,
            doctor_service_factory=lambda _settings: (_ for _ in ()).throw(
                AssertionError("benchmark fixture called doctor")
            ),
            discover_service_factory=lambda settings, source: discover_service(
                settings,
                source,
                transport=transport,
                clock=clock,
                new_capture_id=lambda: UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a"),
            ),
            ingestion_service_factory=lambda settings: ingestion_service(
                settings,
                clock=clock,
                ids=ids,
            ),
            index_service_factory=index_service,
            environ={"PAPER_INSIGHTS_DATA_ROOT": str(root)},
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

    assert invoke(["ingest", "arxiv", "agents", "--limit", "2", "--yes", "--json"]) == 0
    assert invoke(["index", "rebuild", "--json"]) == 0
    with closing(sqlite3.connect(catalog)) as connection:
        rows = connection.execute(
            "SELECT p.id, vo.title FROM papers AS p "
            "JOIN paper_versions AS pv ON pv.paper_id = p.id "
            "JOIN version_observations AS vo ON vo.paper_version_id = pv.id "
            "ORDER BY vo.title"
        ).fetchall()
    title_to_id = {str(title): str(paper_id) for paper_id, title in rows}
    return _Corpus(
        root=root,
        catalog=catalog,
        index=root / ".search" / "search-v1.sqlite3",
        agents_paper_id=title_to_id["Reliable Paper Agents"],
        search_paper_id=title_to_id["Local Search Without Embeddings"],
    )


def _write_prepared_queries(
    path: Path,
    corpus: _Corpus,
    *,
    wrong_expected: bool = True,
    include_empty_result: bool = True,
) -> None:
    records = []
    for slot in range(1, 31):
        query = (
            "zzzz-not-present"
            if include_empty_result and slot == 30
            else ("Agents" if slot % 2 else "Search")
        )
        observed_paper_id = corpus.agents_paper_id if slot % 2 else corpus.search_paper_id
        other_paper_id = corpus.search_paper_id if slot % 2 else corpus.agents_paper_id
        records.append(
            {
                "schema_version": "search-relevance-v1",
                "slot": slot,
                "query": query,
                "expected_relevant_paper_ids": [
                    other_paper_id if wrong_expected else observed_paper_id
                ],
                "observed_top_five_paper_ids": None,
                "p0_relevance_failure": None,
                "reviewer_id": None,
                "reviewed_at": None,
            }
        )
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _jsonl(path: Path) -> tuple[dict[str, object], ...]:
    return tuple(json.loads(line) for line in path.read_text().splitlines() if line.strip())


def _write_review_records(
    path: Path,
    *,
    matches: int,
    reviewed: bool,
    p0_slots: frozenset[int] = frozenset(),
) -> None:
    records = []
    for slot in range(1, 31):
        records.append(
            {
                "schema_version": "search-relevance-v1",
                "slot": slot,
                "query": f"query {slot}",
                "expected_relevant_paper_ids": [PAPER_ID],
                "observed_top_five_paper_ids": [PAPER_ID if slot <= matches else OTHER_PAPER_ID],
                "p0_relevance_failure": (slot in p0_slots) if reviewed else None,
                "reviewer_id": "human-reviewer" if reviewed else None,
                "reviewed_at": "2026-08-30T12:00:00+00:00" if reviewed else None,
            }
        )
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _prepared_record() -> dict[str, object]:
    return {
        "schema_version": "search-relevance-v1",
        "slot": 1,
        "query": "agent evaluation",
        "expected_relevant_paper_ids": [PAPER_ID],
        "observed_top_five_paper_ids": None,
        "p0_relevance_failure": None,
        "reviewer_id": None,
        "reviewed_at": None,
    }


def test_prepared_human_truth_keeps_observations_and_review_unset() -> None:
    record = parse_relevance_record(_prepared_record())

    assert record.state is RelevanceRecordState.PREPARED
    assert record.observed_top_five_paper_ids is None
    assert record.p0_relevance_failure is None
    assert record.reviewer_id is None
    assert record.reviewed_at is None


def test_partial_human_review_is_rejected() -> None:
    partial = deepcopy(_prepared_record())
    partial["observed_top_five_paper_ids"] = [PAPER_ID]
    partial["reviewer_id"] = "reviewer"

    with pytest.raises(ValueError, match="partial human review"):
        parse_relevance_record(partial)


def test_inventory_is_blind_and_bound_to_explicit_catalog_and_index(
    corpus: _Corpus, tmp_path: Path
) -> None:
    output = tmp_path / "output" / "search-relevance" / "fixture"

    code = main(
        [
            "inventory",
            "--catalog",
            str(corpus.catalog),
            "--index",
            str(corpus.index),
            "--output-dir",
            str(output),
        ]
    )

    assert code == 0
    inventory = _jsonl(output / "corpus_inventory.jsonl")
    assert len(inventory) == 2
    assert [row["paper_id"] for row in inventory] == sorted(
        (corpus.agents_paper_id, corpus.search_paper_id)
    )
    forbidden = {
        "query",
        "rank",
        "bm25_score",
        "expected_relevant_paper_ids",
        "observed_top_five_paper_ids",
        "p0_relevance_failure",
        "reviewer_id",
    }
    assert all(not forbidden.intersection(row) for row in inventory)
    manifest = json.loads((output / "inventory_manifest.json").read_text())
    assert manifest["catalog"]["path"] == str(corpus.catalog)
    assert manifest["index"]["path"] == str(corpus.index)
    assert manifest["catalog"]["sha256"] == sha256(corpus.catalog.read_bytes()).hexdigest()
    assert manifest["index"]["sha256"] == sha256(corpus.index.read_bytes()).hexdigest()


def test_inventory_refuses_a_catalog_path_supplied_through_a_symlink(
    corpus: _Corpus, tmp_path: Path
) -> None:
    catalog_link = corpus.root / "catalog-link.sqlite3"
    catalog_link.symlink_to(corpus.catalog)

    code = main(
        [
            "inventory",
            "--catalog",
            str(catalog_link),
            "--index",
            str(corpus.index),
            "--output-dir",
            str(tmp_path / "output" / "search-relevance" / "symlink"),
        ]
    )

    assert code == 2


def test_run_executes_thirty_queries_without_mutating_truth_or_prefilling_review(
    corpus: _Corpus, tmp_path: Path
) -> None:
    output = tmp_path / "output" / "search-relevance" / "fixture"
    queries = tmp_path / "prepared_queries.jsonl"
    _write_prepared_queries(queries, corpus)
    truth_before = queries.read_bytes()
    assert (
        main(
            [
                "inventory",
                "--catalog",
                str(corpus.catalog),
                "--index",
                str(corpus.index),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )

    code = main(
        [
            "run",
            "--catalog",
            str(corpus.catalog),
            "--index",
            str(corpus.index),
            "--queries",
            str(queries),
            "--output-dir",
            str(output),
        ]
    )

    assert code == 0
    assert queries.read_bytes() == truth_before
    observed = _jsonl(output / "observed_results.jsonl")
    assert len(observed) == 30
    assert observed[0]["observed_top_five_paper_ids"] == [corpus.agents_paper_id]
    assert observed[1]["observed_top_five_paper_ids"] == [corpus.search_paper_id]
    assert observed[-1]["observed_top_five_paper_ids"] == []
    assert all("expected_relevant_paper_ids" not in record for record in observed)
    review_records = _jsonl(output / "review_records.jsonl")
    assert len(review_records) == 30
    assert all(record["reviewer_id"] is None for record in review_records)
    assert all(record["p0_relevance_failure"] is None for record in review_records)
    assert all(record["reviewed_at"] is None for record in review_records)
    assert all("approval" not in record for record in review_records)
    form = (output / "review_form.md").read_text()
    assert "Reviewer ID: ____________________" in form
    assert "P0 relevance failure: [ ] true  [ ] false" in form
    assert "Observed top-five paper IDs:\n- None" in form
    assert "approval: true" not in form.casefold()


def test_run_refuses_catalog_index_drift_after_blind_inventory(
    corpus: _Corpus, tmp_path: Path
) -> None:
    output = tmp_path / "output" / "search-relevance" / "fixture"
    queries = tmp_path / "prepared_queries.jsonl"
    _write_prepared_queries(queries, corpus)
    assert (
        main(
            [
                "inventory",
                "--catalog",
                str(corpus.catalog),
                "--index",
                str(corpus.index),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    with closing(sqlite3.connect(corpus.catalog)) as connection:
        connection.execute("UPDATE catalog_meta SET revision = revision + 1 WHERE singleton_id = 1")
        connection.commit()

    code = main(
        [
            "run",
            "--catalog",
            str(corpus.catalog),
            "--index",
            str(corpus.index),
            "--queries",
            str(queries),
            "--output-dir",
            str(output),
        ]
    )

    assert code == 2
    assert not (output / "observed_results.jsonl").exists()


def test_validate_review_refuses_executed_but_unreviewed_records(
    tmp_path: Path,
) -> None:
    reviews = tmp_path / "reviews.jsonl"
    _write_review_records(reviews, matches=30, reviewed=False)

    with pytest.raises(IncompleteHumanReview, match="BLOCKED"):
        evaluate_relevance_gate(load_relevance_dataset(reviews))


@pytest.mark.parametrize(
    ("matches", "p0_slots"),
    [(23, frozenset()), (30, frozenset({1}))],
)
def test_validate_review_fails_closed_below_threshold_or_with_p0(
    matches: int,
    p0_slots: frozenset[int],
    tmp_path: Path,
) -> None:
    reviews = tmp_path / "reviews.jsonl"
    _write_review_records(reviews, matches=matches, reviewed=True, p0_slots=p0_slots)

    evaluation = evaluate_relevance_gate(load_relevance_dataset(reviews))

    assert evaluation.criteria_satisfied is False


def test_validate_review_reports_satisfied_criteria_without_approval(
    tmp_path: Path,
) -> None:
    reviews = tmp_path / "reviews.jsonl"
    _write_review_records(reviews, matches=24, reviewed=True)

    evaluation = evaluate_relevance_gate(load_relevance_dataset(reviews))

    assert evaluation.criteria_satisfied is True


def test_validate_review_binds_completed_records_to_truth_and_observations(
    corpus: _Corpus,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "output" / "search-relevance" / "bound-review"
    queries = tmp_path / "prepared_queries.jsonl"
    _write_prepared_queries(
        queries,
        corpus,
        wrong_expected=False,
        include_empty_result=False,
    )
    assert (
        main(
            [
                "inventory",
                "--catalog",
                str(corpus.catalog),
                "--index",
                str(corpus.index),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "run",
                "--catalog",
                str(corpus.catalog),
                "--index",
                str(corpus.index),
                "--queries",
                str(queries),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    completed = list(_jsonl(output / "review_records.jsonl"))
    for record in completed:
        record["p0_relevance_failure"] = False
        record["reviewer_id"] = "human-reviewer"
        record["reviewed_at"] = "2026-08-30T12:00:00+00:00"
    completed_path = tmp_path / "completed_reviews.jsonl"
    completed_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in completed),
        encoding="utf-8",
    )

    valid_code = main(
        [
            "validate-review",
            "--reviews",
            str(completed_path),
            "--run-manifest",
            str(output / "run_manifest.json"),
        ]
    )

    assert valid_code == 0
    assert "SATISFIED" in capsys.readouterr().out
    completed[0]["query"] = "tampered query"
    completed_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in completed),
        encoding="utf-8",
    )

    tampered_code = main(
        [
            "validate-review",
            "--reviews",
            str(completed_path),
            "--run-manifest",
            str(output / "run_manifest.json"),
        ]
    )

    assert tampered_code == 2
