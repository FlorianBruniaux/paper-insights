from __future__ import annotations

import ast
from pathlib import Path

import pytest


FORBIDDEN = {
    "domain": (
        "paper_insights.application",
        "paper_insights.adapters",
        "paper_insights.interfaces",
        "sqlalchemy",
        "alembic",
        "httpx",
        "pydantic",
        "typer",
        "mcp",
    ),
    "application": (
        "paper_insights.adapters",
        "paper_insights.interfaces",
        "paper_insights.bootstrap",
    ),
}
CLIENT_FACTORIES = {"Client", "AsyncClient", "create_engine", "FastMCP"}


def architecture_violations(root: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        layer = relative.parts[0] if relative.parts else ""
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                imported = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = (node.module,)
            for name in imported:
                forbidden = FORBIDDEN.get(layer, ())
                if any(
                    name == prefix or name.startswith(f"{prefix}.")
                    for prefix in forbidden
                ):
                    violations.append(f"{relative}: forbidden import {name}")
        for statement in tree.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for node in ast.walk(statement):
                if not isinstance(node, ast.Call):
                    continue
                called = node.func
                if isinstance(called, ast.Name):
                    name = called.id
                elif isinstance(called, ast.Attribute):
                    name = called.attr
                else:
                    name = ""
                if name in CLIENT_FACTORIES:
                    violations.append(f"{relative}: client construction at import: {name}")
    return violations


def test_real_source_tree_respects_import_boundaries() -> None:
    root = Path(__file__).parents[2] / "src" / "paper_insights"
    assert architecture_violations(root) == []


@pytest.mark.parametrize(
    ("relative", "source", "expected"),
    [
        ("domain/bad.py", "import sqlalchemy\n", "forbidden import sqlalchemy"),
        (
            "domain/bad.py",
            "from paper_insights.application import ports\n",
            "forbidden import paper_insights.application",
        ),
        (
            "application/bad.py",
            "from paper_insights.adapters import catalog\n",
            "forbidden import paper_insights.adapters",
        ),
        ("application/bad.py", "Client()\n", "client construction at import: Client"),
        ("application/bad.py", "client = Client()\n", "client construction at import: Client"),
    ],
)
def test_checker_rejects_hostile_fixture(
    tmp_path: Path, relative: str, source: str, expected: str
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")

    assert any(expected in item for item in architecture_violations(tmp_path))
