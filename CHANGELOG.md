# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added

- Accepted critical source review specification and bounded implementation plan: paper-specific appraisal, abstract/full-text evidence limits, reversible editorial selection, and calibration of false exclusions. Linked into Phase 5, WP-40, the analysis contract, and the capability matrix; no review runtime or automatic quality filter is delivered.
- English workflow infographic near the top of the README, styled after YouTube Video Insights, with current CLI stages, experimental status, and a separate planned-feature row.
- Editable Mermaid workflow and image-generation prompt with source and asset provenance.
- Author profile at the top of the README, repository badges, and links to YouTube Video Insights, Claude Code Ultimate Guide, Google Search Console MCP, and the wider project portfolio.
- Evidence-backed audit of `academic-research-skills` at commit `8e4c877`, with scores for all four skills, verification of all 189 referenced resources, and a bounded adoption decision for Paper Insights.
- Proposed decision packet for the human relevance benchmark, with reversible corpus options, query distribution, P0 boundaries, and fingerprint-bound fields to complete after inventory.
- Design and implementation plan for cross-cutting evidence governance without changing the existing work-package order.
- Machine-readable capability matrix with deterministic, behavioral and human evidence states, bounded claims and next evaluations.
- Dependency-free capability-matrix validator with fail-closed tests for invalid statuses, missing evidence, denominators and unjustified operational claims.
- Risk register and checked data-flow inventory tied to the capability matrix and direct network imports.
- Documentation foundation for Paper Insights.
- Initial product, data model, ingestion, search, and MCP specifications.
- Local configuration for Claude Code and compatible agents.
- Security and routing hooks with unit tests.
- Verified `unittest` discovery from the root of the `tests` directory.
- Git guard verified against broad staging without blocking explicit relative pathspecs.
- Roadmap and implementation plan for the first vertical slice.
- Complete execution plan for phases 0 through 7, with P0 contracts, parallel work packages, file ownership, gates, and release criteria.
- Gate 0 contracts for versioned observations, multi-record source snapshots, foreign-key identifiers, and atomic catalog revisions.
- Normative specifications for watchlists, evidence-backed analysis, reversible author identity, and cross-corpus federation.
- Closed contracts for collections, three citation formats, six MCP tools, JSON envelopes, and CLI exit codes.
- Complete synchronous port contracts, separate identifier evidence, and versioned bibliographic artifacts.
- Immutable domain types, synchronous ports, and Gate 0 architecture tests.
- Revisioned SQLite catalog with an Alembic migration, composite foreign keys, provenance history, and strictly read-only snapshots.
- Bounded arXiv adapter with redirect validation, deterministic pagination, deduplication, and versioned normalization tested on local fixtures.
- Installable Python foundation, atomic blob storage, and read-only `doctor` diagnostics that distinguish proven corruption from `UNKNOWN` status.
- CI workflow separating static checks, offline unit tests, and the MCP boundary gate before MCP runtime implementation.
- Prepared ingestion with exact confirmation, atomic snapshot graph attachment, short per-record transactions, closed counters, idempotent replay, and explicit repair of interrupted runs.
- Application collections and BibTeX, Markdown, and CSL-JSON citations rendered from an exact observation and provenance, without invented bibliographic fields.
- Self-describing local FTS5 `fts-v2` index with deterministic passages, revision-guarded publication, descriptor-bound read-only access, and six closed filters.
- Gate 2 CLI for discovery, confirmed ingestion, paper and passage search, index rebuilding, BibTeX, Markdown, and CSL-JSON citations, collections, and explicit repair, with versioned JSON envelopes and offline arXiv fixtures.
- Offline Gate 2 harness for blind inventory, execution of 30 searches, capture of the top five `paper_id` values, review forms, and closed validation of human verdicts.

### Changed

- README and changelog translated into English, preserving gate status, evidence limits, identifiers, and measurements.
- Public GitHub publication with the integrated version on `main`; the README retains the experimental status and absence of a public license.
- The Gate 2 benchmark protocol now points to the already approved D1 through D3 decisions and distinguishes their scope for the current candidate from the 30 outstanding human reviews.
- All three Paper Insights skills now use the available Gate 2 CLI, keep MCP as an unopened Gate 3 capability, and include positive and negative routing corpora shared by the Claude Code and Codex projections. The routing hook also distinguishes standalone citation export from research that subsequently requests a citation.
- Decisions D1 through D3, followed by the 30 exact D2 ground truths, are approved. The Gate 2 packet binds the real `gate2-arxiv-metadata-v1` candidate, its catalog at revision 147, its `fts-v2` index, blind inventory, queries, and execution: 30 fully covered queries, 25 raw top-five matches, and no must-find misses. The 30 human verdicts remain absent; Gate 2 stays blocked at 0/30, and the measurement does not prove historical arXiv exhaustiveness.
- arXiv queries now order provider records by descending `submittedDate`. A version's eligibility for a historical cutoff must be checked separately against the retrieved version's metadata.
- Project validation now consumes the capability matrix, and README distinguishes the implemented Gate 2 integration surface from the blocked human relevance gate and unopened later waves.
- The roadmap and complete execution plan now reference the evidence-governance overlay as a cross-cutting control rather than a competing plan.
- The `search-relevance-v1` contract now distinguishes the `blank`, `prepared`, `executed`, and `reviewed` states; only a complete review counts toward Gate 2.
- The arXiv adapter scopes DOI identifiers to the paper while retaining each DOI observation on its exact version, allowing multiple arXiv revisions to share the same DOI without a catalog conflict.
- Paper search hits now carry their source, ordered authors and scoped canonical identifiers directly from the fingerprinted `fts-v2` projection.
- Catalog connections now open only an existing database and reject file or symlink binding changes before applying writable SQLite pragmas.
- CLI date filters accept documented UTC dates with inclusive day bounds, interrupted-run repair defaults to a 24-hour stale window, and interactive ingestion confirms the exact prepared manifest while non-interactive execution still requires `--yes`.
- Catalog snapshots now use immutable descriptor-bound reads and fail closed on active WAL or SHM sidecars, so repair previews do not create corpus files.
- Catalog snapshots now materialize a validated in-memory image before exposing a revision, preventing later concurrent writes from mixing newer rows with that revision while keeping previews free of corpus sidecars.
- CLI success envelopes now validate closed, operation-specific nested data models, and terminal passage search exposes the same revisions, coverage, counters and hit provenance as JSON output.
- Exit code 4 now explicitly covers any completed ingestion run with recorded item errors, including both `partial` and `failed` statuses.
- `docs/DEVELOPMENT.md` and the old vertical-slice plan now point to the complete plan as the sole execution authority.
- `doctor` is specified as strictly read-only; recovery uses `repair interrupted-runs --yes`.
- The discovery manifest distinguishes every capture, run creation attaches its snapshots in a single transaction, and the FTS index is published as one self-describing database.
- Selected locators contribute to the digest, deferred identity evidence avoids foreign keys to future tables, and FTS publication rejects companion journals.
- Catalog commands now carry the complete graph of snapshots and unattached blobs; DTOs close the contracts for outcomes, citation provenance, search filters, index receipts, and analysis cache identity.
- Catalog attachment is bound directly to the prepared manifest; public DTOs validate their values at construction, search results bound and order their hits, and index paths are absolute.
- Architecture checks cover relative imports without a module, ignore deferred lambda bodies, and freeze the exact signatures of all declared ports.
- Passages verify their deterministic identity, text acquisition requires HTTPS, and citation results use a closed warning vocabulary.
- Both inner layers reject infrastructure imports, and all DTO tuple fields reject aliases of mutable collections.
- Pydantic remains prohibited in the domain, ports, and application except for the exact future LLM boundary validation module planned in WP-40.
- Attachment returns a stable snapshot mapping reused during replay; item failures have a closed, traceable, and idempotent contract after rollback.
- Repair materializes every selected but unprocessed record as a `recovery/interrupted` failure; item references include the snapshot, and error messages derive from a closed vocabulary.
- Runs persist their pages and ordered selection separately, allowing exact recovery without decoding a digest or confusing excluded records.
- Source connection failures have a public code distinct from timeouts and invalid responses.
- Interrupted-run recovery has closed DTOs and ports for read-only preview, locked revalidation, and an atomic mutation with a single revision increment.
- Duplicate captures are rejected, and composite foreign keys now enforce ownership across run, source, selection, item, and error.
- Every version observation retains its original selected record, making page reconstruction deterministic even after capture replay.
- `record_item` becomes the sole atomic mutation of the corpus and item; its result returns created identifiers without losing the provenance `run_id`.
- Provider and additional identifiers now explicitly declare paper or version scope, with no implicit catalog convention.
- Versioned observations also carry `origin_source_id`, preventing crossed provenance between version, snapshot, and run.
- Diagnostics revalidate catalog and artifact evidence after every phase to reject conclusions that became stale during a concurrent race.
- Public string enums use `StrEnum`, making `str(member)` identical to the canonical serialized value while retaining the same names and values.
- The catalog search projection includes source, ordered authors, categories, language, date, and collections; its logical fingerprint now covers every filterable value.
- FTS publication restores the previous canonical index after a concurrent directory mutation and never removes an ambiguous name; residue in a displaced directory remains explicitly unrepaired.
- UUID-shaped collection slugs are rejected, and the collection filter interprets a UUID value as an ID and every other value as a slug without ambiguity.
- Configuration now rejects arXiv page sizes above 100 and search limits above 50, in line with the public DTOs and adapters.
