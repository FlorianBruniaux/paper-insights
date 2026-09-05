#!/usr/bin/env python3
"""Check risk references and direct network-flow inventory without dependencies."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RISK_MARKER = "evidence-governance:risk-register"
FLOW_MARKER = "evidence-governance:data-flows"
DIRECT_NETWORK_ROOTS = frozenset({"aiohttp", "httpx", "requests", "socket"})


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_markdown_json(path: Path, marker: str) -> object:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"<!--\s*{re.escape(marker)}\s*-->\s*```json\s*(.*?)\s*```",
        re.DOTALL,
    )
    match = pattern.search(text)
    if match is None:
        raise ValueError(f"missing machine-readable block: {marker}")
    return json.loads(match.group(1))


def _capability_ids(document: object) -> set[str]:
    if not isinstance(document, dict):
        raise ValueError("capability matrix must be an object")
    capabilities = document.get("capabilities")
    if not isinstance(capabilities, list):
        raise ValueError("capability matrix requires capabilities")
    ids = {
        row.get("id")
        for row in capabilities
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    if len(ids) != len(capabilities):
        raise ValueError("capability matrix has invalid or duplicate ids")
    return ids


def _risk_failures(document: object, capability_ids: set[str]) -> list[str]:
    if not isinstance(document, dict) or document.get("schema_version") != "risk-register-v1":
        return ["risk register has an invalid schema_version"]
    risks = document.get("risks")
    if not isinstance(risks, list) or not risks:
        return ["risk register requires risks"]
    failures: list[str] = []
    seen: set[str] = set()
    for index, risk in enumerate(risks):
        if not isinstance(risk, dict):
            failures.append(f"risk row {index} must be an object")
            continue
        risk_id = risk.get("id")
        if not isinstance(risk_id, str) or not risk_id:
            failures.append(f"risk row {index} requires an id")
            continue
        if risk_id in seen:
            failures.append(f"duplicate risk id: {risk_id}")
        seen.add(risk_id)
        references = risk.get("capability_ids")
        if not isinstance(references, list) or not references:
            failures.append(f"risk {risk_id} requires capability_ids")
            continue
        for capability_id in references:
            if capability_id not in capability_ids:
                failures.append(f"risk {risk_id} references unknown capability: {capability_id}")
    return failures


def _imports_network(module: Path) -> bool:
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in DIRECT_NETWORK_ROOTS:
                    return True
                if alias.name == "urllib.request" or alias.name.startswith("urllib.request."):
                    return True
        elif isinstance(node, ast.ImportFrom):
            imported_from = node.module or ""
            if imported_from.split(".", 1)[0] in DIRECT_NETWORK_ROOTS:
                return True
            if imported_from == "urllib.request" or imported_from.startswith("urllib.request."):
                return True
            if imported_from == "urllib" and any(alias.name == "request" for alias in node.names):
                return True
    return False


def _detected_network_modules(root: Path) -> set[str]:
    source_root = root / "src" / "paper_insights"
    if not source_root.is_dir():
        return set()
    return {
        path.relative_to(root).as_posix()
        for path in sorted(source_root.rglob("*.py"))
        if _imports_network(path)
    }


def _flow_failures(document: object, root: Path) -> list[str]:
    if not isinstance(document, dict) or document.get("schema_version") != "data-flow-inventory-v1":
        return ["data-flow inventory has an invalid schema_version"]
    modules = document.get("direct_network_modules")
    stores = document.get("durable_stores")
    if not isinstance(modules, list):
        return ["data-flow inventory requires direct_network_modules"]
    if not isinstance(stores, list) or not stores:
        return ["data-flow inventory requires durable_stores"]

    failures: list[str] = []
    declared: set[str] = set()
    missing: set[str] = set()
    for row in modules:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            failures.append("direct network module requires a path")
            continue
        path = row["path"]
        flow_ids = row.get("flow_ids")
        if (
            not isinstance(flow_ids, list)
            or not flow_ids
            or any(not isinstance(flow_id, str) or not flow_id for flow_id in flow_ids)
        ):
            failures.append(f"direct network module requires flow_ids: {path}")
        if path in declared:
            failures.append(f"duplicate direct network module: {path}")
        declared.add(path)
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts:
            failures.append(f"invalid direct network module path: {path}")
            missing.add(path)
        elif not (root / relative).is_file():
            failures.append(f"declared direct network module does not exist: {path}")
            missing.add(path)

    detected = _detected_network_modules(root)
    for path in sorted(detected - declared):
        failures.append(f"undocumented direct network module: {path}")
    for path in sorted(declared - detected - missing):
        failures.append(f"declared module has no direct network import: {path}")
    return failures


def validate_evidence_governance(root: Path) -> tuple[str, ...]:
    """Return stable failures for the repository evidence-governance artifacts."""
    try:
        matrix = _load_json(root / "docs/evidence/capability-matrix.json")
        risks = _load_markdown_json(root / "docs/evidence/RISK-REGISTER.md", RISK_MARKER)
        flows = _load_markdown_json(root / "docs/evidence/DATA-FLOWS.md", FLOW_MARKER)
        capabilities = _capability_ids(matrix)
    except (OSError, ValueError, json.JSONDecodeError, SyntaxError) as error:
        return (f"cannot load evidence governance artifacts: {error}",)
    failures = _risk_failures(risks, capabilities)
    failures.extend(_flow_failures(flows, root))
    return tuple(failures)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    return parser.parse_args()


def main() -> int:
    failures = validate_evidence_governance(_parse_args().root.resolve())
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: evidence governance inventories are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
