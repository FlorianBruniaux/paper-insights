---
name: paper-research
description: Search and compare the local Paper Insights corpus with source-backed metadata, passages and citations. Use for finding papers, prior work, authors or evidence already indexed. Do not use to collect new papers or modify the corpus.
---

# Research the local paper corpus

Use only the read-only `paper-insights` MCP surface. If the MCP or its index is unavailable, report that the local research capability is not operational. Do not replace it with an external search unless the user explicitly changes the scope.

## Tool order

Use the narrowest sequence that answers the request:

1. `list_collections` when the target corpus or collection is unclear.
2. `search_papers` to identify candidates by title, metadata, author or topic.
3. `get_paper` to inspect versions, identifiers and ordered authors.
4. `search_passages` to retrieve text supporting the question.
5. `get_passage` to resolve a chosen excerpt to its full provenance.
6. `get_citation` only for a paper the user wants to cite.

## Output contract

For each supported claim, include paper title, authors, version, identifier, source URL and passage when available. State the query, filters, result limit and coverage constraints. Mark interpretation separately from text present in a paper.

Never invent a DOI, author identity, affiliation, passage or citation field. An empty result describes the local index, not all scientific literature.
