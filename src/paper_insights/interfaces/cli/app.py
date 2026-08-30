from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import TextIO

from paper_insights.application.diagnostics import DoctorService
from paper_insights.application.ingestion.execute import ExecutePreparedIngestion
from paper_insights.application.ingestion.prepare import PrepareDiscovery
from paper_insights.application.ingestion.repair import RepairInterruptedRuns
from paper_insights.application.research.citations import CitationService
from paper_insights.application.research.collections import CollectionService
from paper_insights.application.research.index import RebuildSearchIndex
from paper_insights.application.research.search import LocalSearch
from paper_insights.config import Settings, SettingsError
from paper_insights.domain.errors import ERROR_EXIT_CODES, ErrorCode, ExitCode
from paper_insights.interfaces.cli.citations import (
    citation_data,
    citation_format,
    paper_version_id,
)
from paper_insights.interfaces.cli.collections import (
    collection_data,
    paper_selector,
    resolve_collection,
)
from paper_insights.interfaces.cli.discover import discovery_query, prepared_data, render_prepared
from paper_insights.interfaces.cli.doctor import render_doctor
from paper_insights.interfaces.cli.envelopes import CliEnvelope, CliErrorEnvelope
from paper_insights.interfaces.cli.index import published_index_data
from paper_insights.interfaces.cli.ingest import ingestion_data
from paper_insights.interfaces.cli.repair import preview_data, repair_results_data
from paper_insights.interfaces.cli.search import (
    paper_query,
    paper_result_data,
    passage_query,
    passage_result_data,
    render_paper_result,
)


class CorpusUnavailableError(RuntimeError):
    pass


DiscoverFactory = Callable[[Settings, str], AbstractContextManager[PrepareDiscovery]]
IngestionFactory = Callable[[Settings], AbstractContextManager[ExecutePreparedIngestion]]
CollectionsFactory = Callable[[Settings], AbstractContextManager[CollectionService]]
SearchFactory = Callable[[Settings], AbstractContextManager[LocalSearch]]
IndexFactory = Callable[[Settings], AbstractContextManager[RebuildSearchIndex]]
CitationFactory = Callable[[Settings], AbstractContextManager[CitationService]]
RepairFactory = Callable[[Settings, int], AbstractContextManager[RepairInterruptedRuns]]
DEFAULT_REPAIR_STALE_AFTER_SECONDS = 86_400


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper-insights")
    parser.add_argument("--config", type=Path)
    subcommands = parser.add_subparsers(dest="command", required=True)
    doctor = subcommands.add_parser("doctor")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    discover = subcommands.add_parser("discover")
    _add_discovery_arguments(discover)
    ingest = subcommands.add_parser("ingest")
    _add_discovery_arguments(ingest)
    ingest.add_argument("--yes", action="store_true", dest="confirmed")
    collections = subcommands.add_parser("collections")
    collection_commands = collections.add_subparsers(dest="collection_command", required=True)
    create = collection_commands.add_parser("create")
    create.add_argument("collection")
    create.add_argument("--title", required=True)
    _add_json_flag(create)
    rename = collection_commands.add_parser("rename")
    rename.add_argument("collection")
    rename.add_argument("--title", required=True)
    _add_json_flag(rename)
    add = collection_commands.add_parser("add")
    add.add_argument("collection")
    add.add_argument("paper")
    add.add_argument("--note")
    _add_json_flag(add)
    remove = collection_commands.add_parser("remove")
    remove.add_argument("collection")
    remove.add_argument("paper")
    _add_json_flag(remove)
    list_command = collection_commands.add_parser("list")
    _add_json_flag(list_command)
    search = subcommands.add_parser("search")
    search_commands = search.add_subparsers(dest="search_command", required=True)
    for name in ("papers", "passages"):
        search_command = search_commands.add_parser(name)
        search_command.add_argument("query")
        search_command.add_argument("--source")
        search_command.add_argument("--category")
        search_command.add_argument("--author")
        search_command.add_argument("--language")
        search_command.add_argument("--from", dest="date_from")
        search_command.add_argument("--to", dest="date_to")
        search_command.add_argument("--collection")
        search_command.add_argument("--limit", type=int)
        _add_json_flag(search_command)
    index = subcommands.add_parser("index")
    index_commands = index.add_subparsers(dest="index_command", required=True)
    rebuild = index_commands.add_parser("rebuild")
    rebuild.add_argument("--chunk-schema-version", default="chunk-v1")
    _add_json_flag(rebuild)
    cite = subcommands.add_parser("cite")
    cite.add_argument("paper")
    cite.add_argument("--paper-version-id")
    cite.add_argument("--format", required=True, choices=("bibtex", "markdown", "csl-json"))
    _add_json_flag(cite)
    repair = subcommands.add_parser("repair")
    repair_commands = repair.add_subparsers(dest="repair_command", required=True)
    interrupted = repair_commands.add_parser("interrupted-runs")
    interrupted.add_argument(
        "--stale-after-seconds",
        type=int,
        default=DEFAULT_REPAIR_STALE_AFTER_SECONDS,
    )
    interrupted.add_argument("--yes", action="store_true", dest="confirmed")
    _add_json_flag(interrupted)
    return parser


def _add_discovery_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source")
    parser.add_argument("query", nargs="?")
    parser.add_argument("--category", action="append", default=[], dest="categories")
    parser.add_argument("--author", action="append", default=[], dest="authors")
    parser.add_argument("--identifier", action="append", default=[], dest="identifiers")
    parser.add_argument("--from", dest="date_from")
    parser.add_argument("--to", dest="date_to")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--cursor")
    parser.add_argument("--json", action="store_true", dest="as_json")


def _add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", dest="as_json")


def run(
    argv: Sequence[str] | None = None,
    *,
    doctor_service_factory: Callable[[Settings], DoctorService],
    discover_service_factory: DiscoverFactory | None = None,
    ingestion_service_factory: IngestionFactory | None = None,
    collections_service_factory: CollectionsFactory | None = None,
    search_service_factory: SearchFactory | None = None,
    index_service_factory: IndexFactory | None = None,
    citation_service_factory: CitationFactory | None = None,
    repair_service_factory: RepairFactory | None = None,
    environ: Mapping[str, str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output = sys.stdout if stdout is None else stdout
    error_output = sys.stderr if stderr is None else stderr
    input_stream = sys.stdin if stdin is None else stdin
    arguments = _parser().parse_args(argv)
    try:
        settings = Settings.load(
            config_path=arguments.config,
            environ=os.environ if environ is None else environ,
        )
    except SettingsError:
        error = {
            "error": {"code": "invalid_configuration"},
            "schema_version": "paper-insights.error.v1",
        }
        error_output.write(json.dumps(error, sort_keys=True) + "\n")
        return int(ExitCode.INVALID)

    if arguments.command == "doctor":
        report = doctor_service_factory(settings).inspect()
        output.write(render_doctor(report, as_json=arguments.as_json))
        return int(ExitCode.SUCCESS if report.is_complete else ExitCode.CORPUS_INVALID)
    try:
        if arguments.command == "discover":
            if discover_service_factory is None:
                return _runtime_unavailable(error_output)
            with discover_service_factory(settings, arguments.source) as service:
                prepared = service.prepare(discovery_query(arguments))
                _write_result(
                    output,
                    operation="discover",
                    data=prepared_data(prepared),
                    as_json=arguments.as_json,
                    human=render_prepared(prepared, as_json=False),
                )
                return int(ExitCode.SUCCESS)
        if arguments.command == "ingest":
            if discover_service_factory is None:
                return _runtime_unavailable(error_output)
            with discover_service_factory(settings, arguments.source) as service:
                prepared = service.prepare(discovery_query(arguments))
            confirmed = arguments.confirmed
            if not confirmed:
                _write_result(
                    output,
                    operation="ingest",
                    data=prepared_data(prepared),
                    as_json=arguments.as_json,
                    human=render_prepared(prepared, as_json=False),
                )
                if not input_stream.isatty():
                    return int(ExitCode.CONFIRMATION_REQUIRED)
                output.flush()
                error_output.write("Confirm ingestion [y/N]: ")
                error_output.flush()
                confirmed = input_stream.readline().strip().lower() in {"y", "yes"}
                if not confirmed:
                    return int(ExitCode.CONFIRMATION_REQUIRED)
            if ingestion_service_factory is None:
                return _runtime_unavailable(error_output)
            with ingestion_service_factory(settings) as service:
                summary = service.execute(prepared, confirmation=prepared.digest)
                _write_result(
                    output,
                    operation="ingest",
                    data=ingestion_data(summary),
                    as_json=arguments.as_json,
                    human=f"ingestion: {summary.counters.status}\n",
                )
                return int(
                    ExitCode.PARTIAL if summary.counters.failed_records else ExitCode.SUCCESS
                )
        if arguments.command == "collections":
            if collections_service_factory is None:
                return _runtime_unavailable(error_output)
            with collections_service_factory(settings) as service:
                command = arguments.collection_command
                collection_payload: dict[str, object]
                if command == "create":
                    collection = service.create(
                        slug=arguments.collection,
                        title=arguments.title,
                    )
                    collection_payload = {"collection": collection_data(collection)}
                elif command == "list":
                    collection_payload = {
                        "collections": [collection_data(item) for item in service.list()]
                    }
                else:
                    collection_id = resolve_collection(service, arguments.collection)
                    if command == "rename":
                        collection = service.rename(collection_id, title=arguments.title)
                    elif command == "add":
                        collection = service.add(
                            collection_id,
                            paper_selector(arguments.paper),
                            note=arguments.note,
                        )
                    elif command == "remove":
                        collection = service.remove(
                            collection_id,
                            paper_selector(arguments.paper),
                        )
                    else:
                        raise ValueError("unsupported collection command")
                    collection_payload = {"collection": collection_data(collection)}
                _write_result(
                    output,
                    operation=f"collections.{command}",
                    data=collection_payload,
                    as_json=arguments.as_json,
                    human=f"collections.{command}: ok\n",
                )
                return int(ExitCode.SUCCESS)
        if arguments.command == "search":
            if search_service_factory is None:
                return _runtime_unavailable(error_output)
            limit = settings.search.default_limit if arguments.limit is None else arguments.limit
            if not 1 <= limit <= settings.search.maximum_limit:
                raise ValueError("search limit is outside configured bounds")
            arguments.limit = limit
            with search_service_factory(settings) as service:
                if arguments.search_command == "papers":
                    paper_search = service.search_papers(paper_query(arguments))
                    search_payload = paper_result_data(paper_search)
                    coverage = paper_search.coverage.value
                    truncated = paper_search.truncated
                    returned = paper_search.returned
                    available = paper_search.available
                    human_search = render_paper_result(paper_search)
                else:
                    passage_search = service.search_passages(passage_query(arguments))
                    search_payload = passage_result_data(passage_search)
                    coverage = passage_search.coverage.value
                    truncated = passage_search.truncated
                    returned = passage_search.returned
                    available = passage_search.available
                    human_search = f"search.{arguments.search_command}: {returned} result(s)\n"
                _write_result(
                    output,
                    operation=f"search.{arguments.search_command}",
                    data=search_payload,
                    as_json=arguments.as_json,
                    human=human_search,
                    coverage=coverage,
                    truncated=truncated,
                    returned=returned,
                    available=available,
                )
                return int(ExitCode.SUCCESS)
        if arguments.command == "index":
            if index_service_factory is None:
                return _runtime_unavailable(error_output)
            with index_service_factory(settings) as service:
                published = service.execute(chunk_schema_version=arguments.chunk_schema_version)
                _write_result(
                    output,
                    operation="index.rebuild",
                    data=published_index_data(published),
                    as_json=arguments.as_json,
                    human=f"index.rebuild: generation {published.generation}\n",
                )
                return int(ExitCode.SUCCESS)
        if arguments.command == "cite":
            if citation_service_factory is None:
                return _runtime_unavailable(error_output)
            with citation_service_factory(settings) as service:
                citation = service.render(
                    paper_selector(arguments.paper),
                    citation_format(arguments.format),
                    paper_version_id=paper_version_id(arguments.paper_version_id),
                )
                _write_result(
                    output,
                    operation="cite",
                    data=citation_data(citation),
                    as_json=arguments.as_json,
                    human=citation.content + "\n",
                    coverage=citation.coverage.value,
                )
                return int(ExitCode.SUCCESS)
        if arguments.command == "repair":
            if repair_service_factory is None:
                return _runtime_unavailable(error_output)
            if arguments.stale_after_seconds <= 0:
                raise ValueError("repair age must be positive")
            with repair_service_factory(settings, arguments.stale_after_seconds) as service:
                preview = service.preview()
                if not arguments.confirmed:
                    _write_result(
                        output,
                        operation="repair.interrupted-runs",
                        data=preview_data(preview),
                        as_json=arguments.as_json,
                        human=f"repair: {len(preview.candidates)} candidate(s)\n",
                    )
                    return int(ExitCode.CONFIRMATION_REQUIRED)
                results = service.execute(preview, confirmed=True)
                _write_result(
                    output,
                    operation="repair.interrupted-runs",
                    data=repair_results_data(results),
                    as_json=arguments.as_json,
                    human=f"repair: {len(results)} result(s)\n",
                )
                return int(ExitCode.SUCCESS)
    except CorpusUnavailableError:
        _write_error(error_output, "corpus_unavailable")
        return int(ExitCode.CORPUS_INVALID)
    except (LookupError, OSError, RuntimeError, ValueError) as exc:
        provider_code = getattr(exc, "code", None)
        if isinstance(provider_code, ErrorCode):
            _write_error(error_output, provider_code.value)
            return int(ERROR_EXIT_CODES[provider_code])
        _write_error(error_output, "invalid_request")
        return int(ExitCode.INVALID)
    return int(ExitCode.INVALID)


def _write_result(
    output: TextIO,
    *,
    operation: str,
    data: dict[str, object],
    as_json: bool,
    human: str,
    coverage: str = "complete",
    truncated: bool = False,
    returned: int | None = None,
    available: int | None = None,
) -> None:
    if not as_json:
        output.write(human)
        return
    envelope_data: dict[str, object] = {
        "schema_version": "paper-insights.cli.v1",
        "operation": operation,
        "data": data,
        "coverage": {"status": coverage},
        "errors": [],
        "truncated": truncated,
    }
    if returned is not None:
        envelope_data["returned"] = returned
        envelope_data["available"] = available
    envelope = CliEnvelope.model_validate(envelope_data)
    output.write(envelope.model_dump_json(exclude_none=True, by_alias=True) + "\n")


def _write_error(output: TextIO, code: str) -> None:
    payload = CliErrorEnvelope.model_validate(
        {
            "error": {"code": code},
            "schema_version": "paper-insights.error.v1",
        }
    )
    output.write(payload.model_dump_json() + "\n")


def _runtime_unavailable(output: TextIO) -> int:
    _write_error(output, "runtime_unavailable")
    return int(ExitCode.CORPUS_INVALID)
