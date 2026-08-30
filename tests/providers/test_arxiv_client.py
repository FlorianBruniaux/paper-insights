from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from paper_insights.adapters.providers.arxiv.client import (
    ArxivClient,
    ArxivClientConfig,
    ArxivProviderError,
)
from paper_insights.domain.acquisition import DiscoveryQuery
from paper_insights.domain.errors import ErrorCode

FIXTURES = Path(__file__).parents[1] / "fixtures" / "arxiv"
CAPTURE_ID = UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")


def make_client(
    handler: httpx.MockTransport,
    *,
    sleeps: list[float] | None = None,
    config: ArxivClientConfig | None = None,
) -> ArxivClient:
    return ArxivClient(
        http_client=httpx.Client(transport=handler),
        config=config or ArxivClientConfig(page_size=1),
        clock=lambda: datetime(2026, 8, 29, tzinfo=UTC),
        new_capture_id=lambda: CAPTURE_ID,
        sleep=(sleeps if sleeps is not None else []).append,
    )


def test_streaming_response_is_rejected_over_byte_limit() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"x" * 101, request=request)
    )
    client = make_client(
        transport,
        config=ArxivClientConfig(page_size=1, max_response_bytes=100),
    )

    with pytest.raises(ArxivProviderError) as raised:
        client.discover(DiscoveryQuery(text="bounded", limit=1))

    assert raised.value.code is ErrorCode.SOURCE_RESPONSE_TOO_LARGE


@pytest.mark.parametrize(
    "base_url",
    ("http://export.arxiv.org/api/query", "https://evil.example/api/query"),
)
def test_base_url_requires_https_and_an_allowlisted_host(base_url: str) -> None:
    with pytest.raises(ValueError):
        ArxivClientConfig(base_url=base_url)


def test_redirect_target_is_revalidated_before_following() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            302,
            headers={"Location": "https://evil.example/feed"},
            request=request,
        )

    client = make_client(httpx.MockTransport(handler))

    with pytest.raises(ArxivProviderError) as raised:
        client.discover(DiscoveryQuery(text="redirect", limit=1))

    assert calls == 1
    assert raised.value.code is ErrorCode.SOURCE_REDIRECT_REFUSED


def test_same_host_https_redirect_is_followed_under_a_bound() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/query":
            return httpx.Response(302, headers={"Location": "/api/redirected"}, request=request)
        return httpx.Response(
            200, content=(FIXTURES / "revision-v2.xml").read_bytes(), request=request
        )

    client = make_client(httpx.MockTransport(handler))
    batch = client.discover(DiscoveryQuery(text="redirect", limit=1))

    assert paths == ["/api/query", "/api/redirected"]
    assert len(batch.records) == 1


@pytest.mark.parametrize("first_status", (429, 500, 503))
def test_retryable_statuses_are_retried_and_retry_after_is_capped(first_status: int) -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(first_status, headers={"Retry-After": "50"}, request=request)
        return httpx.Response(
            200, content=(FIXTURES / "revision-v2.xml").read_bytes(), request=request
        )

    client = make_client(
        httpx.MockTransport(handler),
        sleeps=sleeps,
        config=ArxivClientConfig(page_size=1, max_retry_after=2.0),
    )

    assert len(client.discover(DiscoveryQuery(text="retry", limit=1)).records) == 1
    assert calls == 2
    assert sleeps == [2.0]


def test_timeout_retries_are_bounded() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("fixture timeout", request=request)

    client = make_client(
        httpx.MockTransport(handler),
        sleeps=sleeps,
        config=ArxivClientConfig(page_size=1, max_attempts=3, retry_backoff=0.25),
    )

    with pytest.raises(ArxivProviderError) as raised:
        client.discover(DiscoveryQuery(text="timeout", limit=1))

    assert calls == 3
    assert sleeps == [0.25, 0.5]
    assert raised.value.code is ErrorCode.SOURCE_TIMEOUT


@pytest.mark.parametrize(
    "error_type",
    (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError),
)
def test_non_timeout_transport_errors_use_the_closed_connection_code(
    error_type: type[httpx.TransportError],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise error_type("fixture transport failure", request=request)

    client = make_client(httpx.MockTransport(handler))

    with pytest.raises(ArxivProviderError) as raised:
        client.discover(DiscoveryQuery(text="transport", limit=1))

    assert calls == 1
    assert raised.value.code is ErrorCode.SOURCE_CONNECTION_FAILED


@pytest.mark.parametrize("status_code", (400, 401, 403, 404, 422))
def test_permanent_4xx_is_never_retried(status_code: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, request=request)

    client = make_client(httpx.MockTransport(handler))

    with pytest.raises(ArxivProviderError) as raised:
        client.discover(DiscoveryQuery(text="invalid", limit=1))

    assert calls == 1
    assert raised.value.code is ErrorCode.SOURCE_INVALID_PAYLOAD


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    ((429, ErrorCode.SOURCE_RATE_LIMITED), (503, ErrorCode.SOURCE_INVALID_PAYLOAD)),
)
def test_retryable_status_attempts_are_bounded(status_code: int, expected_code: ErrorCode) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, request=request)

    client = make_client(
        httpx.MockTransport(handler),
        config=ArxivClientConfig(page_size=1, max_attempts=3),
    )

    with pytest.raises(ArxivProviderError) as raised:
        client.discover(DiscoveryQuery(text="unavailable", limit=1))

    assert calls == 3
    assert raised.value.code is expected_code


def test_redirect_chain_is_bounded() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(302, headers={"Location": "/api/query"}, request=request)

    client = make_client(
        httpx.MockTransport(handler),
        config=ArxivClientConfig(page_size=1, max_redirects=1),
    )

    with pytest.raises(ArxivProviderError) as raised:
        client.discover(DiscoveryQuery(text="redirect-loop", limit=1))

    assert calls == 2
    assert raised.value.code is ErrorCode.SOURCE_REDIRECT_REFUSED


def test_duplicate_pages_cannot_exceed_the_configured_page_bound() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = (
            (FIXTURES / "page-1.xml")
            .read_bytes()
            .replace(
                b"<opensearch:totalResults>3</opensearch:totalResults>",
                b"<opensearch:totalResults>100</opensearch:totalResults>",
            )
        )
        return httpx.Response(200, content=payload, request=request)

    client = make_client(
        httpx.MockTransport(handler),
        config=ArxivClientConfig(page_size=2, max_pages=2),
    )

    with pytest.raises(ArxivProviderError) as raised:
        client.discover(DiscoveryQuery(text="duplicate", limit=3))

    assert calls == 2
    assert raised.value.code is ErrorCode.SOURCE_INVALID_PAYLOAD
