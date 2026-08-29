from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

from paper_insights.config import Settings, SettingsError
from paper_insights.domain.errors import ExitCode
from paper_insights.interfaces.cli.doctor import inspect_corpus


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper-insights")
    parser.add_argument("--config", type=Path)
    subcommands = parser.add_subparsers(dest="command", required=True)
    doctor = subcommands.add_parser("doctor")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output = sys.stdout if stdout is None else stdout
    error_output = sys.stderr if stderr is None else stderr
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
        report = inspect_corpus(settings)
        if arguments.as_json:
            output.write(json.dumps(report.as_envelope(), sort_keys=True) + "\n")
        else:
            output.write(f"doctor: {report.status}\n")
        return int(ExitCode.CORPUS_INVALID if report.is_invalid else ExitCode.SUCCESS)
    return int(ExitCode.INVALID)
