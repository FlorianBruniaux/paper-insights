# Foundation Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest a fixed arXiv response into SQLite, search its titles and abstracts, and export a source-backed BibTeX citation through CLI and MCP read-only interfaces.

**Architecture:** Domain dataclasses and protocols stay independent from SQLAlchemy, HTTP and MCP. An application service coordinates a provider, an artifact store and a transactional catalog. A separately published SQLite FTS5 index serves CLI and MCP reads.

**Tech Stack:** Python 3.12, uv, Pydantic 2, httpx, SQLAlchemy 2, Alembic, SQLite FTS5, Typer, MCP Python SDK, pytest, respx, Ruff and mypy.

**Spec:** `docs/superpowers/specs/2026-08-28-paper-insights-design.md`

## Global Constraints

- Python 3.12 minimum.
- SQLite is the only database in this tranche.
- Tests never access the network.
- External responses and MCP payloads are bounded.
- Preview performs no corpus write.
- Every artifact has a relative path, size, media type and SHA-256.
- MCP is read-only and rejects unknown arguments.
- Changelog and relevant docs change with behavior.

---

### Task 1: Package, configuration and paths

**Files:**
- Create: `src/paper_insights/__init__.py`
- Create: `src/paper_insights/config.py`
- Create: `src/paper_insights/paths.py`
- Create: `src/paper_insights/cli.py`
- Create: `tests/test_config.py`
- Create: `tests/test_paths.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: environment variables prefixed by `PAPER_INSIGHTS_` and optional TOML settings.
- Produces: `Settings.load(*, config_path: Path | None, cli_overrides: Mapping[str, object]) -> Settings` and `DataPaths.from_root(root: Path) -> DataPaths`.

- [ ] **Step 1: Write failing tests for strict configuration**

```python
def test_unknown_toml_key_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[paper_insights]\ndata_rooot = "./data"\n')
    with pytest.raises(ValidationError):
        Settings.load(config_path=config, cli_overrides={})
```

- [ ] **Step 2: Run the focused configuration test**

Run: `uv run pytest tests/test_config.py::test_unknown_toml_key_is_rejected -v`

Expected: FAIL because `Settings` does not exist.

- [ ] **Step 3: Implement immutable paths and strict settings**

```python
@dataclass(frozen=True, slots=True)
class DataPaths:
    root: Path
    artifacts: Path
    catalog_database: Path
    search_database: Path

    @classmethod
    def from_root(cls, root: Path) -> "DataPaths":
        resolved = root.expanduser().resolve(strict=False)
        return cls(
            root=resolved,
            artifacts=resolved / "artifacts",
            catalog_database=resolved / "catalog.sqlite3",
            search_database=resolved / ".search" / "search-v1.sqlite3",
        )
```

Configure Pydantic with `extra="forbid"`, parse TOML before environment and apply non-null CLI overrides last.

- [ ] **Step 4: Add `paper-insights doctor --json` without writes**

The command reports Python version, configured data root, catalogue presence and index presence. It does not create the root or probe the network.

- [ ] **Step 5: Run configuration tests and static checks**

Run: `uv run pytest tests/test_config.py tests/test_paths.py -v`

Expected: PASS.

Run: `uv run ruff check src/paper_insights tests/test_config.py tests/test_paths.py`

Expected: PASS.

- [ ] **Step 6: Commit the task**

```bash
git add pyproject.toml src/paper_insights/__init__.py src/paper_insights/config.py src/paper_insights/paths.py src/paper_insights/cli.py tests/test_config.py tests/test_paths.py
git commit -m "feat: add strict configuration foundation"
```

### Task 2: Domain model, catalog and migrations

**Files:**
- Create: `src/paper_insights/domain/models.py`
- Create: `src/paper_insights/catalog/models.py`
- Create: `src/paper_insights/catalog/repository.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/0001_initial_catalog.py`
- Create: `tests/catalog/test_migrations.py`
- Create: `tests/catalog/test_repository.py`

**Interfaces:**
- Consumes: `DataPaths.catalog_database`, `PaperRecord`, `PaperVersionRecord` and ordered `AuthorRecord` values.
- Produces: `CatalogRepository.upsert_record(record: NormalizedPaperRecord, run_id: str) -> UpsertOutcome` and `CatalogRepository.get_paper(paper_id: str) -> PaperView | None`.

- [ ] **Step 1: Write failing migration and idempotence tests**

```python
def test_same_source_version_is_idempotent(repository: CatalogRepository, record: NormalizedPaperRecord) -> None:
    first = repository.upsert_record(record, run_id="run-1")
    second = repository.upsert_record(record, run_id="run-2")
    assert first.status == "created"
    assert second.status == "unchanged"
    assert repository.count_papers() == 1
    assert repository.count_versions() == 1
```

- [ ] **Step 2: Run the focused repository test**

Run: `uv run pytest tests/catalog/test_repository.py::test_same_source_version_is_idempotent -v`

Expected: FAIL because the repository does not exist.

- [ ] **Step 3: Define domain records without ORM imports**

```python
@dataclass(frozen=True, slots=True)
class NormalizedPaperRecord:
    source_id: str
    source_paper_id: str
    source_version_id: str
    title: str
    abstract: str
    authors: tuple[AuthorRecord, ...]
    categories: tuple[str, ...]
    submitted_at: datetime | None
    retrieved_at: datetime
    source_url: str
```

- [ ] **Step 4: Create the initial Alembic migration**

Implement the Phase 1 subset of `papers`, `paper_versions`, `external_identifiers`, `authors`, `paper_authors`, `sources`, `artifacts`, `ingestion_runs` and `collection_errors`. Enable SQLite foreign keys on every connection.

- [ ] **Step 5: Implement transactional upsert**

Use `(scheme="arxiv", value=source_paper_id)` to resolve the paper and `(source_id, source_version_id)` to resolve the version. Preserve author order and do not merge authors by normalized name.

- [ ] **Step 6: Run migration and repository tests**

Run: `uv run pytest tests/catalog -v`

Expected: PASS, including migration from an empty SQLite file.

- [ ] **Step 7: Commit the task**

```bash
git add alembic.ini alembic src/paper_insights/domain src/paper_insights/catalog tests/catalog
git commit -m "feat: add versioned paper catalog"
```

### Task 3: arXiv fixtures, parser and preview

**Files:**
- Create: `src/paper_insights/providers/base.py`
- Create: `src/paper_insights/providers/arxiv.py`
- Create: `tests/fixtures/arxiv/search-three-entries.xml`
- Create: `tests/providers/test_arxiv_parser.py`
- Create: `tests/providers/test_arxiv_client.py`

**Interfaces:**
- Consumes: `DiscoveryQuery(query: str, categories: tuple[str, ...], limit: int)`.
- Produces: `ArxivProvider.preview(query: DiscoveryQuery) -> DiscoveryPreview` and `ArxivProvider.iter_records(query: DiscoveryQuery) -> Iterator[RawPaperRecord]`.

- [ ] **Step 1: Save a redacted, fixed XML fixture with three entries**

The fixture contains two distinct papers and a newer version of the first paper. It preserves namespaces, multiple authors, categories and one DOI. Record the fixture source date in an XML comment.

- [ ] **Step 2: Write failing parser assertions**

```python
def test_parser_preserves_versions_and_author_order(fixture_bytes: bytes) -> None:
    records = parse_arxiv_feed(fixture_bytes, retrieved_at=FIXED_NOW)
    assert [record.source_version_id for record in records] == [
        "2608.00001v1",
        "2608.00002v1",
        "2608.00001v2",
    ]
    assert [author.raw_name for author in records[0].authors] == ["Ada Example", "Lin Example"]
```

- [ ] **Step 3: Run parser test**

Run: `uv run pytest tests/providers/test_arxiv_parser.py -v`

Expected: FAIL because the parser does not exist.

- [ ] **Step 4: Implement query validation, parser and bounded client**

Accept limits from 1 to 100. Configure httpx timeout, maximum response bytes and explicit user agent. Parse XML with the standard library and reject malformed or oversized payloads with stable provider errors.

- [ ] **Step 5: Test HTTP behavior through respx**

Assert encoded query parameters, timeout translation, 429 handling, malformed XML handling and absence of retries for non-transient 4xx responses.

- [ ] **Step 6: Run provider tests**

Run: `uv run pytest tests/providers -v`

Expected: PASS with no external request.

- [ ] **Step 7: Commit the task**

```bash
git add src/paper_insights/providers tests/fixtures/arxiv tests/providers
git commit -m "feat: add bounded arxiv discovery"
```

### Task 4: Artifact store and ingestion service

**Files:**
- Create: `src/paper_insights/artifacts/store.py`
- Create: `src/paper_insights/ingestion/models.py`
- Create: `src/paper_insights/ingestion/service.py`
- Create: `tests/artifacts/test_store.py`
- Create: `tests/ingestion/test_service.py`
- Modify: `src/paper_insights/cli.py`

**Interfaces:**
- Consumes: `PaperProvider`, `CatalogRepository`, `ArtifactStore`, `DiscoveryQuery` and a preview digest.
- Produces: `IngestionService.preview(query) -> DiscoveryPreview` and `IngestionService.run(query, preview_digest) -> IngestionReport`.

- [ ] **Step 1: Write failing atomic publication test**

```python
def test_artifact_is_published_with_hash(store: ArtifactStore, tmp_path: Path) -> None:
    artifact = store.publish(
        paper_id="paper-1",
        version="2608.00001v1",
        kind="source_response",
        media_type="application/atom+xml",
        chunks=[b"<feed />"],
    )
    assert artifact.sha256 == hashlib.sha256(b"<feed />").hexdigest()
    assert (tmp_path / artifact.relative_path).read_bytes() == b"<feed />"
```

- [ ] **Step 2: Run artifact test**

Run: `uv run pytest tests/artifacts/test_store.py -v`

Expected: FAIL because `ArtifactStore` does not exist.

- [ ] **Step 3: Implement private temporary writes and path confinement**

Use a sibling temporary file with mode `0600`, enforce maximum bytes while writing, call `flush` and `os.fsync`, validate the resolved final parent, then call `os.replace`.

- [ ] **Step 4: Write ingestion tests for preview and partial success**

Assert that preview leaves `data_root` absent, identical records become unchanged, a bad second record creates one `collection_error`, and the final report status is `partial`.

- [ ] **Step 5: Implement run lifecycle and CLI confirmation**

Create the run before iterating, commit one record per transaction, update exact counters and publish the final status. `ingest` prints the preview and requires confirmation unless the source is one explicit identifier or `--yes` is present.

- [ ] **Step 6: Run ingestion tests**

Run: `uv run pytest tests/artifacts tests/ingestion -v`

Expected: PASS.

- [ ] **Step 7: Commit the task**

```bash
git add src/paper_insights/artifacts src/paper_insights/ingestion src/paper_insights/cli.py tests/artifacts tests/ingestion
git commit -m "feat: add idempotent ingestion runs"
```

### Task 5: FTS5 search and citations

**Files:**
- Create: `src/paper_insights/search/models.py`
- Create: `src/paper_insights/search/sqlite_fts.py`
- Create: `src/paper_insights/search/service.py`
- Create: `src/paper_insights/citations/service.py`
- Create: `tests/search/test_index.py`
- Create: `tests/search/test_service.py`
- Create: `tests/citations/test_service.py`
- Modify: `src/paper_insights/cli.py`

**Interfaces:**
- Consumes: read-only catalog views and current paper versions.
- Produces: `SearchService.search_papers(query: SearchQuery) -> tuple[SearchHit, ...]`, `get_passage(passage_id: str) -> PassageView` and `CitationService.render(paper_id: str, format: CitationFormat) -> CitationResult`.

- [ ] **Step 1: Write failing atomic index test**

```python
def test_failed_rebuild_preserves_active_index(index: SQLiteFtsIndex, seeded_catalog: Path) -> None:
    first = index.build(seeded_catalog)
    with pytest.raises(IndexBuildError):
        index.build(seeded_catalog, fail_after_documents=1)
    assert index.status().generation_id == first.generation_id
```

- [ ] **Step 2: Run search tests**

Run: `uv run pytest tests/search/test_index.py -v`

Expected: FAIL because the index does not exist.

- [ ] **Step 3: Implement deterministic passages and FTS publication**

Create one abstract passage per current version in P1. Hash the version id, artifact hash, ordinal and normalized text. Build a sibling database, run `quick_check`, write a generation receipt and publish with `os.replace`.

- [ ] **Step 4: Implement parameterized read-only search**

Open the active database with `mode=ro&immutable=1`, enable `query_only`, sanitize user terms and cap limits. Return rank, BM25 score, bounded excerpt and stable identifiers.

- [ ] **Step 5: Implement BibTeX and Markdown citations**

Use catalog metadata only. Escape BibTeX values deterministically, preserve author order and return a tuple of missing field names.

- [ ] **Step 6: Run search and citation tests**

Run: `uv run pytest tests/search tests/citations -v`

Expected: PASS.

- [ ] **Step 7: Commit the task**

```bash
git add src/paper_insights/search src/paper_insights/citations src/paper_insights/cli.py tests/search tests/citations
git commit -m "feat: add source-backed local search"
```

### Task 6: Closed-world MCP facade

**Files:**
- Create: `src/paper_insights/mcp/server.py`
- Create: `tests/mcp/test_contract.py`
- Create: `tests/mcp/test_payloads.py`
- Modify: `src/paper_insights/cli.py`

**Interfaces:**
- Consumes: `SearchService`, `CitationService` and read-only catalog queries.
- Produces: six tools named in `docs/specs/SEARCH-AND-MCP.md` and `paper-insights mcp serve`.

- [ ] **Step 1: Write failing closed-world contract test**

```python
def test_tools_are_exactly_read_only(server: MCPServer) -> None:
    tools = {tool.name: tool for tool in server.list_tools()}
    assert set(tools) == {
        "list_collections",
        "search_papers",
        "get_paper",
        "search_passages",
        "get_passage",
        "get_citation",
    }
    assert all(tool.annotations.readOnlyHint for tool in tools.values())
    assert all(not tool.annotations.destructiveHint for tool in tools.values())
```

- [ ] **Step 2: Run MCP contract test**

Run: `uv run --extra mcp pytest tests/mcp/test_contract.py -v`

Expected: FAIL because the MCP server does not exist.

- [ ] **Step 3: Implement argument validation before service calls**

Reject unknown tool names, extra keys, booleans passed as limits, queries outside 1 to 500 characters, limits outside 1 to 20 and malformed UUID or SHA-256 identifiers.

- [ ] **Step 4: Implement payload clipping and total size gates**

Clip excerpts at 1,500 characters, structured bodies below 24 Kio and total serialized responses below 64 Kio. Set `truncated=true` when entries are removed.

- [ ] **Step 5: Assert absence of mutation paths**

Monkeypatch write-oriented repository and artifact methods to raise if called. Exercise every MCP tool and assert no patched method executes.

- [ ] **Step 6: Run MCP tests**

Run: `uv run --extra mcp pytest tests/mcp -v`

Expected: PASS.

- [ ] **Step 7: Commit the task**

```bash
git add src/paper_insights/mcp src/paper_insights/cli.py tests/mcp
git commit -m "feat: expose read-only paper research mcp"
```

### Task 7: End-to-end fixture, CI and release gate

**Files:**
- Create: `tests/integration/test_arxiv_vertical_slice.py`
- Create: `.github/workflows/ci.yml`
- Create: `docs/DEVELOPMENT.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: all public interfaces produced by Tasks 1 through 6.
- Produces: one offline acceptance test and a CI gate for Python 3.12.

- [ ] **Step 1: Write the full vertical-slice test**

```python
def test_arxiv_fixture_to_search_and_citation(app: TestApplication) -> None:
    first = app.ingest_fixture("search-three-entries.xml")
    second = app.ingest_fixture("search-three-entries.xml")
    assert first.created_count == 3
    assert second.unchanged_count == 3
    assert app.catalog.count_papers() == 2
    assert app.catalog.count_versions() == 3
    app.search.build()
    hits = app.search.search_papers(SearchQuery(text="agent evaluation", limit=10))
    citation = app.citations.render(hits[0].paper_id, CitationFormat.BIBTEX)
    assert citation.paper_id == hits[0].paper_id
    assert "@" in citation.content
```

- [ ] **Step 2: Run the integration test**

Run: `uv run --extra mcp pytest tests/integration/test_arxiv_vertical_slice.py -v`

Expected: PASS without network.

- [ ] **Step 3: Add CI checks**

Configure checkout, Python 3.12, uv cache, `uv sync --all-extras --dev`, Ruff check, Ruff format check, mypy and pytest with coverage threshold 90. Grant only `contents: read`.

- [ ] **Step 4: Document verified commands and current limitations**

Update README only with commands that pass locally. Keep PDF extraction, watchlists, LLM analysis and author enrichment marked unavailable.

- [ ] **Step 5: Run the full local gate**

Run: `uv run ruff check .`

Expected: PASS.

Run: `uv run ruff format --check .`

Expected: PASS.

Run: `uv run mypy src`

Expected: PASS.

Run: `uv run --extra mcp pytest --cov=paper_insights --cov-report=term-missing`

Expected: PASS with at least 90 percent branch-aware coverage.

- [ ] **Step 6: Commit the release gate**

```bash
git add .github/workflows/ci.yml tests/integration docs/DEVELOPMENT.md README.md CHANGELOG.md
git commit -m "test: gate the arxiv vertical slice"
```
