#!/usr/bin/env python3
"""Claude Code PreToolUse guard for project-local destructive actions."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from typing import NoReturn


SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".pypirc",
    "credentials.json",
    "id_ed25519",
    "id_rsa",
    "serviceAccountKey.json",
    "secrets.yaml",
    "secrets.yml",
}

ROOT_DELETE = re.compile(
    r"(?:^|[;&|]\s*)rm\s+(?:-[A-Za-z]*[rR][A-Za-z]*\s+|--recursive\s+)"
    r"(?:-[A-Za-z]+\s+)*(?:/|/\*|~|\$HOME|\$\{HOME\})(?:\s|$|[;&|])"
)
BROAD_STAGE = re.compile(r"(?:^|[;&|]\s*)git\s+add\s+(?:\.|-A|--all)(?:\s*$|\s*[;&|])")
DESTRUCTIVE_GIT = re.compile(
    r"(?:^|[;&|]\s*)git\s+(?:reset\s+--hard|clean\s+(?:-[A-Za-z]*f[A-Za-z]*d|-[A-Za-z]*d[A-Za-z]*f))\b"
)


def block(message: str) -> NoReturn:
    print(f"BLOCKED: {message}", file=sys.stderr)
    raise SystemExit(2)


def load_event() -> dict[str, object]:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as error:
        block(f"invalid hook input: {error}")
    if not isinstance(payload, dict):
        block("hook input must be a JSON object")
    return payload


def resolved_project_root() -> Path:
    value = os.environ.get("CLAUDE_PROJECT_DIR")
    if not value:
        block("CLAUDE_PROJECT_DIR is not set")
    root = Path(value).expanduser().resolve(strict=True)
    if not root.is_dir():
        block("CLAUDE_PROJECT_DIR is not a directory")
    return root


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def check_file_write(tool_input: dict[str, object], root: Path) -> None:
    raw_path = tool_input.get("file_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        block("write tool did not provide a file_path")

    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)

    if not is_within(resolved, root):
        block(f"write outside project: {resolved}")
    if resolved.name in SENSITIVE_NAMES or resolved.name.startswith(".env."):
        block(f"sensitive file write: {resolved.name}")

    data_root = (root / "data").resolve(strict=False)
    if is_within(resolved, data_root):
        block("direct corpus writes are forbidden; use the ingestion service")


def check_bash(tool_input: dict[str, object]) -> None:
    command = tool_input.get("command")
    if not isinstance(command, str):
        block("Bash tool did not provide a command")

    if ROOT_DELETE.search(f"{command} "):
        block("recursive delete of a root target")
    if (
        re.search(r"\bgit\s+push\b", command)
        and re.search(r"(?:--force(?:-with-lease)?|-f)\b", command)
        and re.search(r"\b(?:main|master)\b", command)
    ):
        block("force push to main or master")
    if BROAD_STAGE.search(command):
        block("broad staging is forbidden; use explicit pathspecs")
    if DESTRUCTIVE_GIT.search(command):
        block("destructive Git cleanup discards work")

    normalized = " ".join(command.split())
    forbidden = {
        "--no-preserve-root": "root preservation bypass",
    }
    for pattern, reason in forbidden.items():
        if pattern in normalized:
            block(reason)


def main() -> int:
    event = load_event()
    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        block("tool_input must be a JSON object")

    if tool_name in {"Edit", "Write"}:
        check_file_write(tool_input, resolved_project_root())
    elif tool_name == "Bash":
        check_bash(tool_input)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
