from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/check_evidence_governance.py"


def write_fixture(
    root: Path,
    *,
    capability_id: str = "gate0.contracts",
    risk_capability_id: str = "gate0.contracts",
    declared_network_modules: tuple[str, ...] = (),
) -> None:
    matrix_path = root / "docs/evidence/capability-matrix.json"
    matrix_path.parent.mkdir(parents=True)
    matrix_path.write_text(
        json.dumps({"capabilities": [{"id": capability_id}]}),
        encoding="utf-8",
    )
    risk_document = {
        "schema_version": "risk-register-v1",
        "risks": [{"id": "R1", "capability_ids": [risk_capability_id]}],
    }
    (root / "docs/evidence/RISK-REGISTER.md").write_text(
        "# Risks\n\n<!-- evidence-governance:risk-register -->\n"
        f"```json\n{json.dumps(risk_document)}\n```\n",
        encoding="utf-8",
    )
    flow_document = {
        "schema_version": "data-flow-inventory-v1",
        "direct_network_modules": [
            {"path": path, "flow_ids": ["N1"]} for path in declared_network_modules
        ],
        "durable_stores": [{"id": "S1", "path": "data/catalog.sqlite3"}],
    }
    (root / "docs/evidence/DATA-FLOWS.md").write_text(
        "# Data flows\n\n<!-- evidence-governance:data-flows -->\n"
        f"```json\n{json.dumps(flow_document)}\n```\n",
        encoding="utf-8",
    )


def run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_repository_evidence_governance_is_consistent() -> None:
    result = run_checker(ROOT)

    assert result.returncode == 0
    assert result.stdout == "PASS: evidence governance inventories are consistent\n"
    assert result.stderr == ""


def test_unknown_risk_capability_fails(tmp_path: Path) -> None:
    write_fixture(tmp_path, risk_capability_id="gate9.unknown")

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        "FAIL: risk R1 references unknown capability: gate9.unknown"
    ]


def test_undocumented_direct_network_module_fails(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    module = tmp_path / "src/paper_insights/provider.py"
    module.parent.mkdir(parents=True)
    module.write_text("import httpx\n", encoding="utf-8")

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        "FAIL: undocumented direct network module: src/paper_insights/provider.py"
    ]


def test_documented_network_module_passes_and_urllib_parse_is_local(tmp_path: Path) -> None:
    network_path = "src/paper_insights/provider.py"
    write_fixture(tmp_path, declared_network_modules=(network_path,))
    module = tmp_path / network_path
    module.parent.mkdir(parents=True)
    module.write_text("import httpx\nfrom urllib.parse import urlsplit\n", encoding="utf-8")

    result = run_checker(tmp_path)

    assert result.returncode == 0
    assert result.stdout == "PASS: evidence governance inventories are consistent\n"


def test_declared_network_module_must_exist(tmp_path: Path) -> None:
    write_fixture(tmp_path, declared_network_modules=("src/paper_insights/missing.py",))

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        "FAIL: declared direct network module does not exist: src/paper_insights/missing.py"
    ]
