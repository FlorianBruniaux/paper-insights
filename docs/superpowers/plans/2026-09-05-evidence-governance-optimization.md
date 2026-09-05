# Evidence Governance Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add evidence governance to the existing Paper Insights program, close the documentation drift, and strengthen later analysis and bibliographic gates without bypassing the blocked Gate 2 human review.

**Architecture:** Repository governance stays outside the runtime domain. A standard-library validator owns a canonical JSON capability matrix; the existing roadmap and complete program consume its statuses. Runtime changes remain in their existing work packages and start only after their gates open.

**Tech Stack:** Python 3.12+, JSON, pytest, Ruff, mypy, Markdown, existing SQLite and Alembic program.

**Spec:** `docs/superpowers/specs/2026-09-05-evidence-governance-design.md`

## Global Constraints

- The authoritative product sequence remains `docs/superpowers/plans/2026-08-28-complete-program-execution.md`.
- Gate 2 is blocked until 30 human relevance reviews meet the roadmap threshold and the three product decisions are recorded.
- Academic Research Skills is CC BY-NC 4.0; reimplement concepts without copying its prompts, schemas or code.
- Every metadata or analysis claim keeps source, retrieval context and immutable evidence.
- Tests use local fixtures and no network.
- Update `CHANGELOG.md` under `[Unreleased]` for every behavior or contract change.
- Use explicit Git pathspecs. Do not push.

---

## Plan Critique: Complete Program Before Optimization

### Readiness

**Score:** 82%, almost ready. Gate 0 through the automated Gate 2 harness are implemented and the baseline is green. The plan cannot open Wave 3 because the human relevance gate is 0 of 30 and the evidence state is not centralized.

### Blockers

1. **Gate 2 product authority is incomplete:** representative-query criteria, P0 relevance definition and reference corpus are not selected.
   - Fix: Task 4 creates a hash-bound decision packet, then a human completes the 30 reviews.
2. **Evidence states are scattered:** tests, changelog and prose can be read as equivalent proof.
   - Fix: Tasks 1 and 2 create a machine-readable matrix and make project validation consume it.

### Major concerns

1. **README state drift:** the integration branch exposes Gate 2 CLI behavior while README still says ingestion and search are absent.
   - Fix: Task 2 reports branch capabilities and blocked gates without claiming release readiness.
2. **Analysis proof is underspecified at run level:** WP-40 has a strong cache key but no single immutable receipt binding catalogue revision and version observation.
   - Fix: Task 5 adds the receipt contract before the analysis migration.
3. **Risk and network evidence have no authority:** no document ties known failures and transmissions to capability status.
   - Fix: Task 3 adds checked inventories.

### Scope deferred

- Multi-model review, authoring workflows and alternative ranking.
- Screening accounting until a selection workflow exists.
- Bibliographic retraction checks until their owning provider wave is open.

## Delivery Units

| Unit | Delivers | Blocked by | Validation |
| --- | --- | --- | --- |
| U01 | Canonical capability matrix and fail-closed validator | None | Targeted RED/GREEN tests and repository matrix check pass |
| U02 | Accurate README, roadmap cross-links and scaffold validation | U01 | `validate_project.py` fails without/with an invalid matrix and passes on repository state |
| U03 | Risk register and data-flow inventory | U01 | Every risk capability ID resolves and documented direct network modules equal detected modules |
| U04 | Gate 2 decision packet and human review | U02 | Validator returns `SATISFIED`, at least 24/30 top-five matches, zero P0 |
| U05 | Existing WP-30 to WP-32 | U04 | Gate 3 acceptance in the complete program passes |
| U06 | Analysis receipt and claim evidence refinement | U05, WP-39 | WP-40 automated and 20-item human gates pass |
| U07 | Bibliographic observations and screening accounting | U06 | Unknown/degraded never renders clean; screening denominators close exactly |
| U08 | Existing WP-50 to WP-52 and release gate | U07 | No P0, no unmitigated P1, no incomplete human benchmark, no required `UNKNOWN` |

**Frontier at plan start:** U01.

---

### Task 1: Capability Matrix and Validator

**Files:**

- Create: `docs/evidence/capability-matrix.json`
- Create: `scripts/check_capability_matrix.py`
- Create: `tests/governance/test_capability_matrix.py`

**Interfaces:**

- Produces: `validate_matrix(document: object, root: Path) -> tuple[str, ...]`
- Produces: CLI exit `0` with `PASS:` for a valid matrix and exit `1` with one `FAIL:` line per violation.
- Consumes: repository-relative evidence references and the contract in the design spec.

- [ ] **Step 1: Write failing behavior tests**

Cover the checked-in matrix, duplicated IDs, invalid evidence vocabulary, missing evidence references, invalid human denominators and an unjustified `operational` status. Each fixture is a literal dict and invokes the real validator.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest --disable-socket tests/governance/test_capability_matrix.py -v`

Expected: FAIL during import because `scripts.check_capability_matrix` does not exist.

- [ ] **Step 3: Implement the standard-library validator**

Reject unknown keys and invalid statuses. Resolve evidence paths under the repository root, reject escapes, require existing references for positive evidence, enforce ordered unique IDs and validate denominators.

- [ ] **Step 4: Add the initial six gate rows**

Record Gate 0, Gate 1, Gate 2, Gate 3, Gate 4 and release. Gate 2 human evidence is `blocked` with `observed: 0`, `total: 30`. Later gates remain `specified` and `not_run`.

- [ ] **Step 5: Verify GREEN**

Run: `uv run pytest --disable-socket tests/governance/test_capability_matrix.py -v`

Expected: all targeted tests pass.

Run: `python3 scripts/check_capability_matrix.py`

Expected: `PASS: capability matrix is valid`.

- [ ] **Step 6: Commit**

```bash
git add docs/evidence/capability-matrix.json scripts/check_capability_matrix.py tests/governance/test_capability_matrix.py
git commit -m "feat: add capability evidence matrix"
```

### Task 2: Authority Wiring and Status Correction

**Files:**

- Modify: `scripts/validate_project.py`
- Modify: `README.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/superpowers/plans/2026-08-28-complete-program-execution.md`
- Modify: `CHANGELOG.md`
- Test: `tests/governance/test_capability_matrix.py`

**Interfaces:**

- Consumes: `validate_matrix` from Task 1.
- Produces: dependency-free project validation that fails closed on an absent or invalid matrix.

- [ ] **Step 1: Add a failing integration test**

Run the real project validator against a temporary repository copy with an invalid capability status. Assert exit `1` and a bounded `FAIL:` message.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest --disable-socket tests/governance/test_capability_matrix.py -v`

Expected: the new integration test fails because `validate_project.py` ignores the matrix.

- [ ] **Step 3: Wire validation and correct documentation**

Require the design, optimization plan and matrix. Invoke its validator from `validate_project.py`. Update README to distinguish the implemented integration-branch surface from unopened gates. Add the governance overlay and Gate 2 blocker to the roadmap and complete plan. Record the changes under `[Unreleased]`.

- [ ] **Step 4: Verify GREEN**

Run: `python3 scripts/validate_project.py`

Expected: `PASS: project scaffold is structurally valid`.

Run: `uv run pytest --disable-socket tests/governance -v`

Expected: all governance tests pass.

- [ ] **Step 5: Commit**

```bash
git add README.md CHANGELOG.md docs/ROADMAP.md docs/superpowers/plans/2026-08-28-complete-program-execution.md scripts/validate_project.py tests/governance/test_capability_matrix.py
git commit -m "docs: align roadmap with evidence gates"
```

### Task 3: Risk Register and Data-Flow Inventory

**Files:**

- Create: `docs/evidence/RISK-REGISTER.md`
- Create: `docs/evidence/DATA-FLOWS.md`
- Create: `scripts/check_evidence_governance.py`
- Create: `tests/governance/test_evidence_governance.py`
- Modify: `CHANGELOG.md`

**Interfaces:**

- Consumes: capability IDs from `docs/evidence/capability-matrix.json`.
- Produces: `check_evidence_governance.py` exit `0` only when every risk capability resolves and each directly networked Python module is inventoried.

- [ ] **Step 1: Write failing tests**

Use temporary files to prove an unknown capability ID and an undocumented direct `httpx` import both fail. Prove documented modules and valid capability IDs pass.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest --disable-socket tests/governance/test_evidence_governance.py -v`

Expected: FAIL during import because the checker does not exist.

- [ ] **Step 3: Implement the minimum checker and inventories**

Parse fenced machine-readable rows embedded in both Markdown files. Detect direct imports of `httpx`, `urllib.request`, `requests`, `socket` and `aiohttp` under `src/paper_insights`; `urllib.parse` is not a network path. Compare the resulting paths with declared direct network modules. Validate every risk capability against the matrix.

- [ ] **Step 4: Verify GREEN**

Run: `python3 scripts/check_evidence_governance.py`

Expected: `PASS: evidence governance inventories are consistent`.

Run: `uv run pytest --disable-socket tests/governance -v`

Expected: all governance tests pass.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md docs/evidence/RISK-REGISTER.md docs/evidence/DATA-FLOWS.md scripts/check_evidence_governance.py tests/governance/test_evidence_governance.py
git commit -m "docs: inventory evidence risks and data flows"
```

### Task 4: Gate 2 Product Decision and Human Review

**Files:**

- Create: `docs/benchmarks/SEARCH-RELEVANCE-DECISION.md`
- Runtime artifacts under ignored `output/search-relevance/<candidate>/`
- Human-approved replacement: `tests/benchmarks/search_queries.jsonl`
- Modify after approval: `docs/evidence/capability-matrix.json`
- Modify after approval: `CHANGELOG.md`

**Interfaces:**

- Consumes: the existing `paper-insights-search-relevance` CLI and hash-bound manifests.
- Produces: one named reference corpus, 30 reviewed records and a capability row whose human evidence is no longer blocked.

- [ ] **Step 1: Record the three product decisions**

Define query distribution, P0 classification and the exact catalogue/index candidate. Do not infer these decisions from fixtures.

- [ ] **Step 2: Inventory and prepare the candidate**

Run the exact `inventory` and `run` commands from `docs/benchmarks/SEARCH-RELEVANCE-GATE.md` against absolute paths under one new output directory.

- [ ] **Step 3: Complete the human review**

A human fills all 30 `p0_relevance_failure`, `reviewer_id` and `reviewed_at` fields without modifying query or result fields.

- [ ] **Step 4: Validate and integrate**

Run `paper-insights-search-relevance validate-review`. Require `SATISFIED`, at least 24 top-five matches and zero P0. Replace the tracked benchmark only after explicit human approval.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md docs/benchmarks/SEARCH-RELEVANCE-DECISION.md docs/evidence/capability-matrix.json tests/benchmarks/search_queries.jsonl
git commit -m "test: close human search relevance gate"
```

### Task 5: Strengthen the Wave 4 Analysis Contract

**Files:**

- Modify: `docs/specs/ANALYSIS.md`
- Modify: `docs/specs/DATA-MODEL.md`
- Modify: `docs/superpowers/plans/2026-08-28-complete-program-execution.md`
- Modify: `src/paper_insights/domain/analysis.py` during WP-40
- Create during WP-39: `alembic/versions/0003_analysis.py`
- Create during WP-40: `tests/analysis/test_analysis_receipt.py`
- Extend during WP-40: `tests/analysis/test_claim_evidence.py`
- Extend during WP-40: `tests/analysis/test_prompt_injection_boundary.py`

**Interfaces:**

- Produces: immutable `AnalysisReceipt` bound to the catalogue revision, exact observation, artifacts, prompt, passages, model, parameters, result schema, stop reason and stochasticity declaration.
- Produces: evidence availability and support verdict as separate closed enums.

- [ ] **Step 1: Freeze the receipt and evidence vocabularies in specs before migration code**
- [ ] **Step 2: Add RED migration and domain tests during WP-39/WP-40**
- [ ] **Step 3: Implement the additive migration and minimum domain types**
- [ ] **Step 4: Add the runtime instruction/data test before backend code**
- [ ] **Step 5: Execute the existing WP-40 automated and human gates**

Validation: all commands and thresholds in WP-40 remain authoritative, plus every receipt field changes the cache identity or audit record as specified.

### Task 6: Add Bibliographic Observations and Screening Only at Their Owner Boundaries

**Files:**

- Modify before WP-41: `docs/specs/DATA-MODEL.md`
- Modify before WP-41: `docs/specs/AUTHOR-IDENTITY.md`
- Modify: `docs/superpowers/plans/2026-08-28-complete-program-execution.md`
- Create with provider implementation: `tests/bibliography/test_observation_status.py`
- Create with selection workflow: `tests/research/test_screening_accounting.py`

**Interfaces:**

- Produces: immutable bibliographic check observations with separate check status, finding, source and staleness.
- Produces: screening run accounting satisfying `scanned = included + excluded + skipped`.

- [ ] **Step 1: Freeze closed observation states before provider implementation**
- [ ] **Step 2: Write RED tests proving unknown/degraded/stale never render clean**
- [ ] **Step 3: Implement observations in the owning provider and catalogue package**
- [ ] **Step 4: Add screening only when a collection or analysis selection service exists**
- [ ] **Step 5: Write RED tests for equal criteria and exact denominators before screening code**

Validation: citation existence is never presented as claim support, and no screened record disappears without a disposition.

### Task 7: Resume the Existing Program and Release Audit

**Files and commands:** Use WP-30 through WP-52 exactly as defined in `docs/superpowers/plans/2026-08-28-complete-program-execution.md`, including their file ownership and verification commands.

- [ ] **Step 1: Open Wave 3 only after Task 4 passes**
- [ ] **Step 2: Run Gate 3 and land its integration commit**
- [ ] **Step 3: Complete WP-39 before parallel Wave 4 work**
- [ ] **Step 4: Apply Tasks 5 and 6 inside their owning work packages**
- [ ] **Step 5: Run WP-50 through WP-52 and update every matrix row from fresh evidence**
- [ ] **Step 6: Keep release closed for any P0, unmitigated P1, incomplete human gate or required `UNKNOWN`**

Rollback: Tasks 1 through 3 are additive repository governance. Reverting their scoped commits removes them without changing corpus data. Runtime migrations in later tasks follow the existing additive Alembic and release recovery rules.

## Plan Self-Review

- Spec coverage: all design sections map to Tasks 1 through 7.
- Placeholder scan: no unresolved placeholder, unspecified handler or open interface remains in U01 through U03.
- Type consistency: `validate_matrix(document: object, root: Path) -> tuple[str, ...]` is the only interface consumed across Tasks 1 and 2.
- Scope: U01 through U03 are executable now; U04 is human-blocked; later units preserve existing roadmap dependencies.
