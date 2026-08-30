#!/usr/bin/env python3
"""Validate the documentation and local agent scaffold without dependencies."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 can still run the dependency-free hook checks.
    tomllib = None


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "docs/VISION.md",
    "docs/ARCHITECTURE.md",
    "docs/ROADMAP.md",
    "docs/specs/PRODUCT.md",
    "docs/specs/DATA-MODEL.md",
    "docs/specs/INGESTION.md",
    "docs/specs/SEARCH-AND-MCP.md",
    "docs/decisions/ADR-0001-python-sqlite.md",
    ".claude/settings.json",
    "tests/hooks/test_project_guard.py",
    "tests/hooks/test_research_router.py",
)
FRONTMATTER_NAME = re.compile(r"^---\n.*?^name:\s*([^\n]+)$.*?^---$", re.MULTILINE | re.DOTALL)


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def validate_required_files(failures: list[str]) -> None:
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            fail(f"missing required file: {relative}", failures)


def validate_json(failures: list[str]) -> None:
    settings_path = ROOT / ".claude" / "settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"invalid Claude settings: {error}", failures)
        return
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict) or set(hooks) != {"PreToolUse", "UserPromptSubmit"}:
        fail("Claude settings must register the exact initial hook events", failures)


def validate_toml(failures: list[str]) -> None:
    if tomllib is None:
        return
    for relative in ("pyproject.toml", "config.example.toml"):
        path = ROOT / relative
        try:
            tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as error:
            fail(f"invalid TOML file {relative}: {error}", failures)


def validate_python(failures: list[str]) -> None:
    python_files = sorted((ROOT / ".claude" / "hooks").glob("*.py"))
    python_files.extend(sorted((ROOT / "scripts").glob("*.py")))
    for path in python_files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as error:
            fail(f"invalid Python file {path.relative_to(ROOT)}: {error}", failures)


def validate_frontmatter(directory: Path, failures: list[str]) -> None:
    for path in sorted(directory.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER_NAME.search(text)
        if match is None:
            fail(f"missing name frontmatter: {path.relative_to(ROOT)}", failures)
            continue
        name = match.group(1).strip()
        expected = path.parent.name if path.name == "SKILL.md" else path.stem
        if name != expected:
            fail(
                f"frontmatter name mismatch in {path.relative_to(ROOT)}: {name!r} != {expected!r}",
                failures,
            )


def validate_prose(failures: list[str]) -> None:
    excluded = {ROOT / "docs" / "superpowers" / "plans"}
    for path in sorted(ROOT.rglob("*.md")):
        if any(parent in path.parents for parent in excluded):
            continue
        text = path.read_text(encoding="utf-8")
        if "—" in text:
            fail(f"em dash in prose: {path.relative_to(ROOT)}", failures)
        if re.search(r"\b(?:TBD|FIXME)\b", text):
            fail(f"unresolved placeholder: {path.relative_to(ROOT)}", failures)


def validate_skill_link(failures: list[str]) -> None:
    link = ROOT / ".claude" / "skills"
    if not link.is_symlink():
        fail(".claude/skills must be a symlink", failures)
        return
    if link.resolve(strict=False) != (ROOT / ".agents" / "skills").resolve(strict=False):
        fail(".claude/skills points to the wrong directory", failures)


def main() -> int:
    failures: list[str] = []
    validate_required_files(failures)
    validate_json(failures)
    validate_toml(failures)
    validate_python(failures)
    validate_frontmatter(ROOT / ".claude" / "agents", failures)
    validate_frontmatter(ROOT / ".agents" / "skills", failures)
    validate_prose(failures)
    validate_skill_link(failures)
    if failures:
        for message in failures:
            print(f"FAIL: {message}")
        return 1
    print("PASS: project scaffold is structurally valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
