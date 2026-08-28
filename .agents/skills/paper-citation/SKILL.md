---
name: paper-citation
description: Export a verified BibTeX, Markdown or CSL-JSON citation from a paper already stored in Paper Insights. Use when preparing sources for an article. Do not infer missing metadata or acquire a missing paper.
---

# Export a paper citation

Use the read-only `get_citation` MCP tool for a paper already present in the corpus.

## Workflow

1. Resolve the paper with `search_papers` or an unambiguous stored identifier.
2. Use the version requested by the user. Otherwise use the catalogue's current version and state which version was selected.
3. Call `get_citation` with `bibtex`, `markdown` or `csl-json`.
4. Return the exact citation, paper id, version id, source, retrieval date and reported missing fields.

Ask for clarification when multiple stored papers match. Do not fill absent DOI, venue, year, author identifier or affiliation from model knowledge. Do not label a manually constructed string as an exported citation.

The MCP is planned but not implemented in the initial scaffold. Until `get_citation` exists, stop after reporting that citation export is unavailable.
