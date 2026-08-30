from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import cast
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from paper_insights.adapters.catalog.sqlite.engine import create_catalog_engine
from paper_insights.adapters.catalog.sqlite.readers import SqliteCatalogReader
from paper_insights.adapters.search.sqlite_fts.reader import SqliteFtsSearchReader
from paper_insights.adapters.search.sqlite_fts.schema import read_index_receipt
from paper_insights.domain.retrieval import (
    CoverageStatus,
    IndexDocument,
    IndexReceipt,
    PaperSearchQuery,
)

RELEVANCE_SCHEMA_VERSION = "search-relevance-v1"
RELEVANCE_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "slot",
        "query",
        "expected_relevant_paper_ids",
        "observed_top_five_paper_ids",
        "p0_relevance_failure",
        "reviewer_id",
        "reviewed_at",
    }
)
OBSERVED_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "slot",
        "query",
        "observed_top_five_paper_ids",
        "coverage",
        "catalog_revision",
        "index_revision",
        "returned",
        "available",
        "truncated",
    }
)


class RelevanceRecordState(StrEnum):
    BLANK = "blank"
    PREPARED = "prepared"
    EXECUTED = "executed"
    REVIEWED = "reviewed"


@dataclass(frozen=True, slots=True)
class RelevanceRecord:
    slot: int
    query: str | None
    expected_relevant_paper_ids: tuple[str, ...] | None
    observed_top_five_paper_ids: tuple[str, ...] | None
    p0_relevance_failure: bool | None
    reviewer_id: str | None
    reviewed_at: datetime | None
    state: RelevanceRecordState


@dataclass(frozen=True, slots=True)
class CorpusEvidence:
    root: Path
    catalog_path: Path
    index_path: Path
    catalog_sha256: str
    index_sha256: str
    documents: tuple[IndexDocument, ...]
    receipt: IndexReceipt


@dataclass(frozen=True, slots=True)
class RelevanceGateEvaluation:
    reviewed: int
    top_five_matches: int
    p0_failures: int

    @property
    def criteria_satisfied(self) -> bool:
        return self.reviewed == 30 and self.top_five_matches >= 24 and self.p0_failures == 0


class IncompleteHumanReview(ValueError):
    pass


class _CatalogRuntime:
    def __init__(self, catalog_path: Path) -> None:
        self._catalog_path = catalog_path
        self.engine: Engine | None = None
        self.reader: SqliteCatalogReader | None = None

    def __enter__(self) -> _CatalogRuntime:
        engine = create_catalog_engine(self._catalog_path)
        self.engine = engine
        self.reader = SqliteCatalogReader(engine)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        if self.engine is not None:
            self.engine.dispose()

    def require_reader(self) -> SqliteCatalogReader:
        if self.reader is None:
            raise RuntimeError("catalog runtime is not open")
        return self.reader


def _uuidv7_list(
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
    if any(type(item) is not str or not item.strip() for item in values):
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


def parse_relevance_record(value: dict[str, object]) -> RelevanceRecord:
    if set(value) != RELEVANCE_RECORD_KEYS:
        raise ValueError("human relevance record has unknown or missing fields")
    if value["schema_version"] != RELEVANCE_SCHEMA_VERSION:
        raise ValueError("human relevance record schema is unsupported")
    slot = value["slot"]
    if type(slot) is not int or not 1 <= slot <= 30:
        raise ValueError("human relevance slot must be an integer from 1 to 30")

    query_value = value["query"]
    expected_value = value["expected_relevant_paper_ids"]
    prepared_fields = (query_value is not None, expected_value is not None)
    if any(prepared_fields) and not all(prepared_fields):
        raise ValueError("human relevance truth is partial")
    query: str | None = None
    expected: tuple[str, ...] | None = None
    if all(prepared_fields):
        if type(query_value) is not str or not query_value.strip() or len(query_value) > 500:
            raise ValueError("human relevance query must contain 1 to 500 characters")
        query = query_value
        expected = _uuidv7_list(
            expected_value,
            field="expected_relevant_paper_ids",
            require_non_empty=True,
        )

    observed_value = value["observed_top_five_paper_ids"]
    observed = (
        None
        if observed_value is None
        else _uuidv7_list(
            observed_value,
            field="observed_top_five_paper_ids",
            require_non_empty=False,
            maximum=5,
        )
    )
    if observed is not None and query is None:
        raise ValueError("observed search results require prepared human truth")

    p0_value = value["p0_relevance_failure"]
    reviewer_value = value["reviewer_id"]
    reviewed_at_value = value["reviewed_at"]
    review_fields = (
        p0_value is not None,
        reviewer_value is not None,
        reviewed_at_value is not None,
    )
    if any(review_fields) and not all(review_fields):
        raise ValueError("partial human review is not allowed")

    p0: bool | None = None
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    if all(review_fields):
        if observed is None:
            raise ValueError("human review requires observed search results")
        if type(p0_value) is not bool:
            raise ValueError("p0_relevance_failure must be a JSON boolean")
        if type(reviewer_value) is not str or not reviewer_value.strip():
            raise ValueError("reviewer_id must be a non-empty string")
        if type(reviewed_at_value) is not str or not reviewed_at_value.strip():
            raise ValueError("reviewed_at must be a non-empty UTC timestamp")
        try:
            parsed_at = datetime.fromisoformat(reviewed_at_value)
        except ValueError as exc:
            raise ValueError("reviewed_at must be an ISO 8601 timestamp") from exc
        if parsed_at.utcoffset() != timedelta(0):
            raise ValueError("reviewed_at must use UTC")
        p0 = p0_value
        reviewer = reviewer_value
        reviewed_at = parsed_at

    if reviewed_at is not None:
        state = RelevanceRecordState.REVIEWED
    elif observed is not None:
        state = RelevanceRecordState.EXECUTED
    elif query is not None:
        state = RelevanceRecordState.PREPARED
    else:
        state = RelevanceRecordState.BLANK
    return RelevanceRecord(
        slot=slot,
        query=query,
        expected_relevant_paper_ids=expected,
        observed_top_five_paper_ids=observed,
        p0_relevance_failure=p0,
        reviewer_id=reviewer,
        reviewed_at=reviewed_at,
        state=state,
    )


def load_relevance_dataset(path: Path) -> tuple[RelevanceRecord, ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError("human relevance dataset cannot be read") from exc
    records: list[RelevanceRecord] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"human relevance dataset line {line_number} is invalid JSON") from exc
        if type(raw) is not dict or any(type(key) is not str for key in raw):
            raise ValueError("human relevance dataset records must be JSON objects")
        records.append(parse_relevance_record(cast(dict[str, object], raw)))
    if len(records) != 30:
        raise ValueError("human relevance dataset requires exactly 30 slots")
    if tuple(record.slot for record in records) != tuple(range(1, 31)):
        raise ValueError("human relevance dataset slots must be unique and ordered 1..30")
    return tuple(records)


def evaluate_relevance_gate(
    records: tuple[RelevanceRecord, ...],
) -> RelevanceGateEvaluation:
    reviewed = sum(record.state is RelevanceRecordState.REVIEWED for record in records)
    if len(records) != 30 or reviewed != 30:
        raise IncompleteHumanReview(f"BLOCKED: {reviewed}/30 human reviews are complete")
    top_five_matches = sum(
        bool(
            set(record.expected_relevant_paper_ids or ())
            & set(record.observed_top_five_paper_ids or ())
        )
        for record in records
    )
    p0_failures = sum(record.p0_relevance_failure is True for record in records)
    return RelevanceGateEvaluation(
        reviewed=reviewed,
        top_five_matches=top_five_matches,
        p0_failures=p0_failures,
    )


def _load_json_object(path: Path, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unavailable or invalid") from exc
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise ValueError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _load_observed_results(path: Path) -> tuple[dict[str, object], ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError("observed results cannot be read") from exc
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"observed results line {line_number} is invalid JSON") from exc
        if type(value) is not dict or set(value) != OBSERVED_RECORD_KEYS:
            raise ValueError("observed result has unknown or missing fields")
        record = cast(dict[str, object], value)
        if record["schema_version"] != "search-relevance-observed-v1":
            raise ValueError("observed result schema is unsupported")
        slot = record["slot"]
        query = record["query"]
        if type(slot) is not int or not 1 <= slot <= 30:
            raise ValueError("observed result slot is invalid")
        if type(query) is not str or not query.strip() or len(query) > 500:
            raise ValueError("observed result query is invalid")
        _uuidv7_list(
            record["observed_top_five_paper_ids"],
            field="observed_top_five_paper_ids",
            require_non_empty=False,
            maximum=5,
        )
        records.append(record)
    if len(records) != 30 or tuple(record["slot"] for record in records) != tuple(range(1, 31)):
        raise ValueError("observed results require exactly 30 ordered slots")
    return tuple(records)


def load_bound_review_dataset(
    reviews_path: Path,
    run_manifest_path: Path,
) -> tuple[RelevanceRecord, ...]:
    manifest_path = _regular_file(run_manifest_path, label="run manifest")
    manifest = _load_json_object(manifest_path, label="run manifest")
    if manifest.get("schema_version") != "search-relevance-run-v1":
        raise ValueError("run manifest schema is unsupported")
    human_truth = manifest.get("human_truth")
    artifacts = manifest.get("artifacts")
    if type(human_truth) is not dict or type(artifacts) is not dict:
        raise ValueError("run manifest is incomplete")
    truth_path_value = human_truth.get("path")
    truth_hash = human_truth.get("sha256")
    observed_hash = artifacts.get("observed_results.jsonl")
    if not all(type(value) is str for value in (truth_path_value, truth_hash, observed_hash)):
        raise ValueError("run manifest evidence fields are invalid")
    truth_path = _regular_file(Path(cast(str, truth_path_value)), label="human truth")
    if _sha256_file(truth_path) != truth_hash:
        raise ValueError("prepared human truth changed after benchmark execution")
    observed_path = _regular_file(
        manifest_path.parent / "observed_results.jsonl",
        label="observed results",
    )
    if _sha256_file(observed_path) != observed_hash:
        raise ValueError("observed results changed after benchmark execution")

    truth_records = load_relevance_dataset(truth_path)
    if any(record.state is not RelevanceRecordState.PREPARED for record in truth_records):
        raise ValueError("run manifest human truth is not in prepared state")
    observed_records = _load_observed_results(observed_path)
    review_records = load_relevance_dataset(reviews_path)
    for truth, observed, review in zip(
        truth_records,
        observed_records,
        review_records,
        strict=True,
    ):
        observed_ids = _uuidv7_list(
            observed["observed_top_five_paper_ids"],
            field="observed_top_five_paper_ids",
            require_non_empty=False,
            maximum=5,
        )
        if (
            review.query != truth.query
            or review.expected_relevant_paper_ids != truth.expected_relevant_paper_ids
            or review.query != observed["query"]
            or review.observed_top_five_paper_ids != observed_ids
        ):
            raise ValueError("review records differ from prepared truth or observed results")
    return review_records


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_file(path: Path, *, label: str) -> Path:
    resolved = Path(os.path.abspath(path.expanduser()))
    try:
        status = resolved.lstat()
    except OSError as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
        raise ValueError(f"{label} must be a regular file")
    return resolved


def _capture_corpus(catalog_path: Path, index_path: Path) -> CorpusEvidence:
    catalog = _regular_file(catalog_path, label="catalog")
    index = _regular_file(index_path, label="search index")
    root = catalog.parent
    try:
        index.relative_to(root)
    except ValueError as exc:
        raise ValueError("search index must be confined below the catalog directory") from exc
    catalog_hash_before = _sha256_file(catalog)
    index_hash_before = _sha256_file(index)
    with _CatalogRuntime(catalog) as runtime:
        reader = runtime.require_reader()
        with reader.snapshot() as snapshot:
            revision = snapshot.revision
            documents = snapshot.list_index_documents()
    receipt = read_index_receipt(index, corpus_root=root)
    catalog_hash_after = _sha256_file(catalog)
    index_hash_after = _sha256_file(index)
    if catalog_hash_before != catalog_hash_after or index_hash_before != index_hash_after:
        raise ValueError("catalog or search index changed during benchmark capture")
    if receipt.catalog_revision != revision:
        raise ValueError("catalog and search index revisions differ")
    if receipt.document_count != len(documents):
        raise ValueError("catalog and search index document counts differ")
    if not documents:
        raise ValueError("human relevance benchmark requires a non-empty corpus")
    return CorpusEvidence(
        root=root,
        catalog_path=catalog,
        index_path=index,
        catalog_sha256=catalog_hash_after,
        index_sha256=index_hash_after,
        documents=documents,
        receipt=receipt,
    )


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def _jsonl_bytes(values: Sequence[object]) -> bytes:
    return b"".join(_json_bytes(value) for value in values)


def _validate_json(content: bytes) -> None:
    json.loads(content)


def _validate_jsonl(content: bytes) -> None:
    lines = content.decode().splitlines()
    if not lines:
        raise ValueError("generated JSONL artifact cannot be empty")
    for line in lines:
        json.loads(line)


def _validate_markdown(content: bytes) -> None:
    if not content.decode().strip():
        raise ValueError("generated review form cannot be empty")


def _prepare_output_directory(path: Path) -> Path:
    output = Path(os.path.abspath(path.expanduser()))
    if output.exists():
        status = output.lstat()
        if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
            raise ValueError("output directory must be a real directory")
    else:
        output.mkdir(parents=True, mode=0o700)
    return output


def _write_atomic(
    path: Path,
    content: bytes,
    *,
    validator: Callable[[bytes], None],
) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"refusing to overwrite existing artifact: {path.name}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        validator(content)
        os.replace(temporary, path)
        directory_descriptor = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def _inventory_rows(evidence: CorpusEvidence) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for document in sorted(
        evidence.documents,
        key=lambda item: (str(item.paper_id), str(item.paper_version_id)),
    ):
        rows.append(
            {
                "schema_version": "search-relevance-corpus-item-v1",
                "paper_id": str(document.paper_id),
                "paper_version_id": str(document.paper_version_id),
                "version_observation_id": str(document.version_observation_id),
                "source_id": str(document.source_id),
                "title": document.title,
                "abstract": document.abstract,
                "authors": list(document.authors),
                "categories": list(document.categories),
                "language": document.language,
                "submitted_at": (
                    document.submitted_at.isoformat() if document.submitted_at is not None else None
                ),
                "identifiers": [
                    {
                        "scheme": identifier.scheme,
                        "canonical_value": identifier.canonical_value,
                        "scope": identifier.scope.value,
                    }
                    for identifier in document.identifiers
                ],
            }
        )
    return tuple(rows)


def _evidence_manifest(evidence: CorpusEvidence, inventory_hash: str) -> dict[str, object]:
    paper_ids = {str(document.paper_id) for document in evidence.documents}
    return {
        "schema_version": "search-relevance-inventory-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "catalog": {
            "path": str(evidence.catalog_path),
            "sha256": evidence.catalog_sha256,
            "revision": evidence.receipt.catalog_revision.value,
            "document_count": len(evidence.documents),
            "paper_count": len(paper_ids),
        },
        "index": {
            "path": str(evidence.index_path),
            "sha256": evidence.index_sha256,
            "schema_version": evidence.receipt.index_schema_version,
            "chunk_schema_version": evidence.receipt.chunk_schema_version,
            "generation": evidence.receipt.generation,
            "catalog_revision": evidence.receipt.catalog_revision.value,
            "document_count": evidence.receipt.document_count,
            "passage_count": evidence.receipt.passage_count,
            "content_sha256": str(evidence.receipt.content_sha256),
        },
        "inventory": {
            "path": "corpus_inventory.jsonl",
            "sha256": inventory_hash,
            "row_count": len(evidence.documents),
            "blind_to": ["queries", "expected_relevance", "search_ranks", "bm25_scores"],
        },
    }


def write_inventory(catalog_path: Path, index_path: Path, output_dir: Path) -> None:
    evidence = _capture_corpus(catalog_path, index_path)
    output = _prepare_output_directory(output_dir)
    inventory = _jsonl_bytes(_inventory_rows(evidence))
    manifest = _json_bytes(_evidence_manifest(evidence, hashlib.sha256(inventory).hexdigest()))
    _write_atomic(
        output / "corpus_inventory.jsonl",
        inventory,
        validator=_validate_jsonl,
    )
    _write_atomic(
        output / "inventory_manifest.json",
        manifest,
        validator=_validate_json,
    )


def _read_inventory_manifest(path: Path, evidence: CorpusEvidence) -> bytes:
    try:
        content = path.read_bytes()
        manifest = json.loads(content)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("inventory manifest is unavailable or invalid") from exc
    if type(manifest) is not dict or manifest.get("schema_version") != (
        "search-relevance-inventory-v1"
    ):
        raise ValueError("inventory manifest schema is unsupported")
    catalog = manifest.get("catalog")
    index = manifest.get("index")
    inventory = manifest.get("inventory")
    if type(catalog) is not dict or type(index) is not dict or type(inventory) is not dict:
        raise ValueError("inventory manifest is incomplete")
    expected = (
        catalog.get("path") == str(evidence.catalog_path)
        and catalog.get("sha256") == evidence.catalog_sha256
        and catalog.get("revision") == evidence.receipt.catalog_revision.value
        and index.get("path") == str(evidence.index_path)
        and index.get("sha256") == evidence.index_sha256
        and index.get("content_sha256") == str(evidence.receipt.content_sha256)
    )
    inventory_path = path.parent / "corpus_inventory.jsonl"
    try:
        inventory_hash = _sha256_file(inventory_path)
    except OSError as exc:
        raise ValueError("blind corpus inventory is unavailable") from exc
    if not expected or inventory.get("sha256") != inventory_hash:
        raise ValueError("catalog, index, or blind inventory changed after preparation")
    return content


def _prepared_records(path: Path, paper_ids: set[str]) -> tuple[RelevanceRecord, ...]:
    records = load_relevance_dataset(path)
    if any(record.state is not RelevanceRecordState.PREPARED for record in records):
        raise ValueError("all 30 query slots must contain prepared human truth only")
    for record in records:
        expected = record.expected_relevant_paper_ids
        if expected is None or any(paper_id not in paper_ids for paper_id in expected):
            raise ValueError("expected relevant paper IDs must belong to the captured catalog")
    return records


def _review_form(
    records: tuple[RelevanceRecord, ...],
    observed: tuple[tuple[str, ...], ...],
) -> bytes:
    lines = [
        "# Gate 2 human search relevance review",
        "",
        "This form displays human-authored expected paper IDs beside observed search output. ",
        "It does not assign a P0 verdict, reviewer identity, timestamp, or approval.",
        "",
    ]
    for record, result_ids in zip(records, observed, strict=True):
        expected = record.expected_relevant_paper_ids or ()
        rendered_results = (
            tuple(f"- `{paper_id}`" for paper_id in result_ids) if result_ids else ("- None",)
        )
        lines.extend(
            (
                f"## Slot {record.slot}",
                "",
                f"Query: `{record.query}`",
                "",
                "Expected relevant paper IDs authored before execution:",
                *(f"- `{paper_id}`" for paper_id in expected),
                "",
                "Observed top-five paper IDs:",
                *rendered_results,
                "",
                "Reviewer ID: ____________________",
                "",
                "Reviewed at (UTC): ____________________",
                "",
                "P0 relevance failure: [ ] true  [ ] false",
                "",
            )
        )
    return ("\n".join(lines).rstrip() + "\n").encode()


def run_queries(
    catalog_path: Path,
    index_path: Path,
    queries_path: Path,
    output_dir: Path,
) -> None:
    evidence = _capture_corpus(catalog_path, index_path)
    output = _prepare_output_directory(output_dir)
    inventory_manifest = _read_inventory_manifest(
        output / "inventory_manifest.json",
        evidence,
    )
    paper_ids = {str(document.paper_id) for document in evidence.documents}
    records = _prepared_records(queries_path, paper_ids)
    truth_content = queries_path.read_bytes()
    observations: list[dict[str, object]] = []
    review_records: list[dict[str, object]] = []
    observed_ids: list[tuple[str, ...]] = []
    with _CatalogRuntime(evidence.catalog_path) as runtime:
        search = SqliteFtsSearchReader(
            evidence.index_path,
            runtime.require_reader(),
            corpus_root=evidence.root,
        )
        for record in records:
            if record.query is None or record.expected_relevant_paper_ids is None:
                raise ValueError("prepared relevance record is incomplete")
            result = search.search_papers(PaperSearchQuery(query=record.query, limit=5))
            if (
                result.coverage is not CoverageStatus.COMPLETE
                or result.catalog_revision != evidence.receipt.catalog_revision
                or result.index_revision != evidence.receipt.catalog_revision
            ):
                raise ValueError("search coverage is not complete for the captured corpus")
            result_ids = tuple(str(hit.paper_id) for hit in result.hits)
            observed_ids.append(result_ids)
            observations.append(
                {
                    "schema_version": "search-relevance-observed-v1",
                    "slot": record.slot,
                    "query": record.query,
                    "observed_top_five_paper_ids": list(result_ids),
                    "coverage": result.coverage.value,
                    "catalog_revision": result.catalog_revision.value,
                    "index_revision": result.index_revision.value,
                    "returned": result.returned,
                    "available": result.available,
                    "truncated": result.truncated,
                }
            )
            review = {
                "schema_version": RELEVANCE_SCHEMA_VERSION,
                "slot": record.slot,
                "query": record.query,
                "expected_relevant_paper_ids": list(record.expected_relevant_paper_ids),
                "observed_top_five_paper_ids": list(result_ids),
                "p0_relevance_failure": None,
                "reviewer_id": None,
                "reviewed_at": None,
            }
            if parse_relevance_record(review).state is not RelevanceRecordState.EXECUTED:
                raise ValueError("generated review record is invalid")
            review_records.append(review)
    if len(observations) != 30:
        raise ValueError("benchmark execution did not produce exactly 30 observations")

    observed_content = _jsonl_bytes(observations)
    review_content = _jsonl_bytes(review_records)
    form_content = _review_form(records, tuple(observed_ids))
    run_manifest = _json_bytes(
        {
            "schema_version": "search-relevance-run-v1",
            "created_at": datetime.now(UTC).isoformat(),
            "catalog_path": str(evidence.catalog_path),
            "catalog_sha256": evidence.catalog_sha256,
            "index_path": str(evidence.index_path),
            "index_sha256": evidence.index_sha256,
            "catalog_revision": evidence.receipt.catalog_revision.value,
            "query_count": len(records),
            "human_truth": {
                "path": str(queries_path.expanduser().resolve(strict=False)),
                "sha256": hashlib.sha256(truth_content).hexdigest(),
            },
            "inventory_manifest_sha256": hashlib.sha256(inventory_manifest).hexdigest(),
            "artifacts": {
                "observed_results.jsonl": hashlib.sha256(observed_content).hexdigest(),
                "review_records.jsonl": hashlib.sha256(review_content).hexdigest(),
                "review_form.md": hashlib.sha256(form_content).hexdigest(),
            },
            "human_review_status": "pending",
        }
    )
    _write_atomic(
        output / "observed_results.jsonl",
        observed_content,
        validator=_validate_jsonl,
    )
    _write_atomic(
        output / "review_records.jsonl",
        review_content,
        validator=_validate_jsonl,
    )
    _write_atomic(output / "review_form.md", form_content, validator=_validate_markdown)
    _write_atomic(output / "run_manifest.json", run_manifest, validator=_validate_json)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper-insights-search-relevance")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("inventory", "run"):
        subcommand = commands.add_parser(command)
        subcommand.add_argument("--catalog", type=Path, required=True)
        subcommand.add_argument("--index", type=Path, required=True)
        subcommand.add_argument("--output-dir", type=Path, required=True)
        if command == "run":
            subcommand.add_argument("--queries", type=Path, required=True)
    validation = commands.add_parser("validate-review")
    validation.add_argument("--reviews", type=Path, required=True)
    validation.add_argument("--run-manifest", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "inventory":
            write_inventory(arguments.catalog, arguments.index, arguments.output_dir)
        elif arguments.command == "run":
            run_queries(
                arguments.catalog,
                arguments.index,
                arguments.queries,
                arguments.output_dir,
            )
        elif arguments.command == "validate-review":
            evaluation = evaluate_relevance_gate(
                load_bound_review_dataset(arguments.reviews, arguments.run_manifest)
            )
            if evaluation.criteria_satisfied:
                sys.stdout.write(
                    "SATISFIED: "
                    f"{evaluation.top_five_matches}/30 expected papers in top five; "
                    "0 P0 relevance failures\n"
                )
                return 0
            sys.stdout.write(
                "FAILED: "
                f"{evaluation.top_five_matches}/30 expected papers in top five; "
                f"{evaluation.p0_failures} P0 relevance failures\n"
            )
            return 1
        else:
            raise ValueError("unknown relevance harness command")
    except IncompleteHumanReview as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    except (OSError, SQLAlchemyError, sqlite3.DatabaseError, ValueError) as exc:
        sys.stderr.write(f"search relevance harness failed: {exc}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
