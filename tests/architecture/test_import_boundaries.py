from __future__ import annotations

import ast
from pathlib import Path

import pytest

INFRASTRUCTURE_IMPORTS = (
    "sqlalchemy",
    "alembic",
    "httpx",
    "typer",
    "mcp",
)
FORBIDDEN = {
    "domain": (
        "paper_insights.application",
        "paper_insights.adapters",
        "paper_insights.interfaces",
        "pydantic",
        *INFRASTRUCTURE_IMPORTS,
    ),
    "application": (
        "paper_insights.adapters",
        "paper_insights.interfaces",
        "paper_insights.bootstrap",
        "pydantic",
        *INFRASTRUCTURE_IMPORTS,
    ),
}
CLIENT_FACTORIES = {"Client", "AsyncClient", "create_engine", "FastMCP"}


def _resolved_import(node: ast.ImportFrom, relative: Path) -> str | None:
    if node.level == 0:
        return node.module
    package = ["paper_insights", *relative.parent.parts]
    keep = len(package) - (node.level - 1)
    module = node.module.split(".") if node.module else []
    return ".".join([*package[:keep], *module])


class _ExecutedCallVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append(node)
        self.generic_visit(node)

    def _visit_function_header(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
    ) -> None:
        if not isinstance(node, ast.Lambda):
            for decorator in node.decorator_list:
                self.visit(decorator)
        for default in node.args.defaults:
            self.visit(default)
        for default in node.args.kw_defaults:
            if default is not None:
                self.visit(default)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function_header(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function_header(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_function_header(node)


def _import_time_calls(statements: list[ast.stmt]) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for statement in statements:
        visitor = _ExecutedCallVisitor()
        visitor.visit(statement)
        calls.extend(visitor.calls)
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
            elif isinstance(node, ast.ImportFrom):
                resolved = _resolved_import(node, relative)
                if node.module:
                    imported = tuple(
                        name
                        for name in (
                            resolved,
                            *(f"{resolved}.{alias.name}" for alias in node.names if resolved),
                        )
                        if name
                    )
                elif resolved:
                    imported = tuple(f"{resolved}.{alias.name}" for alias in node.names)
            for name in imported:
                if relative == Path("application/analysis/schemas.py") and (
                    name == "pydantic" or name.startswith("pydantic.")
                ):
                    continue
                forbidden = FORBIDDEN.get(layer, ())
                if any(name == prefix or name.startswith(f"{prefix}.") for prefix in forbidden):
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
        (
            "application/bad.py",
            "from .. import adapters\n",
            "forbidden import paper_insights.adapters",
        ),
        (
            "application/bad.py",
            "from paper_insights import adapters\n",
            "forbidden import paper_insights.adapters",
        ),
        (
            "domain/bad.py",
            "from paper_insights import application\n",
            "forbidden import paper_insights.application",
        ),
        ("application/bad.py", "import sqlalchemy\n", "forbidden import sqlalchemy"),
        ("application/bad.py", "import httpx\n", "forbidden import httpx"),
        ("application/bad.py", "import pydantic\n", "forbidden import pydantic"),
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


def test_checker_does_not_execute_lambda_bodies_in_its_model(tmp_path: Path) -> None:
    path = tmp_path / "application" / "allowed.py"
    path.parent.mkdir(parents=True)
    path.write_text("factory = lambda: Client()\n", encoding="utf-8")

    assert architecture_violations(tmp_path) == []


def test_checker_reserves_pydantic_for_future_llm_boundary_schema(
    tmp_path: Path,
) -> None:
    path = tmp_path / "application" / "analysis" / "schemas.py"
    path.parent.mkdir(parents=True)
    path.write_text("from pydantic import BaseModel\n", encoding="utf-8")

    assert architecture_violations(tmp_path) == []
