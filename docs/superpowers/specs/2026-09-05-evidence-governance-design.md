# Evidence Governance Design

**Status:** Approved direction from the 2026-09-05 repository comparison. This design extends the complete program without replacing its roadmap, architecture or work-package order.

## Decision

Paper Insights adds a repository-level evidence-governance layer before opening further runtime waves. This layer records what is specified, implemented, deterministically checked, behaviorally measured and human-reviewed. It does not add a runtime service, a new database, a model router or a second orchestration system.

The authoritative execution plan remains `docs/superpowers/plans/2026-08-28-complete-program-execution.md`. The companion plan created for this design adds cross-cutting acceptance criteria and names the gates that block each optimization.

## Problem

The integration branch contains the Gate 0 contracts, the Gate 1 foundation, the Gate 2 local retrieval implementation and its offline relevance harness. Evidence is currently distributed across tests, the roadmap, the changelog and benchmark documentation. A reader can mistake one of these states for another:

- source files exist;
- deterministic tests pass;
- a behavior was measured on a named population;
- a human gate is complete;
- the feature is operational in a real corpus.

The current Gate 2 human benchmark is explicitly blocked at 0 of 30 reviews. Wave 3 must therefore remain closed even though the automated suite passes.

## Scope

### Included

1. A canonical JSON capability and evidence matrix checked with the Python standard library.
2. A repository risk register tied to matrix capability identifiers.
3. A data-flow inventory for network calls and durable stores.
4. Explicit Gate 2 product decisions and human-review evidence.
5. Stronger Wave 4 analysis receipts, claim evidence states and adversarial instruction/data tests.
6. Typed bibliographic observations and screening accounting only when their owning workflows exist.

### Excluded

- importing prompts, agents, schemas or source code from Academic Research Skills;
- starting WP-30, WP-31 or WP-32 before Gate 2 human acceptance;
- multi-model verification, reviewer panels or ranking changes;
- replacing SQLite authority with passports or hidden caches;
- adding PostgreSQL, Redis, embeddings, async orchestration or a web UI.

## Capability Matrix Contract

The source of record is `docs/evidence/capability-matrix.json` with `schema_version: "capability-matrix-v1"` and an ordered `capabilities` array.

Each capability contains:

- `id`: stable dotted identifier;
- `roadmap_gate`: `gate0` through `gate5` or `release`;
- `mechanism_status`: `specified`, `implemented` or `operational`;
- `deterministic_evidence`: status plus repository evidence references;
- `behavioral_evidence`: status plus repository evidence references;
- `human_evidence`: status, optional denominator and evidence references;
- `known_exclusions`: non-empty bounded claims that are not established;
- `claim_ceiling`: strongest statement licensed by current evidence;
- `next_evaluation`: one observable next proof step.

Allowed deterministic statuses are `not_run`, `passed`, `failed` and `blocked`. Allowed behavioral and human statuses are `not_run`, `measured`, `mixed`, `failed` and `blocked`.

The validator fails when:

- the schema version, top-level keys or row keys are unknown;
- capability identifiers are duplicated or unordered;
- an allowed vocabulary is violated;
- a positive evidence status lacks an existing repository reference;
- a human denominator is invalid or disagrees with its status;
- exclusions, claim ceiling or next evaluation are empty;
- a capability is marked `operational` without measured behavioral evidence and complete human evidence.

This matrix records evidence. It does not infer that tests prove production behavior.

## Risk and Data-Flow Contracts

`docs/evidence/RISK-REGISTER.md` maps each standing risk to capability IDs, existing controls, evidence status and residual gap. It never upgrades a status independently from the matrix.

`docs/evidence/DATA-FLOWS.md` inventories each direct network path and durable store with trigger, transmitted or stored data, destination, credentials, limits, retention and off switch. A check compares declared Python network adapters with documented rows. Indirect model or CLI transports remain review-owned and explicitly marked as such.

## Gate 2 Decision

Gate 2 remains the immediate product frontier. Before any human scoring run, the project owner records:

1. the representative-query sampling rules;
2. the exact P0 relevance definition;
3. the hash-bound catalogue and FTS index chosen as the reference corpus.

The tracked benchmark stays blank until a real reviewer completes the 30 records. Automated tools may prepare forms and verify hashes, but may not populate identities, verdicts or approval.

## Wave 4 Analysis Refinement

WP-40 keeps its existing cache key and claim-to-passage constraint. Its migration and runtime add an immutable analysis receipt containing the catalogue revision, `paper_version_id`, `version_observation_id`, artifact SHA-256, ordered passage IDs, chunk schema, prompt version and SHA-256, result schema, provider, model, canonical parameters, stop reason and stochasticity declaration.

Claim evidence separates:

- extraction and availability state;
- support verdict;
- evidence coverage;
- exact source artifact and offsets.

An exact excerpt does not imply support. An unresolvable, unchecked or degraded state never becomes a clean verdict.

The prompt-injection test moves from audit-only thinking to a WP-40 acceptance test. It must show that adversarial paper text cannot alter tools, file access, network authorization, system instructions or output schema.

## Bibliographic Observations and Screening

Bibliographic checks are immutable observations with source, source identifier, retrieval time, staleness threshold, check status and finding. `not_checked`, `unavailable`, `degraded` and `stale` remain distinct from a clean finding. Citation existence never proves claim support.

Screening accounting is introduced only with a workflow that selects literature for a collection or analysis. Every run must satisfy `scanned = included + excluded + skipped`, retain reasons and apply the same criteria to local and external candidates. Generic ingestion does not gain screening semantics.

## Delivery Graph

```text
U01 evidence matrix and validator
  -> U02 roadmap, README and validation wiring
  -> U03 risk register and data-flow inventory
  -> U04 Gate 2 decision packet and 30 human reviews
  -> U05 existing Wave 3 work packages
  -> U06 Wave 4 analysis evidence refinement
  -> U07 bibliographic observations and screening accounting
  -> U08 existing hardening and release audits
```

U01 is the only implementation frontier opened by this design. U04 requires human decisions and review. U05 through U08 remain blocked by their existing roadmap gates.

## Verification

- `python3 scripts/check_capability_matrix.py`
- `python3 scripts/validate_project.py`
- `uv run pytest --disable-socket`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src`

No live provider, model or external corpus call is required for U01 through U03.
