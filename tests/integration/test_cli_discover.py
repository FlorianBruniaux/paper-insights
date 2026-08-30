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
from paper_insights.interfaces.cli.app import IngestionServices, run

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
        ingestion_service_factory=lambda _settings, source: nullcontext(
            IngestionServices(
                prepare=runtime.discovery[source],  # type: ignore[attr-defined]
                execute=runtime.ingestion,  # type: ignore[attr-defined]
            )
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


def test_discover_rejects_date_without_complete_utc_rfc3339(tmp_path: Path) -> None:
    provider = _FixtureProvider()
    prepare = PrepareDiscovery(provider=provider, clock=_Clock())

    code, payload, errors = _run(
        ["discover", "arxiv", "agents", "--from", "2026-08-01", "--json"],
        runtime=SimpleNamespace(discovery={"arxiv": prepare}),
        data_root=tmp_path / "absent-corpus",
    )

    assert code == 2
    assert payload == {}
    assert json.loads(errors)["error"]["code"] == "invalid_request"


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
