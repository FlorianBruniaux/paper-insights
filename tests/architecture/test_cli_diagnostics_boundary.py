from __future__ import annotations

import ast
from pathlib import Path


def test_cli_diagnostics_do_not_import_infrastructure() -> None:
    cli_root = Path(__file__).parents[2] / "src" / "paper_insights" / "interfaces" / "cli"
    forbidden: list[str] = []
    for path in sorted(cli_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = (node.module,)
            else:
                continue
            for name in names:
                if name == "sqlite3" or name.startswith("paper_insights.adapters"):
                    forbidden.append(f"{path.name}: {name}")

    assert forbidden == []
