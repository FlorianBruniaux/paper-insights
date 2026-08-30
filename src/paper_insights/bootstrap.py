from __future__ import annotations

import secrets
import sqlite3
import stat
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import TextIO
from uuid import UUID

import httpx
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from paper_insights.adapters.artifacts.filesystem.store import FilesystemBlobStore
from paper_insights.adapters.catalog.sqlite.engine import create_catalog_engine
from paper_insights.adapters.catalog.sqlite.readers import (
    SqliteCatalogReader,
    SqliteCatalogRevisionGuard,
)
from paper_insights.adapters.catalog.sqlite.uow import SqliteCatalogUnitOfWorkFactory
from paper_insights.adapters.diagnostics.sqlite import SqliteCatalogDiagnostics
from paper_insights.adapters.providers.arxiv.client import ArxivClient, ArxivClientConfig
from paper_insights.adapters.providers.arxiv.normalizer import normalized_metadata_payload
from paper_insights.adapters.search.sqlite_fts.builder import SqliteFtsIndexBuilder
from paper_insights.adapters.search.sqlite_fts.reader import SqliteFtsSearchReader
from paper_insights.application.diagnostics import DoctorService
from paper_insights.application.ingestion.execute import ExecutePreparedIngestion
from paper_insights.application.ingestion.prepare import PrepareDiscovery
from paper_insights.application.ingestion.repair import RepairInterruptedRuns
from paper_insights.application.ports.clock import Clock
from paper_insights.application.ports.ids import IdGenerator
from paper_insights.application.research.citations import (
    CitationService,
    SourceBackedCitationRenderer,
)
from paper_insights.application.research.collections import CollectionService
from paper_insights.application.research.index import RebuildSearchIndex
from paper_insights.application.research.search import LocalSearch
from paper_insights.config import Settings
from paper_insights.interfaces.cli.app import CorpusUnavailableError, run


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class UUIDv7Generator:
    def new(self) -> UUID:
        timestamp_ms = time.time_ns() // 1_000_000
        value = timestamp_ms << 80
        value |= 0x7 << 76
        value |= secrets.randbits(12) << 64
        value |= 0b10 << 62
        value |= secrets.randbits(62)
        return UUID(int=value)


def build_doctor_service(settings: Settings) -> DoctorService:
    paths = settings.paths
    return DoctorService(SqliteCatalogDiagnostics(paths), FilesystemBlobStore(paths))


def _provider(
    settings: Settings,
    source: str,
    client: httpx.Client,
    *,
    clock: Clock,
    new_capture_id: Callable[[], UUID] | None = None,
) -> ArxivClient:
    if source != "arxiv" or not settings.arxiv.enabled:
        raise ValueError("unsupported or disabled source")
    return ArxivClient(
        http_client=client,
        config=ArxivClientConfig(
            page_size=settings.arxiv.page_size,
            timeout_seconds=settings.request_timeout_seconds,
            user_agent=settings.user_agent,
        ),
        clock=clock.now,
        new_capture_id=new_capture_id,
    )


@contextmanager
def discover_service(
    settings: Settings,
    source: str,
    *,
    transport: httpx.BaseTransport | None = None,
    clock: Clock | None = None,
    new_capture_id: Callable[[], UUID] | None = None,
) -> Iterator[PrepareDiscovery]:
    active_clock = clock or SystemClock()
    with httpx.Client(transport=transport) as client:
        yield PrepareDiscovery(
            provider=_provider(
                settings,
                source,
                client,
                clock=active_clock,
                new_capture_id=new_capture_id,
            ),
            clock=active_clock,
        )


def _catalog_runtime(
    settings: Settings,
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
) -> tuple[
    Engine,
    Clock,
    IdGenerator,
    SqliteCatalogReader,
    SqliteCatalogUnitOfWorkFactory,
]:
    catalog = settings.paths.catalog
    try:
        status = catalog.lstat()
    except FileNotFoundError as exc:
        raise CorpusUnavailableError("catalogue is not initialized") from exc
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
        raise CorpusUnavailableError("catalogue path is unsafe")
    active_clock = clock or SystemClock()
    active_ids = ids or UUIDv7Generator()
    engine = create_catalog_engine(catalog)
    reader = SqliteCatalogReader(engine)
    unit_of_work = SqliteCatalogUnitOfWorkFactory(
        engine=engine,
        clock=active_clock,
        ids=active_ids,
    )
    return engine, active_clock, active_ids, reader, unit_of_work


@contextmanager
def _closed_database_errors() -> Iterator[None]:
    try:
        yield
    except (SQLAlchemyError, sqlite3.DatabaseError) as exc:
        raise CorpusUnavailableError("corpus database is unavailable") from exc


@contextmanager
def ingestion_service(
    settings: Settings,
    *,
    clock: Clock | None = None,
    ids: IdGenerator | None = None,
) -> Iterator[ExecutePreparedIngestion]:
    with _closed_database_errors():
        engine, active_clock, active_ids, _reader, unit_of_work = _catalog_runtime(
            settings, clock=clock, ids=ids
        )
        try:
            yield ExecutePreparedIngestion(
                blobs=FilesystemBlobStore(settings.paths),
                catalog=unit_of_work,
                clock=active_clock,
                ids=active_ids,
                metadata_payload=normalized_metadata_payload,
            )
        finally:
            engine.dispose()


@contextmanager
def collections_service(settings: Settings) -> Iterator[CollectionService]:
    with _closed_database_errors():
        engine, _clock, _ids, reader, unit_of_work = _catalog_runtime(settings)
        try:
            yield CollectionService(unit_of_work, reader)
        finally:
            engine.dispose()


@contextmanager
def search_service(settings: Settings) -> Iterator[LocalSearch]:
    with _closed_database_errors():
        engine, _clock, _ids, reader, _unit = _catalog_runtime(settings)
        try:
            yield LocalSearch(
                SqliteFtsSearchReader(
                    settings.paths.search_index,
                    reader,
                    corpus_root=settings.paths.data_root,
                )
            )
        finally:
            engine.dispose()


@contextmanager
def index_service(settings: Settings) -> Iterator[RebuildSearchIndex]:
    with _closed_database_errors():
        engine, _clock, _ids, reader, _unit = _catalog_runtime(settings)
        try:
            yield RebuildSearchIndex(
                catalog=reader,
                builder=SqliteFtsIndexBuilder(
                    settings.paths.search_index,
                    corpus_root=settings.paths.data_root,
                ),
                revision_guard=SqliteCatalogRevisionGuard(engine),
            )
        finally:
            engine.dispose()


@contextmanager
def citation_service(settings: Settings) -> Iterator[CitationService]:
    with _closed_database_errors():
        engine, _clock, _ids, reader, _unit = _catalog_runtime(settings)
        try:
            yield CitationService(reader, SourceBackedCitationRenderer())
        finally:
            engine.dispose()


@contextmanager
def repair_service(
    settings: Settings,
    stale_after_seconds: int,
) -> Iterator[RepairInterruptedRuns]:
    with _closed_database_errors():
        engine, clock, _ids, reader, unit_of_work = _catalog_runtime(settings)
        try:
            yield RepairInterruptedRuns(
                reader=reader,
                catalog=unit_of_work,
                clock=clock,
                stale_after=timedelta(seconds=stale_after_seconds),
            )
        finally:
            engine.dispose()


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    return run(
        argv,
        doctor_service_factory=build_doctor_service,
        discover_service_factory=discover_service,
        ingestion_service_factory=ingestion_service,
        collections_service_factory=collections_service,
        search_service_factory=search_service,
        index_service_factory=index_service,
        citation_service_factory=citation_service,
        repair_service_factory=repair_service,
        environ=environ,
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )
