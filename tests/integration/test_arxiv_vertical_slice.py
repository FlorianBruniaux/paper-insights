from __future__ import annotations

import io
import json
import sqlite3
from collections import deque
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
from alembic.config import Config

from alembic import command
from paper_insights.application.ingestion.repair import InterruptedRunsPreview
from paper_insights.bootstrap import (
    citation_service,
    collections_service,
    index_service,
    ingestion_service,
    main,
    repair_service,
    search_service,
)
from paper_insights.interfaces.cli.app import run

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


class _PreviewOnlyRepair:
    def preview(self) -> InterruptedRunsPreview:
        return InterruptedRunsPreview(
            cutoff=datetime(2026, 8, 29, 7, 0, tzinfo=UTC),
            candidates=(),
        )

    def execute(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("unconfirmed repair attempted a mutation")


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
    stdout = io.StringIO()
    stderr = io.StringIO()

    code = run(
        [
            "repair",
            "interrupted-runs",
            "--stale-after-seconds",
            "3600",
            "--json",
        ],
        doctor_service_factory=lambda _settings: (_ for _ in ()).throw(
            AssertionError("repair called doctor")
        ),
        repair_service_factory=lambda _settings, age: nullcontext(
            _PreviewOnlyRepair() if age == 3600 else None  # type: ignore[arg-type]
        ),
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(tmp_path / "absent")},
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 3
    assert stderr.getvalue() == ""
    assert json.loads(stdout.getvalue())["data"]["candidates"] == []


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
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("search_query", "")
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
            ingestion_service_factory=lambda settings, source: ingestion_service(
                settings,
                source,
                transport=httpx.MockTransport(handler),
                clock=clock,
                ids=ids,
                new_capture_id=lambda: next(capture_ids),
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
        return code, json.loads(rendered) if rendered else {}, stderr.getvalue()

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
    assert listed["data"]["collections"][0]["paper_count"] == 1  # type: ignore[index]

    with sqlite3.connect(data_root / "catalog.sqlite3") as connection:
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

    assert (paper_count, version_count) == (2, 3)
    assert v1_title == "Reliable Paper Agents"

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
        assert citation["data"]["source_id"] == "arxiv"  # type: ignore[index]
        assert citation["data"]["snapshot_id"]  # type: ignore[index]
        assert citation["data"]["record_ordinal"] == 0  # type: ignore[index]
