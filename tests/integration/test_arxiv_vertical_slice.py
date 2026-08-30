from __future__ import annotations

import io
import json
import sqlite3
from collections import deque
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from alembic.config import Config
from pydantic import ValidationError

from alembic import command
from paper_insights.bootstrap import (
    citation_service,
    collections_service,
    discover_service,
    index_service,
    ingestion_service,
    main,
    repair_service,
    search_service,
)
from paper_insights.interfaces.cli.app import run
from paper_insights.interfaces.cli.envelopes import CliEnvelope, CliErrorEnvelope

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "arxiv"


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 8, 29, 8, 0, tzinfo=UTC)


class _Ids:
    def __init__(self) -> None:
        self._values = deque(
            UUID(f"01890f3c-0000-7000-8000-{value:012d}") for value in range(1, 200)
        )

    def new(self) -> UUID:
        return self._values.popleft()


def _migrate(database: Path) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database}")
    command.upgrade(config, "head")


def test_missing_catalog_fails_closed_without_initializing_it(tmp_path: Path) -> None:
    data_root = tmp_path / "absent"
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = main(
        ["collections", "list", "--json"],
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(data_root)},
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 6
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue())["error"]["code"] == "corpus_unavailable"
    assert not data_root.exists()


def test_repair_requires_confirmation_after_read_only_preview(tmp_path: Path) -> None:
    data_root = tmp_path / "corpus"
    data_root.mkdir()
    catalog = data_root / "catalog.sqlite3"
    _migrate(catalog)
    wal = catalog.with_name(catalog.name + "-wal")
    shm = catalog.with_name(catalog.name + "-shm")
    assert not wal.exists()
    assert not shm.exists()
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        [
            "repair",
            "interrupted-runs",
            "--json",
        ],
        doctor_service_factory=lambda _settings: (_ for _ in ()).throw(
            AssertionError("repair called doctor")
        ),
        repair_service_factory=repair_service,
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(data_root)},
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 3
    assert stderr.getvalue() == ""
    assert json.loads(stdout.getvalue())["data"]["candidates"] == []
    assert not wal.exists()
    assert not shm.exists()


def test_ingest_preview_needs_no_catalog_and_creates_nothing(tmp_path: Path) -> None:
    data_root = tmp_path / "absent"
    stdout = io.StringIO()
    stderr = io.StringIO()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            content=(FIXTURES / "revision-v2.xml").read_bytes(),
            request=request,
        )
    )

    code = run(
        ["ingest", "arxiv", "--identifier", "2608.01234", "--limit", "1", "--json"],
        doctor_service_factory=lambda _settings: (_ for _ in ()).throw(
            AssertionError("preview called doctor")
        ),
        discover_service_factory=lambda settings, source: discover_service(
            settings,
            source,
            transport=transport,
            clock=_Clock(),
            new_capture_id=lambda: UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5c"),
        ),
        ingestion_service_factory=lambda _settings: (_ for _ in ()).throw(
            AssertionError("unconfirmed preview opened catalog runtime")
        ),
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(data_root)},
        stdin=io.StringIO(),
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 3
    assert stderr.getvalue() == ""
    assert json.loads(stdout.getvalue())["data"]["preview"]["selected_records"] == 1
    assert not data_root.exists()


def test_catalog_and_index_database_errors_are_closed(tmp_path: Path) -> None:
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    (empty_root / "catalog.sqlite3").touch()
    empty_stdout = io.StringIO()
    empty_stderr = io.StringIO()

    empty_code = main(
        ["collections", "list", "--json"],
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(empty_root)},
        stdout=empty_stdout,
        stderr=empty_stderr,
    )

    corrupt_root = tmp_path / "corrupt"
    corrupt_root.mkdir()
    _migrate(corrupt_root / "catalog.sqlite3")
    (corrupt_root / ".search").mkdir()
    (corrupt_root / ".search" / "search-v1.sqlite3").write_bytes(b"not sqlite")
    corrupt_stdout = io.StringIO()
    corrupt_stderr = io.StringIO()
    corrupt_code = main(
        ["search", "papers", "agents", "--json"],
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(corrupt_root)},
        stdout=corrupt_stdout,
        stderr=corrupt_stderr,
    )

    assert (empty_code, corrupt_code) == (6, 6)
    assert empty_stdout.getvalue() == corrupt_stdout.getvalue() == ""
    assert json.loads(empty_stderr.getvalue())["error"]["code"] == "corpus_unavailable"
    assert json.loads(corrupt_stderr.getvalue())["error"]["code"] == "corpus_unavailable"


@pytest.mark.parametrize("limit", (0, 51))
def test_search_rejects_out_of_range_limit_before_factory(tmp_path: Path, limit: int) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(
        ["search", "papers", "agents", "--limit", str(limit), "--json"],
        doctor_service_factory=lambda _settings: (_ for _ in ()).throw(
            AssertionError("search called doctor")
        ),
        search_service_factory=lambda _settings: (_ for _ in ()).throw(
            AssertionError("invalid search opened runtime")
        ),
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(tmp_path)},
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 2
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue())["error"]["code"] == "invalid_request"


def test_cli_envelope_forbids_extra_fields_and_unknown_operations() -> None:
    valid = {
        "schema_version": "paper-insights.cli.v1",
        "operation": "discover",
        "data": {"preview": {}, "records": []},
        "coverage": {"status": "complete"},
        "errors": [],
        "truncated": False,
    }

    assert CliEnvelope.model_validate(valid).operation == "discover"
    with pytest.raises(ValidationError):
        CliEnvelope.model_validate({**valid, "operation": "unknown"})
    with pytest.raises(ValidationError):
        CliEnvelope.model_validate({**valid, "unexpected": True})
    with pytest.raises(ValidationError):
        CliEnvelope.model_validate({**valid, "data": {"preview": {}, "records": [], "x": 1}})
    with pytest.raises(ValidationError):
        CliEnvelope.model_validate(
            {**valid, "data": {"preview": {"path": Path("x")}, "records": []}}
        )
    with pytest.raises(ValidationError):
        CliErrorEnvelope.model_validate(
            {"schema_version": "paper-insights.error.v1", "error": {"code": "made_up"}}
        )

    partial = CliEnvelope.model_validate(
        {
            **valid,
            "operation": "ingest",
            "data": {"run_id": "run", "counters": {}},
            "errors": [{"code": "ingestion_items_failed", "count": 1}],
        }
    )
    assert partial.errors[0].count == 1


def test_offline_arxiv_cli_preserves_versions_and_provenance(tmp_path: Path) -> None:
    data_root = tmp_path / "corpus"
    data_root.mkdir()
    _migrate(data_root / "catalog.sqlite3")
    ids = _Ids()
    clock = _Clock()
    capture_ids = iter(
        (
            UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a"),
            UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a"),
            UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5b"),
            UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5d"),
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("search_query", "")
        if "hostile-conflict" in query:
            payload = (
                (FIXTURES / "page-1.xml")
                .read_bytes()
                .replace(
                    b'    <category term="cs.DB" />\n',
                    b'    <category term="cs.DB" />\n'
                    b"    <arxiv:doi>10.1234/example.1</arxiv:doi>\n",
                )
            )
            return httpx.Response(200, content=payload, request=request)
        fixture = "revision-v2.xml" if "id:2608.01234" in query else "page-1.xml"
        return httpx.Response(
            200,
            content=(FIXTURES / fixture).read_bytes(),
            request=request,
        )

    def invoke(arguments: list[str]) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run(
            arguments,
            doctor_service_factory=lambda _settings: (_ for _ in ()).throw(
                AssertionError("vertical slice called doctor")
            ),
            discover_service_factory=lambda settings, source: discover_service(
                settings,
                source,
                transport=httpx.MockTransport(handler),
                clock=clock,
                new_capture_id=lambda: next(capture_ids),
            ),
            ingestion_service_factory=lambda settings: ingestion_service(
                settings,
                clock=clock,
                ids=ids,
            ),
            collections_service_factory=collections_service,
            search_service_factory=search_service,
            index_service_factory=index_service,
            citation_service_factory=citation_service,
            repair_service_factory=repair_service,
            environ={"PAPER_INSIGHTS_DATA_ROOT": str(data_root)},
            stdout=stdout,
            stderr=stderr,
        )
        rendered = stdout.getvalue()
        if not rendered:
            payload: dict[str, object] = {}
        elif rendered.startswith("{"):
            payload = json.loads(rendered)
        else:
            payload = {"text": rendered}
        return code, payload, stderr.getvalue()

    first_code, first, first_error = invoke(
        ["ingest", "arxiv", "agents", "--limit", "2", "--yes", "--json"]
    )
    replay_code, replay, replay_error = invoke(
        ["ingest", "arxiv", "agents", "--limit", "2", "--yes", "--json"]
    )
    revision_code, revision, revision_error = invoke(
        [
            "ingest",
            "arxiv",
            "--identifier",
            "2608.01234",
            "--limit",
            "1",
            "--yes",
            "--json",
        ]
    )

    assert (first_code, replay_code, revision_code) == (0, 0, 0)
    assert first_error == replay_error == revision_error == ""
    assert first["data"]["counters"]["new_papers"] == 2  # type: ignore[index]
    assert first["data"]["counters"]["new_versions"] == 2  # type: ignore[index]
    assert replay["data"]["counters"]["unchanged_records"] == 2  # type: ignore[index]
    assert revision["data"]["counters"]["new_versions"] == 1  # type: ignore[index]

    index_code, published, index_error = invoke(["index", "rebuild", "--json"])
    search_code, searched, search_error = invoke(
        ["search", "papers", "Revised", "--limit", "5", "--json"]
    )
    create_code, _created, create_error = invoke(
        ["collections", "create", "agents", "--title", "Agent papers", "--json"]
    )
    add_code, _added, add_error = invoke(
        ["collections", "add", "agents", "arxiv:2608.01234", "--json"]
    )
    list_code, listed, list_error = invoke(["collections", "list", "--json"])

    assert (index_code, search_code, create_code, add_code, list_code) == (0, 0, 0, 0, 0)
    assert index_error == search_error == create_error == add_error == list_error == ""
    assert published["data"]["catalog_revision"] > 0  # type: ignore[index]
    assert searched["coverage"]["status"] == "complete"  # type: ignore[index]
    assert searched["data"]["hits"][0]["title"] == "Reliable Paper Agents, Revised"  # type: ignore[index]
    assert searched["data"]["hits"][0]["source_id"] == "arxiv"  # type: ignore[index]
    assert searched["data"]["hits"][0]["authors"] == [  # type: ignore[index]
        "Alice Example",
        "Bob Researcher",
    ]
    assert searched["data"]["hits"][0]["identifiers"] == [  # type: ignore[index]
        {"scheme": "arxiv", "canonical_value": "2608.01234", "scope": "paper"},
        {"scheme": "doi", "canonical_value": "10.1234/example.1", "scope": "paper"},
        {"scheme": "arxiv", "canonical_value": "2608.01234v2", "scope": "version"},
    ]
    assert listed["data"]["collections"][0]["paper_count"] == 1  # type: ignore[index]

    refreshed_code, refreshed_search, refreshed_error = invoke(
        ["search", "papers", "Revised", "--limit", "5", "--json"]
    )
    terminal_code, terminal_search, terminal_error = invoke(
        ["search", "papers", "Revised", "--limit", "5"]
    )
    assert (refreshed_code, terminal_code) == (0, 0)
    assert refreshed_error == terminal_error == ""
    assert "source=arxiv" in terminal_search["text"]  # type: ignore[operator]
    assert "authors=[Alice Example, Bob Researcher]" in terminal_search["text"]  # type: ignore[operator]
    assert "doi:10.1234/example.1 [paper]" in terminal_search["text"]  # type: ignore[operator]
    assert f"paper_id={searched['data']['hits'][0]['paper_id']}" in terminal_search["text"]  # type: ignore[index,operator]
    assert (
        f"paper_version_id={searched['data']['hits'][0]['paper_version_id']}"
        in terminal_search["text"]  # type: ignore[index,operator]
    )
    assert "bm25_score=" in terminal_search["text"]  # type: ignore[operator]
    assert "artifact_sha256=" in terminal_search["text"]  # type: ignore[operator]
    assert "catalog_revision=" in terminal_search["text"]  # type: ignore[operator]
    assert "index_revision=" in terminal_search["text"]  # type: ignore[operator]
    assert (
        f"coverage={refreshed_search['coverage']['status']}" in terminal_search["text"]  # type: ignore[index,operator]
    )
    assert f"returned={refreshed_search['returned']}" in terminal_search["text"]  # type: ignore[operator]
    assert f"available={refreshed_search['available']}" in terminal_search["text"]  # type: ignore[operator]
    assert (
        f"truncated={str(refreshed_search['truncated']).lower()}" in terminal_search["text"]  # type: ignore[operator]
    )

    with closing(sqlite3.connect(data_root / "catalog.sqlite3")) as connection:
        paper_count = connection.execute("SELECT count(*) FROM papers").fetchone()[0]
        version_count = connection.execute("SELECT count(*) FROM paper_versions").fetchone()[0]
        v1_title = connection.execute(
            "SELECT vo.title FROM version_observations AS vo "
            "JOIN paper_versions AS pv ON pv.id = vo.paper_version_id "
            "WHERE pv.source_version_key = ?",
            ("2608.01234v1",),
        ).fetchone()[0]
        v2_id = connection.execute(
            "SELECT id FROM paper_versions WHERE source_version_key = ?",
            ("2608.01234v2",),
        ).fetchone()[0]
        v1_id = connection.execute(
            "SELECT id FROM paper_versions WHERE source_version_key = ?",
            ("2608.01234v1",),
        ).fetchone()[0]
        v1_snapshot, v1_ordinal = connection.execute(
            "SELECT vo.origin_source_snapshot_id, vo.origin_record_ordinal "
            "FROM version_observations AS vo WHERE vo.paper_version_id = ?",
            (v1_id,),
        ).fetchone()
        v2_snapshot, v2_ordinal = connection.execute(
            "SELECT vo.origin_source_snapshot_id, vo.origin_record_ordinal "
            "FROM version_observations AS vo WHERE vo.paper_version_id = ?",
            (v2_id,),
        ).fetchone()
        snapshot_count = connection.execute("SELECT count(*) FROM source_snapshots").fetchone()[0]
        snapshot_record_count = connection.execute(
            "SELECT count(*) FROM snapshot_records"
        ).fetchone()[0]
        exact_links = connection.execute(
            "SELECT count(*) FROM snapshot_records AS sr "
            "JOIN version_observations AS vo ON vo.id = sr.version_observation_id "
            "WHERE vo.origin_source_snapshot_id = sr.source_snapshot_id "
            "AND vo.origin_record_ordinal = sr.ordinal"
        ).fetchone()[0]

    assert (paper_count, version_count) == (2, 3)
    assert v1_title == "Reliable Paper Agents"
    assert (snapshot_count, snapshot_record_count, exact_links) == (2, 3, 3)
    assert (v1_ordinal, v2_ordinal) == (0, 0)

    for citation_format in ("bibtex", "markdown", "csl-json"):
        cite_code, citation, cite_error = invoke(
            [
                "cite",
                "arxiv:2608.01234",
                "--paper-version-id",
                v2_id,
                "--format",
                citation_format,
                "--json",
            ]
        )
        assert cite_code == 0
        assert cite_error == ""
        assert citation["data"]["format"] == citation_format  # type: ignore[index]
        assert citation["data"]["paper_version_id"] == v2_id  # type: ignore[index]
        assert citation["data"]["source_id"] == "arxiv"  # type: ignore[index]
        assert citation["data"]["snapshot_id"] == v2_snapshot  # type: ignore[index]
        assert citation["data"]["record_ordinal"] == v2_ordinal  # type: ignore[index]

    v1_code, v1_citation, v1_error = invoke(
        [
            "cite",
            "arxiv:2608.01234",
            "--paper-version-id",
            v1_id,
            "--format",
            "markdown",
            "--json",
        ]
    )
    assert v1_code == 0
    assert v1_error == ""
    assert v1_citation["data"]["paper_version_id"] == v1_id  # type: ignore[index]
    assert v1_citation["data"]["snapshot_id"] == v1_snapshot  # type: ignore[index]
    assert "Reliable Paper Agents" in v1_citation["data"]["content"]  # type: ignore[index,operator]
    assert "Revised" not in v1_citation["data"]["content"]  # type: ignore[index,operator]

    conflict_code, conflict, conflict_error = invoke(
        ["ingest", "arxiv", "hostile-conflict", "--limit", "2", "--yes", "--json"]
    )
    assert conflict_code == 4
    assert conflict_error == ""
    assert conflict["data"]["counters"]["status"] == "partial"  # type: ignore[index]
    assert conflict["data"]["counters"]["unchanged_records"] == 1  # type: ignore[index]
    assert conflict["data"]["counters"]["failed_records"] == 1  # type: ignore[index]
    assert conflict["errors"] == [{"code": "ingestion_items_failed", "count": 1}]
    with closing(sqlite3.connect(data_root / "catalog.sqlite3")) as connection:
        assert connection.execute("SELECT count(*) FROM paper_versions").fetchone()[0] == 3
        assert connection.execute("SELECT count(*) FROM collection_errors").fetchone()[0] == 1
        run_id = conflict["data"]["run_id"]  # type: ignore[index]
        items = connection.execute(
            "SELECT record_ordinal, outcome FROM ingestion_run_items "
            "WHERE run_id = ? ORDER BY record_ordinal",
            (run_id,),
        ).fetchall()
        assert items == [(0, "unchanged"), (1, "failed")]
        linked_error = connection.execute(
            "SELECT count(*) FROM collection_errors AS ce "
            "JOIN ingestion_run_items AS iri ON iri.run_id = ce.run_id "
            "AND iri.source_snapshot_id = ce.source_snapshot_id "
            "AND iri.record_ordinal = ce.record_ordinal "
            "WHERE ce.run_id = ? AND iri.outcome = 'failed'",
            (run_id,),
        ).fetchone()[0]
        assert linked_error == 1
        assert (
            connection.execute(
                "SELECT is_current FROM paper_versions WHERE id = ?",
                (v2_id,),
            ).fetchone()[0]
            == 1
        )
