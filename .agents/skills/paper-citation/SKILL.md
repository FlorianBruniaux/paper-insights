---
name: paper-citation
description: Export a verified BibTeX, Markdown or CSL-JSON citation from a paper already stored in Paper Insights. Use when preparing sources for an article. Do not infer missing metadata or acquire a missing paper.
allowed-tools: ["Bash(uv run paper-insights *)", "Bash(paper-insights *)"]
effort: low
---

# Export a paper citation

Use the read-only Gate 2 CLI for a paper already present in the corpus. From the repository, invoke it as `uv run paper-insights`; use `paper-insights` only when the package is already installed in the active environment.

## Workflow

1. Resolve the paper with an unambiguous stored UUID, arXiv ID or DOI. Use `paper-insights search papers "<query>" --json` only when the user has not supplied a resolvable identifier; continue after exactly one paper is selected.
2. Use the version requested by the user. Otherwise let the catalogue select its current version and report the selected version from the result.
3. Run `paper-insights cite <paper> --format <bibtex|markdown|csl-json> --json`. Continue only when the result includes its paper, version, observation and source provenance.
4. Return the citation content exactly as rendered, followed by the paper ID, version ID, source, retrieval date, warnings and missing fields. This report is the completion criterion.

Ask for clarification when multiple stored papers match. Do not fill absent DOI, venue, year, author identifier or affiliation from model knowledge. Do not label a manually constructed string as an exported citation.

When the Gate 3 MCP server becomes operational, `get_citation` is the equivalent read-only tool. Do not claim that surface is available before its runtime gate passes.
