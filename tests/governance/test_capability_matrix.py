from __future__ import annotations

import json
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/check_capability_matrix.py"


def valid_matrix() -> dict[str, object]:
    return {
        "schema_version": "capability-matrix-v1",
        "capabilities": [
            {
                "id": "gate0.contracts",
                "roadmap_gate": "gate0",
                "mechanism_status": "operational",
                "deterministic_evidence": {
                    "status": "passed",
                    "references": ["evidence.txt"],
                },
                "behavioral_evidence": {
                    "status": "measured",
                    "references": ["evidence.txt"],
                },
                "human_evidence": {
                    "status": "measured",
                    "denominator": {"observed": 1, "total": 1},
                    "references": ["evidence.txt"],
                },
                "known_exclusions": ["No claim beyond the recorded fixture."],
                "claim_ceiling": "The recorded fixture passed all three evidence layers.",
                "next_evaluation": "Repeat against the next repository revision.",
            }
        ],
    }


def run_checker(root: Path, document: dict[str, object]) -> subprocess.CompletedProcess[str]:
    matrix_path = root / "matrix.json"
    matrix_path.write_text(json.dumps(document), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--matrix",
            str(matrix_path),
            "--root",
            str(root),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_repository_capability_matrix_is_valid() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout == "PASS: capability matrix is valid\n"
    assert result.stderr == ""


def test_duplicate_or_unordered_capability_ids_fail(tmp_path: Path) -> None:
    (tmp_path / "evidence.txt").write_text("evidence", encoding="utf-8")
    document = valid_matrix()
    capabilities = document["capabilities"]
    assert isinstance(capabilities, list)
    capabilities.append(deepcopy(capabilities[0]))

    result = run_checker(tmp_path, document)

    assert result.returncode == 1
    assert result.stdout.splitlines() == ["FAIL: capability ids must be unique and sorted"]


def test_positive_evidence_requires_an_existing_repository_reference(
    tmp_path: Path,
) -> None:
    document = valid_matrix()

    result = run_checker(tmp_path, document)

    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        "FAIL: gate0.contracts deterministic_evidence reference does not exist: evidence.txt",
        "FAIL: gate0.contracts behavioral_evidence reference does not exist: evidence.txt",
        "FAIL: gate0.contracts human_evidence reference does not exist: evidence.txt",
    ]


def test_human_denominator_must_be_closed(tmp_path: Path) -> None:
    (tmp_path / "evidence.txt").write_text("evidence", encoding="utf-8")
    document = valid_matrix()
    capability = document["capabilities"]
    assert isinstance(capability, list)
    human = capability[0]["human_evidence"]
    assert isinstance(human, dict)
    human["denominator"] = {"observed": 2, "total": 1}

    result = run_checker(tmp_path, document)

    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        "FAIL: gate0.contracts human_evidence denominator requires 0 <= observed <= total",
        "FAIL: gate0.contracts operational status requires complete human evidence",
    ]


def test_operational_status_requires_all_evidence_layers(tmp_path: Path) -> None:
    (tmp_path / "evidence.txt").write_text("evidence", encoding="utf-8")
    document = valid_matrix()
    capability = document["capabilities"]
    assert isinstance(capability, list)
    behavioral = capability[0]["behavioral_evidence"]
    assert isinstance(behavioral, dict)
    behavioral["status"] = "not_run"
    behavioral["references"] = []

    result = run_checker(tmp_path, document)

    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        "FAIL: gate0.contracts operational status requires measured behavioral evidence"
    ]


def test_unknown_row_key_and_status_fail(tmp_path: Path) -> None:
    (tmp_path / "evidence.txt").write_text("evidence", encoding="utf-8")
    document = valid_matrix()
    capability = document["capabilities"]
    assert isinstance(capability, list)
    capability[0]["surprise"] = True
    deterministic = capability[0]["deterministic_evidence"]
    assert isinstance(deterministic, dict)
    deterministic["status"] = "green"

    result = run_checker(tmp_path, document)

    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        "FAIL: gate0.contracts has unknown keys: surprise",
        "FAIL: gate0.contracts deterministic_evidence has invalid status: green",
        "FAIL: gate0.contracts operational status requires passed deterministic evidence",
    ]


def test_cli_reports_repository_matrix_status() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout == "PASS: capability matrix is valid\n"
    assert result.stderr == ""


def test_project_validator_surfaces_capability_matrix_failures(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(ROOT / "scripts/validate_project.py", scripts / "validate_project.py")
    shutil.copy2(CHECKER, scripts / "check_capability_matrix.py")
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("evidence", encoding="utf-8")
    document = valid_matrix()
    capabilities = document["capabilities"]
    assert isinstance(capabilities, list)
    deterministic = capabilities[0]["deterministic_evidence"]
    assert isinstance(deterministic, dict)
    deterministic["status"] = "green"
    matrix_path = tmp_path / "docs/evidence/capability-matrix.json"
    matrix_path.parent.mkdir(parents=True)
    matrix_path.write_text(json.dumps(document), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(scripts / "validate_project.py")],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert (
        "FAIL: capability matrix: gate0.contracts deterministic_evidence has invalid status: green"
    ) in result.stdout
