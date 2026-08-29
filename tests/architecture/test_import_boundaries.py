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


def _resolved_import(node: ast.ImportFrom, relative: Path) -> str | None:
    if not node.module:
        return None
    if node.level == 0:
        return node.module
    package = ["paper_insights", *relative.parent.parts]
    keep = len(package) - (node.level - 1)
    return ".".join([*package[:keep], *node.module.split(".")])


def _import_time_calls(statements: list[ast.stmt]) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for statement in statements:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            expressions = [
                *statement.decorator_list,
                *statement.args.defaults,
                *(value for value in statement.args.kw_defaults if value is not None),
            ]
            for expression in expressions:
                calls.extend(node for node in ast.walk(expression) if isinstance(node, ast.Call))
            continue
        if isinstance(statement, ast.ClassDef):
            expressions = [*statement.decorator_list, *statement.bases]
            expressions.extend(keyword.value for keyword in statement.keywords)
            for expression in expressions:
                calls.extend(node for node in ast.walk(expression) if isinstance(node, ast.Call))
            calls.extend(_import_time_calls(statement.body))
            continue
        calls.extend(node for node in ast.walk(statement) if isinstance(node, ast.Call))
    return calls


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
                resolved = _resolved_import(node, relative)
                imported = (resolved,) if resolved else ()
            for name in imported:
                forbidden = FORBIDDEN.get(layer, ())
                if any(
                    name == prefix or name.startswith(f"{prefix}.")
                    for prefix in forbidden
                ):
                    violations.append(f"{relative}: forbidden import {name}")
        for node in _import_time_calls(tree.body):
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
        (
            "application/bad.py",
            "from ..adapters import catalog\n",
            "forbidden import paper_insights.adapters",
        ),
        ("application/bad.py", "Client()\n", "client construction at import: Client"),
        ("application/bad.py", "client = Client()\n", "client construction at import: Client"),
        (
            "application/bad.py",
            "def build(client=Client()):\n    return client\n",
            "client construction at import: Client",
        ),
        (
            "application/bad.py",
            "class Holder:\n    client = Client()\n",
            "client construction at import: Client",
        ),
    ],
)
def test_checker_rejects_hostile_fixture(
    tmp_path: Path, relative: str, source: str, expected: str
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")

    assert any(expected in item for item in architecture_violations(tmp_path))
