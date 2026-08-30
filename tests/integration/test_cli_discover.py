from __future__ import annotations

import io
import json
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from paper_insights.adapters.providers.arxiv.client import ArxivProviderError
from paper_insights.adapters.providers.arxiv.parser import parse_arxiv_feed
from paper_insights.application.ingestion.prepare import PrepareDiscovery
from paper_insights.domain.acquisition import DiscoveryBatch, DiscoveryPage, DiscoveryQuery
from paper_insights.domain.errors import ErrorCode
from paper_insights.domain.identifiers import Sha256, SourceId
from paper_insights.interfaces.cli.app import run

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "arxiv" / "page-1.xml"
NOW = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)


class _Clock:
    def now(self) -> datetime:
        return NOW


class _FixtureProvider:
    source_id = SourceId("arxiv")

    def __init__(self) -> None:
        self.calls: list[DiscoveryQuery] = []

    def discover(self, query: DiscoveryQuery) -> DiscoveryBatch:
        self.calls.append(query)
        payload = FIXTURE.read_bytes()
        parsed = parse_arxiv_feed(payload, page_ordinal=0)
        page = DiscoveryPage(
            capture_id=UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a"),
            records=parsed.records,
            raw_payload=payload,
            media_type="application/atom+xml",
            retrieved_at=NOW,
            request_fingerprint=Sha256("f" * 64),
            next_cursor=None,
        )
        return DiscoveryBatch(
            source_id=self.source_id,
            query=query,
            pages=(page,),
            records=tuple(
                record.observation for record in parsed.records if record.observation is not None
            ),
            issues=parsed.issues,
        )


class _RejectIngestion:
    def execute(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("unconfirmed CLI ingestion attempted a mutation")


def _run(
    argv: list[str],
    *,
    runtime: object,
    data_root: Path,
) -> tuple[int, dict[str, object], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(
        argv,
        doctor_service_factory=lambda _settings: (_ for _ in ()).throw(
            AssertionError("doctor factory used by a business command")
        ),
        discover_service_factory=lambda _settings, source: nullcontext(
            runtime.discovery[source]  # type: ignore[attr-defined]
        ),
        ingestion_service_factory=lambda _settings: nullcontext(
            runtime.ingestion  # type: ignore[attr-defined]
        ),
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(data_root)},
        stdout=stdout,
        stderr=stderr,
    )
    rendered = stdout.getvalue()
    return code, json.loads(rendered) if rendered else {}, stderr.getvalue()


def test_discover_json_is_versioned_and_makes_zero_corpus_mutation(tmp_path: Path) -> None:
    provider = _FixtureProvider()
    prepare = PrepareDiscovery(provider=provider, clock=_Clock())
    data_root = tmp_path / "absent-corpus"

    code, payload, errors = _run(
        [
            "discover",
            "arxiv",
            "paper agents",
            "--category",
            "cs.AI",
            "--limit",
            "2",
            "--json",
        ],
        runtime=SimpleNamespace(discovery={"arxiv": prepare}),
        data_root=data_root,
    )

    assert code == 0
    assert errors == ""
    assert payload["schema_version"] == "paper-insights.cli.v1"
    assert payload["operation"] == "discover"
    assert payload["coverage"] == {"status": "complete"}
    preview = payload["data"]["preview"]  # type: ignore[index]
    assert preview["schema_version"] == "discovery-preview-v1"
    assert preview["selected_records"] == 2
    assert preview["query"]["categories"] == ["cs.AI"]
    assert [record["source_version_key"] for record in payload["data"]["records"]] == [  # type: ignore[index]
        "2608.01234v1",
        "2608.05678v1",
    ]
    first_record = payload["data"]["records"][0]  # type: ignore[index]
    assert first_record["abstract"] == "Evidence-backed scientific workflows."
    assert [author["raw_name"] for author in first_record["authors"]] == [
        "Alice Example",
        "Bob Researcher",
    ]
    assert [category["value"] for category in first_record["categories"]] == [
        "cs.AI",
        "cs.LG",
    ]
    assert first_record["identifiers"] == [
        {"scheme": "doi", "canonical_value": "10.1234/example.1", "scope": "paper"}
    ]
    assert provider.calls == [DiscoveryQuery(text="paper agents", categories=("cs.AI",), limit=2)]
    assert not data_root.exists()


def test_ingest_without_yes_returns_three_after_preview_and_never_executes(
    tmp_path: Path,
) -> None:
    provider = _FixtureProvider()
    prepare = PrepareDiscovery(provider=provider, clock=_Clock())
    data_root = tmp_path / "absent-corpus"

    code, payload, errors = _run(
        ["ingest", "arxiv", "paper agents", "--limit", "2", "--json"],
        runtime=SimpleNamespace(
            discovery={"arxiv": prepare},
            ingestion=_RejectIngestion(),
        ),
        data_root=data_root,
    )

    assert code == 3
    assert errors == ""
    assert payload["operation"] == "ingest"
    assert payload["data"]["preview"]["selected_records"] == 2  # type: ignore[index]
    assert payload["errors"] == []
    assert provider.calls == [DiscoveryQuery(text="paper agents", limit=2)]
    assert not data_root.exists()


def test_discover_accepts_documented_iso_dates_as_inclusive_utc_bounds(tmp_path: Path) -> None:
    provider = _FixtureProvider()
    prepare = PrepareDiscovery(provider=provider, clock=_Clock())

    code, _payload, errors = _run(
        [
            "discover",
            "arxiv",
            "agents",
            "--from",
            "2026-08-01",
            "--to",
            "2026-08-02",
            "--json",
        ],
        runtime=SimpleNamespace(discovery={"arxiv": prepare}),
        data_root=tmp_path / "absent-corpus",
    )

    assert code == 0
    assert errors == ""
    assert provider.calls == [
        DiscoveryQuery(
            text="agents",
            date_from=datetime(2026, 8, 1, tzinfo=UTC),
            date_to=datetime(2026, 8, 2, 23, 59, 59, 999999, tzinfo=UTC),
            limit=20,
        )
    ]


def test_ingest_tty_confirmation_reuses_the_prepared_discovery(tmp_path: Path) -> None:
    provider = _FixtureProvider()
    prepare = PrepareDiscovery(provider=provider, clock=_Clock())
    executed: list[object] = []

    class Ingestion:
        def execute(self, prepared: object, *, confirmation: object) -> object:
            executed.append((prepared, confirmation))
            raise ArxivProviderError(ErrorCode.CATALOG_CONFLICT, "stop after identity proof")

    class TtyInput(io.StringIO):
        def isatty(self) -> bool:
            return True

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(
        ["ingest", "arxiv", "agents", "--limit", "1"],
        doctor_service_factory=lambda _settings: (_ for _ in ()).throw(
            AssertionError("ingest called doctor")
        ),
        discover_service_factory=lambda _settings, _source: nullcontext(prepare),
        ingestion_service_factory=lambda _settings: nullcontext(
            Ingestion()  # type: ignore[arg-type]
        ),
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(tmp_path)},
        stdin=TtyInput("yes\n"),
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 6
    assert stdout.getvalue().startswith("arxiv: 1/2 selected\ndigest: ")
    assert stderr.getvalue().startswith("Confirm ingestion [y/N]: ")
    assert len(executed) == 1
    prepared, confirmation = executed[0]  # type: ignore[misc]
    assert confirmation == prepared.digest  # type: ignore[attr-defined]
    assert provider.calls == [DiscoveryQuery(text="agents", limit=1)]


def test_discover_keeps_complete_rfc3339_utc_boundaries(tmp_path: Path) -> None:
    provider = _FixtureProvider()
    prepare = PrepareDiscovery(provider=provider, clock=_Clock())

    code, _payload, errors = _run(
        [
            "discover",
            "arxiv",
            "agents",
            "--from",
            "2026-08-01T12:34:56Z",
            "--to",
            "2026-08-02T01:02:03+00:00",
            "--json",
        ],
        runtime=SimpleNamespace(discovery={"arxiv": prepare}),
        data_root=tmp_path / "absent-corpus",
    )

    assert code == 0
    assert errors == ""
    assert provider.calls[0].date_from == datetime(2026, 8, 1, 12, 34, 56, tzinfo=UTC)
    assert provider.calls[0].date_to == datetime(2026, 8, 2, 1, 2, 3, tzinfo=UTC)


def test_discover_maps_provider_error_to_the_frozen_exit_code(tmp_path: Path) -> None:
    class FailedDiscovery:
        def prepare(self, _query: DiscoveryQuery) -> object:
            raise ArxivProviderError(ErrorCode.SOURCE_TIMEOUT, "internal provider detail")

    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(
        ["discover", "arxiv", "agents", "--json"],
        doctor_service_factory=lambda _settings: (_ for _ in ()).throw(
            AssertionError("discover called doctor")
        ),
        discover_service_factory=lambda _settings, _source: nullcontext(
            FailedDiscovery()  # type: ignore[arg-type]
        ),
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(tmp_path / "absent")},
        stdout=stdout,
        stderr=stderr,
    )

    assert code == 5
    assert stdout.getvalue() == ""
    assert json.loads(stderr.getvalue())["error"]["code"] == "source_timeout"
    assert "internal provider detail" not in stderr.getvalue()
