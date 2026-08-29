from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx

from paper_insights.adapters.providers.arxiv.client import ArxivClient, ArxivClientConfig
from paper_insights.domain.acquisition import DiscoveryQuery

FIXTURES = Path(__file__).parents[1] / "fixtures" / "arxiv"
CAPTURE_IDS = iter(
    (
        UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a"),
        UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5b"),
    )
)


def test_pagination_deduplicates_overlap_and_stops_at_total_limit() -> None:
    starts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["start"])
        starts.append(start)
        fixture = "page-1.xml" if start == 0 else "page-2-overlap.xml"
        return httpx.Response(200, content=(FIXTURES / fixture).read_bytes(), request=request)

    client = ArxivClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        config=ArxivClientConfig(page_size=2),
        clock=lambda: datetime(2026, 8, 29, tzinfo=UTC),
        new_capture_id=lambda: next(CAPTURE_IDS),
        sleep=lambda _delay: None,
    )

    batch = client.discover(DiscoveryQuery(text="paper agents", limit=3))

    assert starts == [0, 2]
    assert len(batch.pages) == 2
    assert tuple(record.source_version_key for record in batch.records) == (
        "2608.01234v1",
        "2608.05678v1",
        "2608.09999v1",
    )
    assert batch.pages[1].records[0].observation is None
    assert batch.pages[1].records[1].observation == batch.records[2]
    assert batch.pages[0].next_cursor == "2"
    assert batch.pages[1].next_cursor is None
    assert all(page.raw_payload for page in batch.pages)


def test_cursor_and_query_fields_are_encoded_deterministically() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(
            200, content=(FIXTURES / "revision-v2.xml").read_bytes(), request=request
        )

    capture_id = UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")
    client = ArxivClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        config=ArxivClientConfig(page_size=10),
        clock=lambda: datetime(2026, 8, 29, tzinfo=UTC),
        new_capture_id=lambda: capture_id,
        sleep=lambda _delay: None,
    )

    client.discover(
        DiscoveryQuery(
            text="evidence",
            categories=("cs.AI",),
            authors=("Alice Example",),
            date_from=datetime(2026, 8, 1, tzinfo=UTC),
            date_to=datetime(2026, 8, 31, 23, 59, tzinfo=UTC),
            limit=1,
            cursor="7",
        )
    )

    assert seen[0].params["start"] == "7"
    assert seen[0].params["max_results"] == "1"
    assert seen[0].params["sortBy"] == "submittedDate"
    assert seen[0].params["sortOrder"] == "ascending"
    search_query = seen[0].params["search_query"]
    assert 'all:"evidence"' in search_query
    assert "cat:cs.AI" in search_query
    assert 'au:"Alice Example"' in search_query
    assert "submittedDate:[202608010000 TO 202608312359]" in search_query


def test_request_fingerprint_keeps_initial_query_across_a_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/query":
            return httpx.Response(302, headers={"Location": "/api/final"}, request=request)
        return httpx.Response(
            200, content=(FIXTURES / "revision-v2.xml").read_bytes(), request=request
        )

    def discover(text: str) -> str:
        client = ArxivClient(
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
            config=ArxivClientConfig(page_size=1),
            clock=lambda: datetime(2026, 8, 29, tzinfo=UTC),
            new_capture_id=lambda: UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a"),
            sleep=lambda _delay: None,
        )
        return client.discover(DiscoveryQuery(text=text, limit=1)).pages[
            0
        ].request_fingerprint.value

    assert discover("alpha") != discover("beta")


def test_request_fingerprint_covers_every_redirect_hop() -> None:
    def discover(*, with_intermediate_hop: bool) -> str:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/query":
                target = "/api/intermediate" if with_intermediate_hop else "/api/final"
                return httpx.Response(302, headers={"Location": target}, request=request)
            if request.url.path == "/api/intermediate":
                return httpx.Response(
                    302, headers={"Location": "/api/final"}, request=request
                )
            return httpx.Response(
                200, content=(FIXTURES / "revision-v2.xml").read_bytes(), request=request
            )

        client = ArxivClient(
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
            config=ArxivClientConfig(page_size=1),
            clock=lambda: datetime(2026, 8, 29, tzinfo=UTC),
            new_capture_id=lambda: UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a"),
            sleep=lambda _delay: None,
        )
        return client.discover(DiscoveryQuery(text="same", limit=1)).pages[
            0
        ].request_fingerprint.value

    assert discover(with_intermediate_hop=False) != discover(with_intermediate_hop=True)
