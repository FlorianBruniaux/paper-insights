#!/usr/bin/env python3
"""Validate the repository capability and evidence matrix without dependencies."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "docs" / "evidence" / "capability-matrix.json"
TOP_LEVEL_KEYS = frozenset({"schema_version", "capabilities"})
CAPABILITY_KEYS = frozenset(
    {
        "id",
        "roadmap_gate",
        "mechanism_status",
        "deterministic_evidence",
        "behavioral_evidence",
        "human_evidence",
        "known_exclusions",
        "claim_ceiling",
        "next_evaluation",
    }
)
EVIDENCE_KEYS = frozenset({"status", "references"})
HUMAN_EVIDENCE_KEYS = frozenset({"status", "denominator", "references"})
DENOMINATOR_KEYS = frozenset({"observed", "total"})
GATES = frozenset({"gate0", "gate1", "gate2", "gate3", "gate4", "gate5", "release"})
MECHANISM_STATUSES = frozenset({"specified", "implemented", "operational"})
DETERMINISTIC_STATUSES = frozenset({"not_run", "passed", "failed", "blocked"})
OBSERVATIONAL_STATUSES = frozenset({"not_run", "measured", "mixed", "failed", "blocked"})
CAPABILITY_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


def _unknown_keys(value: dict[str, object], allowed: frozenset[str]) -> str:
    return ", ".join(sorted(set(value) - allowed))


def _non_empty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_references(
    capability_id: str,
    layer: str,
    status: object,
    references: object,
    root: Path,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(references, list) or any(not _non_empty_text(item) for item in references):
        return [f"{capability_id} {layer} references must be a string array"]
    if status != "not_run" and not references:
        failures.append(f"{capability_id} {layer} requires evidence references")
    root_resolved = root.resolve()
    for reference in references:
        if not isinstance(reference, str):
            continue
        relative = Path(reference)
        if relative.is_absolute() or ".." in relative.parts:
            failures.append(f"{capability_id} {layer} has invalid reference: {reference}")
            continue
        resolved = (root_resolved / relative).resolve()
        if not resolved.is_relative_to(root_resolved):
            failures.append(f"{capability_id} {layer} has invalid reference: {reference}")
        elif not resolved.exists():
            failures.append(f"{capability_id} {layer} reference does not exist: {reference}")
    return failures


def _validate_evidence_layer(
    capability_id: str,
    layer: str,
    value: object,
    allowed_statuses: frozenset[str],
    root: Path,
) -> tuple[list[str], str | None, tuple[int, int] | None]:
    if not isinstance(value, dict):
        return [f"{capability_id} {layer} must be an object"], None, None

    failures: list[str] = []
    allowed_keys = HUMAN_EVIDENCE_KEYS if layer == "human_evidence" else EVIDENCE_KEYS
    unknown = _unknown_keys(value, allowed_keys)
    if unknown:
        failures.append(f"{capability_id} {layer} has unknown keys: {unknown}")

    status = value.get("status")
    if status not in allowed_statuses:
        failures.append(f"{capability_id} {layer} has invalid status: {status}")
    failures.extend(
        _validate_references(capability_id, layer, status, value.get("references"), root)
    )

    denominator: tuple[int, int] | None = None
    if layer == "human_evidence":
        raw_denominator = value.get("denominator")
        if status == "not_run" and raw_denominator is not None:
            failures.append(f"{capability_id} human_evidence not_run forbids a denominator")
        elif status != "not_run" and not isinstance(raw_denominator, dict):
            failures.append(f"{capability_id} human_evidence requires a denominator")
        elif isinstance(raw_denominator, dict):
            denominator_unknown = _unknown_keys(raw_denominator, DENOMINATOR_KEYS)
            if denominator_unknown:
                failures.append(
                    f"{capability_id} human_evidence denominator has unknown keys: "
                    f"{denominator_unknown}"
                )
            observed = raw_denominator.get("observed")
            total = raw_denominator.get("total")
            integers = (
                isinstance(observed, int)
                and not isinstance(observed, bool)
                and isinstance(total, int)
                and not isinstance(total, bool)
            )
            if not integers or total <= 0 or observed < 0 or observed > total:
                failures.append(
                    f"{capability_id} human_evidence denominator requires 0 <= observed <= total"
                )
            else:
                denominator = (observed, total)

    return failures, status if isinstance(status, str) else None, denominator


def validate_matrix(document: object, root: Path) -> tuple[str, ...]:
    """Return stable validation failures for one parsed capability matrix."""
    if not isinstance(document, dict):
        return ("capability matrix must be an object",)

    failures: list[str] = []
    unknown = _unknown_keys(document, TOP_LEVEL_KEYS)
    if unknown:
        failures.append(f"capability matrix has unknown keys: {unknown}")
    if document.get("schema_version") != "capability-matrix-v1":
        failures.append("capability matrix has an invalid schema_version")

    capabilities = document.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        failures.append("capabilities must be a non-empty array")
        return tuple(failures)

    ids = [row.get("id") if isinstance(row, dict) else None for row in capabilities]
    if any(not isinstance(item, str) for item in ids) or ids != sorted(set(ids)):
        failures.append("capability ids must be unique and sorted")

    for index, row in enumerate(capabilities):
        if not isinstance(row, dict):
            failures.append(f"capability row {index} must be an object")
            continue
        raw_id = row.get("id")
        capability_id = raw_id if isinstance(raw_id, str) else f"capability row {index}"
        if not isinstance(raw_id, str) or CAPABILITY_ID.fullmatch(raw_id) is None:
            failures.append(f"{capability_id} has an invalid id")

        unknown = _unknown_keys(row, CAPABILITY_KEYS)
        if unknown:
            failures.append(f"{capability_id} has unknown keys: {unknown}")
        missing = sorted(CAPABILITY_KEYS - set(row))
        if missing:
            failures.append(f"{capability_id} is missing keys: {', '.join(missing)}")

        gate = row.get("roadmap_gate")
        if gate not in GATES:
            failures.append(f"{capability_id} has invalid roadmap_gate: {gate}")
        mechanism_status = row.get("mechanism_status")
        if mechanism_status not in MECHANISM_STATUSES:
            failures.append(f"{capability_id} has invalid mechanism_status: {mechanism_status}")

        deterministic_failures, deterministic_status, _ = _validate_evidence_layer(
            capability_id,
            "deterministic_evidence",
            row.get("deterministic_evidence"),
            DETERMINISTIC_STATUSES,
            root,
        )
        behavioral_failures, behavioral_status, _ = _validate_evidence_layer(
            capability_id,
            "behavioral_evidence",
            row.get("behavioral_evidence"),
            OBSERVATIONAL_STATUSES,
            root,
        )
        human_failures, human_status, human_denominator = _validate_evidence_layer(
            capability_id,
            "human_evidence",
            row.get("human_evidence"),
            OBSERVATIONAL_STATUSES,
            root,
        )
        failures.extend(deterministic_failures)
        failures.extend(behavioral_failures)
        failures.extend(human_failures)

        exclusions = row.get("known_exclusions")
        if (
            not isinstance(exclusions, list)
            or not exclusions
            or any(not _non_empty_text(item) for item in exclusions)
        ):
            failures.append(f"{capability_id} known_exclusions must be non-empty strings")
        if not _non_empty_text(row.get("claim_ceiling")):
            failures.append(f"{capability_id} claim_ceiling is required")
        if not _non_empty_text(row.get("next_evaluation")):
            failures.append(f"{capability_id} next_evaluation is required")

        if mechanism_status in {"implemented", "operational"} and deterministic_status != "passed":
            failures.append(
                f"{capability_id} {mechanism_status} status requires passed deterministic evidence"
            )
        if mechanism_status == "operational":
            if behavioral_status != "measured":
                failures.append(
                    f"{capability_id} operational status requires measured behavioral evidence"
                )
            if (
                human_status != "measured"
                or human_denominator is None
                or human_denominator[0] != human_denominator[1]
            ):
                failures.append(
                    f"{capability_id} operational status requires complete human evidence"
                )

    return tuple(failures)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--root", type=Path, default=ROOT)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        document = json.loads(args.matrix.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read capability matrix: {error}")
        return 1
    failures = validate_matrix(document, args.root)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("PASS: capability matrix is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
