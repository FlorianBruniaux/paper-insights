# Paper Insights Complete Program Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` to execute this plan with one integrator and at most three implementation workers. Every work package follows test-driven development and ends with a targeted commit.

**Goal:** Deliver the complete Paper Insights roadmap: reproducible arXiv acquisition, versioned provenance, local FTS5 research, citations, read-only MCP, watchlists, source-backed analysis, reversible author enrichment and federated research with YT Insights and Agentic Ecosystem Map.

**Architecture:** Build a local-first modular monolith with hexagonal boundaries. Domain and application modules depend only on immutable value objects and `Protocol` ports. SQLite, filesystems, HTTP, LLMs, CLI and MCP remain adapters. Keep one catalogue database, one separately published FTS5 database and immutable content-addressed blobs under a configurable data root.

**Tech stack:** Python 3.12, uv, Pydantic 2, Typer, SQLAlchemy 2, Alembic, SQLite FTS5, httpx, MCP Python SDK, pytest, pytest-socket, respx, Ruff and mypy.

**Supersedes for execution:** `docs/superpowers/plans/2026-08-28-foundation-vertical-slice.md`. That document remains useful as the first draft, but its interfaces and schema must not be implemented before Gate 0 below is merged.

## 1. Non-negotiable decisions

1. `papers` owns work identity only. Every observed title, abstract, DOI, author order, category, comment, journal reference, language and source URL belongs to a versioned observation.
2. Preview and ingestion consume the same immutable `PreparedDiscovery`. Execution never re-fetches a query after confirmation.
3. A multi-record source response is a `source_snapshot`, not a paper artifact. Each normalized record links to its source snapshot and ordinal.
4. `doctor` is strictly read-only. Recovery is an explicit `repair interrupted-runs --yes` command.
5. Polymorphic external identifiers are forbidden. Papers, versions and authors use separate identifier tables with real foreign keys.
6. `catalog_meta.revision` increments in the same transaction as every visible catalogue mutation. An FTS build publishes only if its source revision is still current.
7. One worker owns all Alembic revisions and SQLAlchemy catalogue models. Parallel workers never create migration heads.
8. CLI and MCP call application services only. SQLAlchemy models never leave the catalogue adapter.
9. The MCP has exactly six read-only tools in P1. It performs no network, corpus mutation, index rebuild, extraction or analysis.
10. LinkedIn stays manual. The product may create a search URL, but only a human confirmation stores a profile URL.
11. Federation orchestrates independent corpora. It does not merge their databases or compare heterogeneous BM25 scores as if they shared a scale.
12. No async runtime, web UI, PostgreSQL, Redis, embeddings or distributed queue is added before a measured need and a separate ADR.

## 2. Bounded contexts and dependency rule

| Context | Authority | Public ports |
| --- | --- | --- |
| Platform | settings, paths, clock, IDs, errors, composition | `Clock`, `IdGenerator`, `Settings` |
| Acquisition | provider queries, pages, snapshots, preview and run lifecycle | `DiscoveryProvider`, `CatalogUnitOfWorkFactory`, `BlobStore` |
| Corpus | papers, versions, observed authors, identifiers, collections | `CatalogReader`, `CorpusRepository` |
| Retrieval | index generations, documents, passages, BM25 search | `SearchIndexBuilder`, `SearchIndexReader` |
| Citations | BibTeX, Markdown and CSL-JSON rendering | `CitationRenderer` |
| Monitoring | watchlists, overlap windows, cursors and digests | `WatchlistUnitOfWorkFactory` |
| Analysis | PDF acquisition, extraction, chunking, LLM results and claims | `FullTextProvider`, `TextExtractor`, `AnalysisBackend`, `AnalysisUnitOfWorkFactory` |
| Identity | OpenAlex/ORCID observations and reversible identity decisions | `IdentityProvider`, `IdentityUnitOfWorkFactory` |
| Federation | independent queries and partial-coverage aggregation | `FederatedCorpus`, `EvidenceBundleWriter` |
| Delivery | Typer CLI and read-only MCP | application services only |

Required package shape:

```text
src/paper_insights/
├── domain/
├── application/
│   ├── ports/
│   ├── ingestion/
│   ├── research/
│   ├── monitoring/
│   ├── analysis/
│   ├── identity/
│   └── federation/
├── adapters/
│   ├── providers/
│   ├── catalog/sqlite/
│   ├── artifacts/filesystem/
│   ├── search/sqlite_fts/
│   ├── analysis/
│   ├── identity/
│   └── federation/
├── interfaces/
│   ├── cli/
│   └── mcp/
├── config.py
├── paths.py
└── bootstrap.py
```

An architecture test fails if `domain` imports `application`, `adapters` or `interfaces`, or if `application` imports `adapters` or `interfaces`.

## 3. Contracts frozen at Gate 0

Create immutable dataclasses and protocols matching these signatures. Pydantic is restricted to configuration, CLI/MCP envelopes and LLM boundary schemas.

```python
@dataclass(frozen=True, slots=True)
class DiscoveryPage:
    capture_id: UUID
    records: tuple[SourceRecord, ...]
    raw_payload: bytes
    media_type: str
    retrieved_at: datetime
    request_fingerprint: str
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class DiscoveryBatch:
    source_id: str
    query: DiscoveryQuery
    pages: tuple[DiscoveryPage, ...]
    records: tuple[ObservedPaperVersion, ...]
    issues: tuple[CollectionIssue, ...]


@dataclass(frozen=True, slots=True)
class PreparedDiscovery:
    batch: DiscoveryBatch
    preview: DiscoveryPreview
    digest: str
    prepared_at: datetime
    expires_at: datetime


class DiscoveryProvider(Protocol):
    source_id: str

    def discover(self, query: DiscoveryQuery) -> DiscoveryBatch: ...


class CatalogReader(Protocol):
    def snapshot(self) -> CatalogSnapshot: ...


class CatalogRevisionGuard(Protocol):
    def hold_if_current(self, expected: CatalogRevision) -> CatalogRevisionLease: ...


class CatalogUnitOfWorkFactory(Protocol):
    def begin(self) -> CatalogUnitOfWork: ...


class CatalogUnitOfWork(Protocol):
    corpus: CorpusRepository
    ingestion: IngestionRepository
    collections: CollectionRepository

    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class SearchIndexReader(Protocol):
    def search_papers(self, query: PaperSearchQuery) -> PaperSearchResult: ...
    def search_passages(self, query: PassageSearchQuery) -> PassageSearchResult: ...
    def get_passage(self, passage_id: PassageId) -> PassageView | None: ...


class FederatedCorpus(Protocol):
    corpus_id: CorpusId

    def capabilities(self) -> CorpusCapabilities: ...
    def search(self, query: FederatedSearchQuery) -> NativeCorpusResult: ...
    def resolve_evidence(self, ref: EvidenceRef) -> EvidenceItem | None: ...
```

`PaperSearchResult` and `PassageSearchResult` carry hits, coverage, catalogue and index revisions, `truncated`, `returned` and `available`. Every normalized observation carries page and record ordinals. The ordered `DiscoveryBatch.records` view must equal the observations embedded in its pages.

Gate 0 also freezes synchronous ports for `SearchIndexBuilder`, `CitationRenderer`, `WatchlistUnitOfWorkFactory`, `FullTextProvider`, `TextExtractor`, `AnalysisUnitOfWorkFactory`, `IdentityUnitOfWorkFactory` and `EvidenceBundleWriter`. Their complete signatures and DTO names live in `docs/specs/PORTS.md`. Workers may add implementations but may not change these contracts.

Run counters have exactly these meanings:

- `new_papers`: locally unknown works created;
- `new_versions`: locally unknown source versions created;
- `metadata_updates`: new versioned observations attached to an already known source version;
- `unchanged_records`: records whose normalized hash already exists;
- `failed_records`: selected records not committed.

Invariant at finalization:

```text
selected_records = new_versions + metadata_updates + unchanged_records + failed_records
new_papers <= new_versions
```

`passage_id` is the SHA-256 of canonical JSON containing `paper_version_id`, artifact SHA-256, `chunk_schema_version`, section, ordinal, normalized text and offsets. Its stability applies across index rebuilds of the same catalogue content and chunk schema.

## 4. Execution topology

Use four slots at most:

- Integrator: shared contracts, `pyproject.toml`, `uv.lock`, `README.md`, `CHANGELOG.md`, `.github/`, ADRs, composition root and final integration.
- Worker A: catalogue owner for the whole program, including `alembic/**` and `adapters/catalog/sqlite/**`.
- Worker B: external providers, acquisition and monitoring.
- Worker C: retrieval, delivery, analysis, identity or federation according to the active wave.

Each work package runs in an isolated Git worktree. A worker owns only the listed paths, does not edit specs or shared files and returns one targeted commit. The integrator cherry-picks only after its package gate passes. The integrator rechecks the live worktree and runs cross-package tests after every wave.

```text
Gate 0 contracts
  ├─ WP-10 catalogue ───────────┐
  ├─ WP-11 arXiv ───────────────┼─ Gate 1
  └─ WP-12 platform/artifacts ──┘
       ├─ WP-20 ingestion ──────┐
       ├─ WP-21 retrieval ──────┼─ Gate 2
       └─ WP-22 citations ──────┘
            ├─ WP-30 CLI/MCP ───┐
            ├─ WP-31 watchlists ┼─ Gate 3
            └─ WP-32 full text ─┘
                 ├─ WP-40 analysis ─┐
                 ├─ WP-41 identity ─┼─ Gate 4
                 └─ WP-42 federation┘
                           └─ audits and release
```

## 5. Wave 0: repair and freeze contracts

Wave 0 is sequential because all later packages consume its schema and ports.

### WP-00: Correct normative specifications

**Owner:** Integrator.

**Files:**

- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/specs/DATA-MODEL.md`
- Modify: `docs/specs/INGESTION.md`
- Modify: `docs/specs/SEARCH-AND-MCP.md`
- Modify: `docs/specs/PRODUCT.md`
- Create: `docs/specs/PORTS.md`
- Modify: `docs/ROADMAP.md`
- Create: `docs/specs/WATCHLISTS.md`
- Create: `docs/specs/ANALYSIS.md`
- Create: `docs/specs/AUTHOR-IDENTITY.md`
- Create: `docs/specs/FEDERATION.md`
- Create: `docs/decisions/ADR-0002-versioned-observations-and-provenance.md`
- Create: `docs/decisions/ADR-0003-preview-manifest-and-publication.md`
- Create: `docs/decisions/ADR-0004-modular-monolith-ports.md`
- Modify: `docs/superpowers/plans/2026-08-28-foundation-vertical-slice.md`
- Modify: `docs/superpowers/specs/2026-08-28-paper-insights-design.md`
- Modify: `docs/DEVELOPMENT.md`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-08-28-complete-program-execution.md` only for Gate 0 contract corrections
- Modify: `CHANGELOG.md`

**Steps:**

- [ ] Move observed metadata to `paper_versions`/`version_observations` and define separate identifier tables.
- [ ] Add source snapshots, snapshot records, categories, collections, run items, catalogue revision, claim evidence, affiliation observations and reversible identity events.
- [ ] Replace `preview(query) + iter_records(query)` with `discover(query) -> DiscoveryBatch`, then prepare and execute the exact batch.
- [ ] Keep `doctor` read-only and specify explicit repair.
- [ ] Define SQLite writer locking, WAL, `busy_timeout`, `foreign_keys`, `synchronous=FULL`, snapshot reads and crash recovery.
- [ ] Specify all six MCP read models and all three citation formats.
- [ ] Freeze every public synchronous port signature and its boundary DTO names in `docs/specs/PORTS.md`.
- [ ] Mark the old vertical-slice plan as superseded until Gate 0.

**Verification:**

Run: `uv run python scripts/validate_project.py`

Expected: PASS with all new documents linked and no scaffold regression.

Commit: `docs: freeze paper insights contracts`

### WP-01: Add domain types, ports and architecture tests

**Owner:** Integrator.

**Files:**

- Create: `src/paper_insights/domain/identifiers.py`
- Create: `src/paper_insights/domain/acquisition.py`
- Create: `src/paper_insights/domain/corpus.py`
- Create: `src/paper_insights/domain/retrieval.py`
- Create: `src/paper_insights/domain/monitoring.py`
- Create: `src/paper_insights/domain/analysis.py`
- Create: `src/paper_insights/domain/identity.py`
- Create: `src/paper_insights/domain/federation.py`
- Create: `src/paper_insights/domain/errors.py`
- Create: `src/paper_insights/application/ports/clock.py`
- Create: `src/paper_insights/application/ports/ids.py`
- Create: `src/paper_insights/application/ports/discovery.py`
- Create: `src/paper_insights/application/ports/catalog.py`
- Create: `src/paper_insights/application/ports/artifacts.py`
- Create: `src/paper_insights/application/ports/search.py`
- Create: `src/paper_insights/application/ports/citations.py`
- Create: `src/paper_insights/application/ports/monitoring.py`
- Create: `src/paper_insights/application/ports/analysis.py`
- Create: `src/paper_insights/application/ports/identity.py`
- Create: `src/paper_insights/application/ports/federation.py`
- Create: `tests/domain/test_identifiers.py`
- Create: `tests/domain/test_run_counters.py`
- Create: `tests/domain/test_preview_digest.py`
- Create: `tests/domain/test_passage_ids.py`
- Create: `tests/domain/test_error_codes.py`
- Create: `tests/domain/test_contract_shapes.py`
- Create: `tests/architecture/test_import_boundaries.py`

**Steps:**

- [ ] Write failing tests for canonical identifiers, preview digest, expiry and counter invariants.
- [ ] Add immutable dataclasses, value objects, stable error codes and protocols.
- [ ] Carry provenance, coverage, revisions and truncation in the shared read models.
- [ ] Freeze the closed CLI exit-code enum and public JSON schema versions.
- [ ] Implement UUIDv7 behind `IdGenerator`; pin `uuid-utils` in WP-02 rather than leaking it into the domain.
- [ ] Add the import-boundary test over the Python AST.

**Verification:**

Run: `uv run pytest tests/domain tests/architecture -v`

Expected: PASS.

Commit: `feat: freeze domain and application ports`

### Gate 0 acceptance

- [ ] The four ADR/spec corrections resolve versioning, provenance, preview, publication and boundary ownership.
- [ ] No infrastructure import exists in `domain` or `application`.
- [ ] DTOs, error codes, JSON envelopes and CLI exit codes are closed-world and versioned.
- [ ] Worker A has exclusive migration ownership recorded in this plan.
- [ ] Integrator approves the Gate 0 commit before opening implementation worktrees.

## 6. Wave 1: foundations, three packages in parallel

### WP-10: Catalogue and initial migration

**Owner:** Worker A, exclusive for all catalogue schema work.

**Files:**

- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/0001_initial_catalog.py`
- Create: `src/paper_insights/adapters/catalog/sqlite/engine.py`
- Create: `src/paper_insights/adapters/catalog/sqlite/models.py`
- Create: `src/paper_insights/adapters/catalog/sqlite/uow.py`
- Create: `src/paper_insights/adapters/catalog/sqlite/readers.py`
- Create: `tests/catalog/test_migrations.py`
- Create: `tests/catalog/test_constraints.py`
- Create: `tests/catalog/test_uow.py`
- Create: `tests/catalog/test_snapshot.py`

**Required schema:** `catalog_meta`, `sources`, `stored_blobs`, `source_snapshots`, `snapshot_records`, `ingestion_runs`, `ingestion_run_items`, `collection_errors`, `papers`, `paper_versions`, `version_observations`, `paper_identifiers`, `paper_identifier_evidence`, `version_identifiers`, `version_identifier_evidence`, `authors`, `author_identifiers`, `author_identifier_evidence`, `paper_authors`, `paper_version_categories`, `artifacts`, `collections`, `collection_papers`.

**Steps:**

- [ ] Write failing zero-to-head, foreign-key, JSON, partial-current-version and rollback tests.
- [ ] Implement the migration with real FKs, `CHECK` constraints and a partial unique index for one current version per paper/source.
- [ ] Implement one-item `BEGIN IMMEDIATE` units of work and read-only snapshot readers.
- [ ] Increment `catalog_meta.revision` inside visible mutation transactions.
- [ ] Prove two concurrent writers respect `busy_timeout` and never corrupt counts.

**Verification:**

Run: `uv run pytest tests/catalog -v`

Expected: PASS, including `PRAGMA foreign_key_check` and `quick_check`.

Commit: `feat: add revisioned sqlite catalog`

### WP-11: Bounded arXiv provider

**Owner:** Worker B.

**Files:**

- Create: `src/paper_insights/adapters/providers/arxiv/client.py`
- Create: `src/paper_insights/adapters/providers/arxiv/parser.py`
- Create: `src/paper_insights/adapters/providers/arxiv/normalizer.py`
- Create: `tests/fixtures/arxiv/page-1.xml`
- Create: `tests/fixtures/arxiv/page-2-overlap.xml`
- Create: `tests/fixtures/arxiv/revision-v2.xml`
- Create: `tests/providers/test_arxiv_parser.py`
- Create: `tests/providers/test_arxiv_normalizer.py`
- Create: `tests/providers/test_arxiv_client.py`
- Create: `tests/providers/test_arxiv_pagination.py`

**Steps:**

- [ ] Write failing fixture tests for namespaces, ordered authors, missing DOI, all categories and v1/v2 history.
- [ ] Stream responses under a configured byte limit and reject unexpected scheme, host or redirect target.
- [ ] Implement deterministic pagination, overlap deduplication and stop-at-limit semantics.
- [ ] Bound retries for timeout, 429 and 5xx; honor bounded `Retry-After`; never retry permanent 4xx.
- [ ] Return raw pages and normalized records together in one `DiscoveryBatch`.

**Verification:**

Run: `uv run pytest --disable-socket tests/providers -v`

Expected: PASS without a real network request.

Commit: `feat: add bounded arxiv discovery adapter`

### WP-12: Packaging, configuration, files and doctor

**Owner:** Worker C. The integrator alone applies shared-file changes from this commit.

**Files:**

- Modify: `pyproject.toml`
- Create: `src/paper_insights/__init__.py`
- Create: `src/paper_insights/config.py`
- Create: `src/paper_insights/paths.py`
- Create: `src/paper_insights/adapters/artifacts/filesystem/store.py`
- Create: `src/paper_insights/interfaces/cli/app.py`
- Create: `src/paper_insights/interfaces/cli/doctor.py`
- Create: `tests/config/test_settings.py`
- Create: `tests/config/test_paths.py`
- Create: `tests/artifacts/test_store.py`
- Create: `tests/cli/test_doctor.py`

**Steps:**

- [ ] Add `[build-system]`, console script `paper-insights`, strict mypy/Ruff/pytest config and pinned runtime/dev dependency groups.
- [ ] Reject unknown configuration keys and derive every path from one `data_root`.
- [ ] Publish content-addressed blobs using private sibling temporary files, `fsync`, path confinement and `os.replace`.
- [ ] Detect symlink escapes and report orphaned blobs without deleting them.
- [ ] Make `doctor --json` perform no write, network call, repair or secret echo.

**Verification:**

Run: `uv lock && uv sync --all-extras --dev`

Run: `uv run pytest tests/config tests/artifacts tests/cli/test_doctor.py -v`

Expected: PASS and `git diff --exit-code uv.lock` after a second `uv lock`.

Commit: `feat: add installable local platform foundation`

### Gate 1 integration

**Owner:** Integrator.

- [ ] Cherry-pick WP-10, WP-11 and WP-12 in that order.
- [ ] Resolve shared-file changes without altering package-owned behavior.
- [ ] Create `.github/workflows/ci.yml` with `static`, `unit` and `integration-mcp` jobs and `contents: read` only.
- [ ] Create `src/paper_insights/bootstrap.py` with dependency injection, but no client construction at import time.
- [ ] Run `uv lock --check`, Ruff, mypy and all Wave 1 tests.
- [ ] Commit as `build: integrate paper insights foundations`.

## 7. Wave 2: usable arXiv vertical, three packages in parallel

### WP-20: Prepared ingestion and recovery

**Owner:** Worker B.

**Files:**

- Create: `src/paper_insights/application/ingestion/prepare.py`
- Create: `src/paper_insights/application/ingestion/execute.py`
- Create: `src/paper_insights/application/ingestion/repair.py`
- Create: `tests/ingestion/test_prepare.py`
- Create: `tests/ingestion/test_execute.py`
- Create: `tests/ingestion/test_partial_failure.py`
- Create: `tests/ingestion/test_recovery.py`

**Steps:**

- [ ] Prove preview makes zero filesystem or catalogue mutation.
- [ ] Digest canonical query, selected source version IDs and, for every ordered raw page, capture UUIDv7, SHA-256, retrieval timestamp and request fingerprint.
- [ ] Reject expired or mismatched confirmation before opening a run.
- [ ] Publish raw and canonical metadata blobs outside SQL transactions, then attach all snapshots and records with run creation in one transaction before processing one record per short transaction.
- [ ] Inject crashes before blob replace, after blob publication and before the snapshot/run commit; prove no partial snapshot graph becomes visible.
- [ ] Record exact success/failure counters and make a repeated batch unchanged.
- [ ] Implement explicit `RepairInterruptedRuns`, never invoked by doctor.

**Verification:**

Run: `uv run pytest tests/ingestion -v`

Expected: PASS for exact-batch confirmation, idempotence, partial failure and interruption recovery.

Commit: `feat: add confirmed idempotent ingestion`

### WP-21: FTS5 index and search

**Owner:** Worker C.

**Files:**

- Create: `src/paper_insights/application/research/search.py`
- Create: `src/paper_insights/application/research/index.py`
- Create: `src/paper_insights/adapters/search/sqlite_fts/schema.py`
- Create: `src/paper_insights/adapters/search/sqlite_fts/builder.py`
- Create: `src/paper_insights/adapters/search/sqlite_fts/reader.py`
- Create: `tests/search/test_passage_ids.py`
- Create: `tests/search/test_builder.py`
- Create: `tests/search/test_reader.py`
- Create: `tests/search/test_hostile_queries.py`
- Create: `tests/benchmarks/search_queries.jsonl`
- Create: `tests/benchmarks/test_search_relevance.py`

**Steps:**

- [ ] Generate deterministic title and abstract passages from each observation's canonical `metadata` artifact in a coherent catalogue snapshot.
- [ ] Build one sibling FTS database whose authoritative receipt is `index_meta`, run `quick_check`, verify counts and recheck catalogue revision.
- [ ] Abandon a stale build and preserve the previously published index after any injected crash.
- [ ] Open reads with URI `mode=ro`, enable `query_only` and sanitize hostile FTS input.
- [ ] Return stable IDs, raw BM25 score, rank, bounded excerpt, coverage and index revision.

**Human gate:** Annotate 30 representative queries. At least 24 must place one expected relevant paper in the top five, with no P0 relevance failure. Store verdicts in `tests/benchmarks/search_queries.jsonl`.

**Verification:**

Run: `uv run pytest tests/search tests/benchmarks/test_search_relevance.py -v`

Expected: automated tests PASS; benchmark remains blocked until the human labels and verdict are present.

Commit: `feat: add revision-safe local paper search`

### WP-22: Collections and citations

**Owner:** Worker A, no migration change required because collections are in `0001_initial`.

**Files:**

- Create: `src/paper_insights/application/research/collections.py`
- Create: `src/paper_insights/application/research/citations.py`
- Create: `tests/collections/test_service.py`
- Create: `tests/citations/test_bibtex.py`
- Create: `tests/citations/test_markdown.py`
- Create: `tests/citations/test_csl_json.py`
- Create: `tests/citations/test_identifier_resolution.py`

**Steps:**

- [ ] Resolve internal, arXiv and DOI identifiers without title guessing.
- [ ] Create, rename, list, add to and remove from collections through application services; keep MCP read-only.
- [ ] Render BibTeX, Markdown and CSL-JSON from observed catalogue metadata only.
- [ ] Preserve author order, escape BibTeX deterministically and list missing fields.
- [ ] Define collection read models and stable counts for CLI/MCP.

**Verification:**

Run: `uv run pytest tests/collections tests/citations -v`

Expected: PASS with no fabricated field.

Commit: `feat: add collections and source-backed citations`

### Gate 2 integration

**Owner:** Integrator.

**Files:**

- Create: `src/paper_insights/interfaces/cli/ingest.py`
- Create: `src/paper_insights/interfaces/cli/discover.py`
- Create: `src/paper_insights/interfaces/cli/search.py`
- Create: `src/paper_insights/interfaces/cli/index.py`
- Create: `src/paper_insights/interfaces/cli/citations.py`
- Create: `src/paper_insights/interfaces/cli/collections.py`
- Create: `src/paper_insights/interfaces/cli/repair.py`
- Modify: `src/paper_insights/interfaces/cli/app.py`
- Create: `tests/integration/test_arxiv_vertical_slice.py`
- Create: `tests/integration/test_cli_discover.py`
- Create: `tests/integration/test_cli_collections.py`

**Acceptance:**

- [ ] Fixed fixtures produce two works, three versions and linked raw snapshots.
- [ ] The same batch produces zero new versions on its second execution.
- [ ] A v2 collected later does not overwrite v1 metadata.
- [ ] A failed item remains linked to its run without losing prior successes.
- [ ] Search and all citation formats resolve to the exact version and snapshot.
- [ ] `discover` reste sans mutation et les commandes de collection couvrent create, rename, list, add et remove.
- [ ] Every test runs with sockets disabled except explicit respx provider tests.

Commit: `test: gate the offline arxiv vertical slice`

## 8. Wave 3: delivery, monitoring and full text in parallel

Before opening the three worktrees, Worker A creates and lands `0002_watchlists.py`. After that schema cut, WP-30, WP-31 and WP-32 run concurrently.

### WP-30: Closed-world read-only MCP

**Owner:** Worker A after the watchlist migration is merged.

**Files:**

- Create: `src/paper_insights/interfaces/mcp/schemas.py`
- Create: `src/paper_insights/interfaces/mcp/server.py`
- Create: `tests/mcp/test_contract.py`
- Create: `tests/mcp/test_payloads.py`
- Create: `tests/mcp/test_read_only.py`
- Create: `tests/mcp/test_stdio_client.py`

**Steps:**

- [ ] Expose exactly `list_collections`, `search_papers`, `get_paper`, `search_passages`, `get_passage` and `get_citation`.
- [ ] Reject extra arguments, booleans-as-integers, malformed IDs and invalid limits before service calls.
- [ ] Set all four MCP annotations and enforce 24 KiB structured and 64 KiB total response limits.
- [ ] Open catalogue and search SQLite connections read-only with `query_only`.
- [ ] Prove every tool works through a real stdio MCP client and cannot call write ports or network.

**Verification:**

Run: `uv run --extra mcp pytest --disable-socket tests/mcp -v`

Expected: PASS.

Commit: `feat: expose closed-world paper research mcp`

### WP-31: Watchlists and digests

**Owner:** Worker B. Worker A alone authors the additive migration before the three parallel packages begin.

**Files:**

- Create: `alembic/versions/0002_watchlists.py` (Worker A)
- Create: `src/paper_insights/application/monitoring/run_watchlist.py`
- Create: `src/paper_insights/application/monitoring/digest.py`
- Create: `src/paper_insights/adapters/catalog/sqlite/watchlists.py`
- Create: `src/paper_insights/interfaces/cli/watch.py`
- Create: `tests/watchlists/test_cursor.py`
- Create: `tests/watchlists/test_deduplication.py`
- Create: `tests/watchlists/test_digest.py`
- Create: `tests/watchlists/test_scheduler_exit_codes.py`

**Steps:**

- [ ] Store query, validated cursor, overlap window and last successful run.
- [ ] Require `--yes` for each `watch run`, including scheduler calls; without it return code 3 and zero mutation.
- [ ] Diff on source paper/version identifiers, not cursor position alone.
- [ ] Deduplicate multi-category notices in one digest.
- [ ] Advance the cursor only in successful finalization; retain the previous cursor after partial/failed runs.
- [ ] Emit deterministic Markdown and JSON digests with the product codes: 0 success, 2 invalid input or configuration, 3 confirmation required, 4 partial success, 5 source unavailable and 6 corpus invalid.

**Verification:**

Run: `uv run pytest tests/watchlists -v`

Expected: the second identical run contains zero new items and interruption preserves the prior cursor.

Commit: `feat: add resumable paper watchlists`

### WP-32: Policy-bound PDF and text extraction

**Owner:** Worker C. This package runs concurrently with WP-30 and WP-31 and does not import the MCP adapter.

**Files:**

- Create: `docs/policies/FULLTEXT-ACCESS.md`
- Create: `src/paper_insights/application/analysis/acquire_fulltext.py`
- Create: `src/paper_insights/adapters/providers/arxiv/pdf.py`
- Create: `src/paper_insights/adapters/analysis/pymupdf_extractor.py`
- Create: `tests/fixtures/pdf/valid.pdf`
- Create: `tests/fixtures/pdf/encrypted.pdf`
- Create: `tests/fixtures/pdf/truncated.pdf`
- Create: `tests/fulltext/test_downloader.py`
- Create: `tests/fulltext/test_extractor.py`
- Create: `tests/fulltext/test_hostile_documents.py`

**Steps:**

- [ ] Document allowed sources, provenance, retention and explicit refusal cases before downloader code.
- [ ] Enforce allowed HTTPS hosts, redirect policy, streamed byte cap, MIME and PDF signature before publication.
- [ ] Run extraction with time/page/character limits and no network.
- [ ] Link derived text to PDF SHA-256, extractor name/version and source URL.
- [ ] Reject encrypted, malformed, oversized or timed-out documents with stable codes.

**Verification:**

Run: `uv run pytest --disable-socket tests/fulltext -v`

Expected: PASS for valid and hostile fixtures.

Commit: `feat: add bounded fulltext extraction`

### Gate 3 acceptance

- [ ] MCP behavioral test passes through stdio and all six tools remain read-only.
- [ ] Watchlist replay, overlap, cursor recovery and scheduler exit codes pass.
- [ ] Full-text policy is reviewed before enabling any live download.
- [ ] `paper-researcher` configuration loads the local MCP and can search, retrieve a passage and cite it without mutation.
- [ ] Integrator commits `test: gate mcp monitoring and fulltext`.

## 9. Wave 4: analysis, identity and federation in parallel

### WP-39: Wave 4 schema and federation contract cut

**Owner:** Integrator for the ADR; Worker A for both migrations. This package lands before any Wave 4 worker is dispatched.

**Files:**

- Create: `docs/decisions/ADR-0005-federated-corpus-contract.md` (Integrator)
- Create: `alembic/versions/0003_analysis.py` (Worker A)
- Create: `alembic/versions/0004_author_identity.py` (Worker A)
- Modify: `tests/catalog/test_migrations.py` (Worker A)

**Steps:**

- [ ] Freeze corpus capabilities, native scores, source types, partial coverage and evidence-bundle manifest in ADR-0005.
- [ ] Land both additive migrations against one linear Alembic head.
- [ ] Run zero-to-head, every-upgrade, foreign-key and quick-check tests before opening Wave 4 worktrees.
- [ ] Commit the ADR separately from Worker A's migration commit with explicit pathspecs.

Once this contract cut passes, WP-40, WP-41 and WP-42 run concurrently.

### WP-40: Source-backed analysis and cache

**Owner:** Worker A after both Wave 4 migrations are merged.

**Files:**

- Consume: `alembic/versions/0003_analysis.py` from WP-39
- Create: `src/paper_insights/application/analysis/schemas.py`
- Create: `src/paper_insights/application/analysis/chunking.py`
- Create: `src/paper_insights/application/analysis/service.py`
- Create: `src/paper_insights/adapters/analysis/openai_backend.py`
- Create: `src/paper_insights/adapters/catalog/sqlite/analyses.py`
- Create: `src/paper_insights/interfaces/cli/analyze.py`
- Create: `tests/analysis/test_chunking.py`
- Create: `tests/analysis/test_schema.py`
- Create: `tests/analysis/test_claim_evidence.py`
- Create: `tests/analysis/test_cache.py`
- Create: `tests/analysis/test_prompt_injection_boundary.py`
- Create: `tests/analysis/test_human_gate.py`
- Human-produced: `tests/benchmarks/analysis_reviews.jsonl`
- Human-produced: `tests/benchmarks/analysis_acceptance.json`

**Steps:**

- [ ] Version chunk, prompt and result schemas; set Pydantic `extra="forbid"`.
- [ ] Treat paper text as untrusted data and keep it outside system/developer instructions.
- [ ] Key the cache on paper version, artifact SHA-256, ordered passage IDs, chunk schema, prompt version and SHA-256, provider, model, request parameters and result schema version.
- [ ] Store raw model stop reason and validation state.
- [ ] Publish `complete` only when every claim references at least one existing passage.
- [ ] Preserve a prior valid result when a retry is truncated or invalid.
- [ ] Validate the closed human-review schemas, exact dataset SHA-256, canonical attestation SHA-256 and derived counters; fail closed when any field or human verdict is absent.

**Human gate:** A human reviews 20 analyses across at least four paper types in `analysis_reviews.jsonl` and signs `analysis_acceptance.json` as defined in `docs/specs/ANALYSIS.md`. Each unsupported claim is a P0 failure. At least 18 of 20 must be rated useful and faithful before batch mode is enabled. Agents must not invent or prefill reviewer identities, approvals or verdicts.

**Verification:**

Run: `uv run pytest --disable-socket tests/analysis -v`

Expected: automated tests PASS; batch mode remains disabled until both human evaluation artifacts are present, valid and consistent.

Commit: `feat: add source-backed paper analysis`

### WP-41: Reversible author enrichment

**Owner:** Worker B after both Wave 4 migrations are merged.

**Files:**

- Consume: `alembic/versions/0004_author_identity.py` from WP-39
- Create: `src/paper_insights/application/identity/enrich.py`
- Create: `src/paper_insights/application/identity/matching.py`
- Create: `src/paper_insights/application/identity/decisions.py`
- Create: `src/paper_insights/adapters/identity/openalex.py`
- Create: `src/paper_insights/adapters/identity/orcid.py`
- Create: `src/paper_insights/adapters/catalog/sqlite/identity.py`
- Create: `src/paper_insights/interfaces/cli/authors.py`
- Create: `tests/identity/test_openalex.py`
- Create: `tests/identity/test_orcid.py`
- Create: `tests/identity/test_matching.py`
- Create: `tests/identity/test_reversible_decisions.py`
- Create: `tests/identity/test_linkedin_manual_confirmation.py`

**Steps:**

- [ ] Store provider responses as provenance-bearing observations, never direct identity mutations.
- [ ] Merge automatically only on exact verified ORCID or an explicitly approved equivalent rule.
- [ ] Produce review candidates for names, affiliations and co-author evidence.
- [ ] Store merge/split events with evidence, actor, timestamp and inverse operation.
- [ ] Generate LinkedIn search URLs separately; only an explicit confirmation command stores a profile URL.

**Verification:**

Run: `uv run pytest --disable-socket tests/identity -v`

Expected: two homonyms remain separate and every accepted merge can be reversed losslessly.

Commit: `feat: add reversible author identity enrichment`

### WP-42: Federated research

**Owner:** Worker C after the MCP contract is stable. The integrator owns ADR-0005 and lands it before dispatch.

**Files:**

- Consume: `docs/decisions/ADR-0005-federated-corpus-contract.md`
- Create: `src/paper_insights/application/federation/models.py`
- Create: `src/paper_insights/application/federation/service.py`
- Create: `src/paper_insights/adapters/federation/papers.py`
- Create: `src/paper_insights/adapters/federation/yt_insights.py`
- Create: `src/paper_insights/adapters/federation/agentic_ecosystem_map.py`
- Create: `src/paper_insights/application/federation/evidence_export.py`
- Create: `src/paper_insights/interfaces/cli/federated.py`
- Create: `tests/federation/test_contract.py`
- Create: `tests/federation/test_partial_coverage.py`
- Create: `tests/federation/test_source_types.py`
- Create: `tests/federation/test_evidence_export.py`

**Steps:**

- [ ] Freeze `FederatedResult v1` with corpus authority, native ID, source type, provenance, citation and coverage status.
- [ ] Implement three adapters against versioned public CLI/MCP contracts, not direct database imports.
- [ ] Keep per-corpus ranking and never normalize unrelated BM25 scores into a shared percentage.
- [ ] Report unavailable corpora as partial coverage without discarding successful results.
- [ ] Export a manifest and evidence files grouped by corpus with checksums.

**Verification:**

Run: `uv run pytest --disable-socket tests/federation -v`

Expected: a repository or video can never be rendered as a paper citation, and one unavailable corpus yields explicit partial coverage.

Commit: `feat: add provenance-preserving federated research`

### Gate 4 acceptance

- [ ] Every published analysis claim resolves to a stored passage.
- [ ] Human analysis review and acceptance artifacts pass their closed-schema, checksum, attestation and threshold validation before batch processing is enabled.
- [ ] Author merges are evidence-backed and reversible; LinkedIn remains human-only.
- [ ] Federation retains native authority and explicit partial coverage.
- [ ] Integrator commits `test: gate analysis identity and federation`.

## 10. Wave 5: hardening and independent audits

Run three read-only review packages in parallel after all implementation commits are integrated.

### WP-50: Integrity and recovery audit

**Owner:** Reviewer A, read-only.

- [ ] Test migrations from zero and each released revision.
- [ ] Inject crashes around blob publication, snapshot attach, item commit, cursor finalization and index replace.
- [ ] Verify `foreign_key_check`, `quick_check`, blob hashes, orphan reporting and catalogue/index revisions.
- [ ] Report findings by priority with exact reproduction commands.

### WP-51: MCP and federation audit

**Owner:** Reviewer B, read-only.

- [ ] Enumerate the exact tool surface and annotations.
- [ ] Instrument filesystem, SQLite and socket writes during every MCP call.
- [ ] Fuzz unknown and oversized parameters and payload clipping.
- [ ] Simulate each corpus outage and cross-type citation confusion.

### WP-52: Analysis and identity audit

**Owner:** Reviewer C, read-only.

- [ ] Attempt prompt injection through paper text and metadata.
- [ ] Test invalid, truncated and stale cached LLM responses.
- [ ] Sample every claim-to-passage edge.
- [ ] Attempt homonym merges and unconfirmed LinkedIn profile writes.

### Gate 5 remediation

The integrator triages all P0/P1 findings. Remediation uses new targeted packages under the original file owner. The release gate stays closed while any P0 is open, any P1 integrity issue is unmitigated, either human benchmark is incomplete, or any evidence remains `UNKNOWN`.

## 11. Final release gate

**Owner:** Integrator.

**Files:**

- Modify: `README.md`
- Modify: `docs/DEVELOPMENT.md`
- Modify: `docs/ROADMAP.md`
- Modify: `CHANGELOG.md`
- Modify: `.github/workflows/ci.yml`

**Commands:**

```bash
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run --all-extras pytest --disable-socket --cov=paper_insights --cov-branch --cov-report=term-missing
uv run alembic upgrade head
uv run python scripts/validate_project.py
```

Additional behavior checks:

- [ ] Run the complete arXiv fixture-to-MCP flow from an empty temporary data root.
- [ ] Run an identical watchlist twice and verify zero new items on the second run.
- [ ] Rebuild FTS while injecting a failure and prove the previous index remains readable.
- [ ] Run the MCP through a real client with write and socket probes active.
- [ ] Verify an analysis claim opens its exact passage and source artifact.
- [ ] Reverse one author merge and prove the pre-merge state is restored.
- [ ] Run federation with one corpus unavailable and inspect the evidence manifest.
- [ ] Verify both human benchmark files contain completed verdicts and acceptance signatures.
- [ ] Inspect `git status --short` and preserve unrelated user changes.

Coverage thresholds:

- domain and application branch coverage: at least 90 percent;
- adapters: no global percentage claim; every public adapter path has contract and failure tests;
- human search relevance: at least 24 of 30 queries with an expected paper in top five and zero P0 failure;
- human analysis review: at least 18 of 20 useful and faithful, with zero unsupported published claim.

Final commit: `feat: complete paper insights research platform`

## 12. Execution protocol

For each wave:

1. The integrator records the start commit and creates one isolated worktree per worker.
2. Each worker receives one work package, exact path ownership and the instruction not to revert concurrent edits.
3. Workers write the failing test first, run the focused test, implement the minimum code, run their package gate and commit explicit pathspecs.
4. The integrator reviews the diff, cherry-picks in dependency order and runs all accumulated tests.
5. Any contract change stops the wave and returns to the integrator. Workers do not silently alter ports or migrations.
6. Independent reviewers run only after the implementation package is green.
7. `CHANGELOG.md` is maintained by the integrator at every integrated behavior change; workers do not contend on it.
8. A gate is complete only when behavior is executed. Structural validation alone is not runtime proof.

The first execution session starts with WP-00 and WP-01 only. Wave 1 opens after Gate 0 is committed and reviewed.
