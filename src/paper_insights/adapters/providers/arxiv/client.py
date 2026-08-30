from __future__ import annotations

import hashlib
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit
from uuid import UUID

import httpx

from paper_insights.adapters.providers.arxiv.parser import parse_arxiv_feed
from paper_insights.domain.acquisition import (
    DiscoveryBatch,
    DiscoveryIssue,
    DiscoveryPage,
    DiscoveryQuery,
    DiscoveryRecord,
    ObservedPaperVersion,
)
from paper_insights.domain.errors import ErrorCode
from paper_insights.domain.identifiers import Sha256, SourceId

ARXIV_SOURCE = SourceId("arxiv")


class ArxivProviderError(RuntimeError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ArxivClientConfig:
    base_url: str = "https://export.arxiv.org/api/query"
    allowed_hosts: tuple[str, ...] = ("export.arxiv.org",)
    page_size: int = 50
    max_pages: int = 20
    max_response_bytes: int = 5 * 1024 * 1024
    timeout_seconds: float = 20.0
    max_attempts: int = 3
    max_redirects: int = 3
    retry_backoff: float = 0.5
    max_retry_after: float = 10.0
    user_agent: str = "paper-insights/0.1"

    def __post_init__(self) -> None:
        if not self.allowed_hosts or any(not host for host in self.allowed_hosts):
            raise ValueError("at least one allowed arXiv host is required")
        _validate_url(self.base_url, frozenset(self.allowed_hosts))
        if not 1 <= self.page_size <= 100:
            raise ValueError("arXiv page size must be between 1 and 100")
        if self.max_pages < 1:
            raise ValueError("arXiv page limit must be positive")
        if self.max_response_bytes < 1:
            raise ValueError("arXiv response byte limit must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("arXiv timeout must be positive")
        if self.max_attempts < 1:
            raise ValueError("arXiv attempts must be positive")
        if self.max_redirects < 0:
            raise ValueError("arXiv redirect limit cannot be negative")
        if self.retry_backoff < 0 or self.max_retry_after < 0:
            raise ValueError("arXiv retry delays cannot be negative")
        if not self.user_agent.strip():
            raise ValueError("arXiv user agent is required")


@dataclass(frozen=True, slots=True)
class _FetchedPage:
    payload: bytes
    media_type: str
    request_trace: tuple[str, ...]


class _RetryableStatus(Exception):
    def __init__(self, status_code: int, retry_after: str | None) -> None:
        super().__init__(str(status_code))
        self.status_code = status_code
        self.retry_after = retry_after


def _validate_url(url: str, allowed_hosts: frozenset[str]) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise ValueError("arXiv URL must use HTTPS on an allowed host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("arXiv URL cannot contain credentials")


def _new_uuid7() -> UUID:
    timestamp_ms = time.time_ns() // 1_000_000
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = timestamp_ms << 80
    value |= 0x7 << 76
    value |= random_a << 64
    value |= 0b10 << 62
    value |= random_b
    return UUID(int=value)


def _quoted(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _search_query(query: DiscoveryQuery) -> str:
    clauses: list[str] = []
    if query.text:
        clauses.append(f"all:{_quoted(query.text)}")
    clauses.extend(f"cat:{category}" for category in query.categories)
    clauses.extend(f"au:{_quoted(author)}" for author in query.authors)
    clauses.extend(f"id:{identifier}" for identifier in query.identifiers)
    if query.date_from is not None or query.date_to is not None:
        lower = query.date_from.astimezone(UTC).strftime("%Y%m%d%H%M") if query.date_from else "*"
        upper = query.date_to.astimezone(UTC).strftime("%Y%m%d%H%M") if query.date_to else "*"
        clauses.append(f"submittedDate:[{lower} TO {upper}]")
    return " AND ".join(clauses)


class ArxivClient:
    source_id = ARXIV_SOURCE

    def __init__(
        self,
        *,
        http_client: httpx.Client,
        config: ArxivClientConfig | None = None,
        clock: Callable[[], datetime] | None = None,
        new_capture_id: Callable[[], UUID] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._http = http_client
        self._config = config or ArxivClientConfig()
        self._allowed_hosts = frozenset(self._config.allowed_hosts)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._new_capture_id = new_capture_id or _new_uuid7
        self._sleep = sleep or time.sleep

    def discover(self, query: DiscoveryQuery) -> DiscoveryBatch:
        try:
            start = int(query.cursor) if query.cursor is not None else 0
        except ValueError as exc:
            raise ValueError("arXiv cursor must be a non-negative integer") from exc
        if start < 0:
            raise ValueError("arXiv cursor must be a non-negative integer")

        pages: list[DiscoveryPage] = []
        observations: list[ObservedPaperVersion] = []
        issues: list[DiscoveryIssue] = []
        seen_versions: set[str] = set()
        page_ordinal = 0

        while len(observations) < query.limit:
            requested = min(self._config.page_size, query.limit - len(observations))
            params = {
                "max_results": str(requested),
                "search_query": _search_query(query),
                "sortBy": "submittedDate",
                "sortOrder": "ascending",
                "start": str(start),
            }
            fetched = self._fetch_page(params)
            try:
                parsed = parse_arxiv_feed(fetched.payload, page_ordinal=page_ordinal)
            except ValueError as exc:
                raise ArxivProviderError(
                    ErrorCode.SOURCE_INVALID_PAYLOAD, "arXiv returned invalid Atom XML"
                ) from exc

            page_records: list[DiscoveryRecord] = []
            for record in parsed.records:
                observation = record.observation
                if observation is None:
                    page_records.append(record)
                    continue
                if (
                    observation.source_version_key in seen_versions
                    or len(observations) >= query.limit
                ):
                    page_records.append(replace(record, observation=None))
                    continue
                seen_versions.add(observation.source_version_key)
                observations.append(observation)
                page_records.append(record)

            next_start = start + len(parsed.records)
            has_more = bool(parsed.records) and (
                parsed.total_results is None or next_start < parsed.total_results
            )
            next_cursor = str(next_start) if has_more and len(observations) < query.limit else None
            request_fingerprint = Sha256(
                hashlib.sha256(
                    json.dumps(
                        {
                            "request_trace": list(fetched.request_trace),
                            "schema_version": "arxiv-request-fingerprint-v1",
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
            )
            pages.append(
                DiscoveryPage(
                    capture_id=self._new_capture_id(),
                    records=tuple(page_records),
                    raw_payload=fetched.payload,
                    media_type=fetched.media_type,
                    retrieved_at=self._clock(),
                    request_fingerprint=request_fingerprint,
                    next_cursor=next_cursor,
                )
            )
            issues.extend(parsed.issues)
            if next_cursor is None:
                break
            if len(pages) >= self._config.max_pages:
                raise ArxivProviderError(
                    ErrorCode.SOURCE_INVALID_PAYLOAD,
                    "arXiv pagination exceeded the page limit",
                )
            start = next_start
            page_ordinal += 1

        return DiscoveryBatch(
            source_id=self.source_id,
            query=query,
            pages=tuple(pages),
            records=tuple(observations),
            issues=tuple(issues),
        )

    def _fetch_page(self, params: dict[str, str]) -> _FetchedPage:
        last_status: int | None = None
        for attempt in range(self._config.max_attempts):
            try:
                return self._fetch_with_redirects(params)
            except httpx.TimeoutException as exc:
                if attempt + 1 == self._config.max_attempts:
                    raise ArxivProviderError(
                        ErrorCode.SOURCE_TIMEOUT, "arXiv request timed out"
                    ) from exc
                self._sleep(self._retry_delay(None, attempt))
            except httpx.TransportError as exc:
                raise ArxivProviderError(
                    ErrorCode.SOURCE_CONNECTION_FAILED,
                    "arXiv transport failed",
                ) from exc
            except _RetryableStatus as exc:
                last_status = exc.status_code
                if attempt + 1 == self._config.max_attempts:
                    code = (
                        ErrorCode.SOURCE_RATE_LIMITED
                        if exc.status_code == 429
                        else ErrorCode.SOURCE_INVALID_PAYLOAD
                    )
                    raise ArxivProviderError(code, "arXiv remained unavailable") from exc
                self._sleep(self._retry_delay(exc.retry_after, attempt))
        raise ArxivProviderError(
            ErrorCode.SOURCE_INVALID_PAYLOAD,
            f"arXiv request failed with status {last_status or 'unknown'}",
        )

    def _fetch_with_redirects(self, params: dict[str, str]) -> _FetchedPage:
        url = self._config.base_url
        request_params: dict[str, str] | None = params
        request_trace: list[str] = []
        for redirect_count in range(self._config.max_redirects + 1):
            try:
                _validate_url(url, self._allowed_hosts)
            except ValueError as exc:
                raise ArxivProviderError(
                    ErrorCode.SOURCE_REDIRECT_REFUSED, "arXiv redirect target was refused"
                ) from exc
            with self._http.stream(
                "GET",
                url,
                params=request_params,
                headers={"Accept": "application/atom+xml", "User-Agent": self._config.user_agent},
                timeout=self._config.timeout_seconds,
                follow_redirects=False,
            ) as response:
                request_trace.append(str(response.request.url))
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if location is None or redirect_count == self._config.max_redirects:
                        raise ArxivProviderError(
                            ErrorCode.SOURCE_REDIRECT_REFUSED,
                            "arXiv redirect limit was exceeded",
                        )
                    url = urljoin(str(response.request.url), location)
                    request_params = None
                    continue
                if response.status_code == 429 or 500 <= response.status_code <= 599:
                    raise _RetryableStatus(
                        response.status_code, response.headers.get("Retry-After")
                    )
                if 400 <= response.status_code <= 499:
                    raise ArxivProviderError(
                        ErrorCode.SOURCE_INVALID_PAYLOAD, "arXiv rejected the request"
                    )
                if response.status_code < 200 or response.status_code >= 300:
                    raise ArxivProviderError(
                        ErrorCode.SOURCE_INVALID_PAYLOAD, "arXiv returned an unexpected status"
                    )
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > self._config.max_response_bytes:
                        raise ArxivProviderError(
                            ErrorCode.SOURCE_RESPONSE_TOO_LARGE,
                            "arXiv response exceeded the byte limit",
                        )
                    chunks.append(chunk)
                media_type = response.headers.get("Content-Type", "application/atom+xml")
                return _FetchedPage(
                    payload=b"".join(chunks),
                    media_type=media_type.split(";", 1)[0].strip(),
                    request_trace=tuple(request_trace),
                )
        raise ArxivProviderError(
            ErrorCode.SOURCE_REDIRECT_REFUSED, "arXiv redirect limit was exceeded"
        )

    def _retry_delay(self, retry_after: str | None, attempt: int) -> float:
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                try:
                    when = parsedate_to_datetime(retry_after)
                    if when.tzinfo is None or when.utcoffset() is None:
                        raise ValueError("Retry-After date is not timezone-aware")
                    delay = max(0.0, (when.astimezone(UTC) - self._clock()).total_seconds())
                except (TypeError, ValueError):
                    delay = self._config.retry_backoff * (2**attempt)
        else:
            delay = self._config.retry_backoff * (2**attempt)
        return min(max(0.0, delay), self._config.max_retry_after)
