---
name: paper-research
description: Search and compare the local Paper Insights corpus with source-backed metadata and passages. Use for finding papers, prior work, authors or evidence already indexed. Use paper-citation for a standalone citation export and paper-ingest for corpus mutation.
allowed-tools: ["Bash(uv run paper-insights *)", "Bash(paper-insights *)"]
effort: medium
---

# Research the local paper corpus

Use the read-only Gate 2 CLI while the target MCP server remains unavailable. From the repository, invoke it as `uv run paper-insights`; use `paper-insights` only when the package is already installed in the active environment. Do not replace local-corpus research with an external search unless the user explicitly changes the scope.

## CLI order

Use the narrowest sequence that answers the request:

1. Run `paper-insights doctor --json`. Continue only when the catalogue and published search index are readable and revision-aligned.
2. Run `paper-insights collections list --json` when the requested collection is unclear. Continue after reporting the exact collection scope or the absence of a matching collection.
3. Run `paper-insights search papers "<query>" --json` with only the requested filters. Continue after recording the applied query, filters, limit, catalogue revision, index revision and coverage.
4. Run `paper-insights search passages "<query>" --json` when the answer needs textual support. A passage is usable only when its paper, version, observation and artifact provenance are present.
5. If the user also needs one selected citation, hand that paper to `paper-citation`. A standalone export request belongs directly to that skill.

When the Gate 3 MCP server becomes operational, the equivalent read-only order is `list_collections`, `search_papers`, `get_paper`, `search_passages`, `get_passage`, then `get_citation`. Do not claim that surface is available before its runtime gate passes.

## Output contract

For each supported claim, include paper title, authors, version, identifier, source URL and passage when available. State the query, filters, result limit and coverage constraints. Mark interpretation separately from text present in a paper.

Never invent a DOI, author identity, affiliation, passage or citation field. An empty result describes the local index, not all scientific literature. Completion requires every conclusion to distinguish observed metadata, paper text and interpretation.
