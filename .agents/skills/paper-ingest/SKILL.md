---
name: paper-ingest
description: Preview and ingest papers from supported sources into the local Paper Insights corpus. Use for adding an arXiv paper or collecting a query. Do not use for read-only corpus research, citation-only exports or watchlists, which are not operational yet.
allowed-tools: ["Bash(uv run paper-insights *)", "Bash(paper-insights *)"]
effort: low
---

# Ingest scientific papers

Keep ingestion in the main session because it can access the network and mutate the local corpus.

From the repository, invoke the CLI as `uv run paper-insights`. Use `paper-insights` only when the package is already installed in the active environment.

## Workflow

1. Run `paper-insights doctor --json`. Continue only when required checks pass; otherwise report the closed failure or `UNKNOWN` without exposing configuration values.
2. Run `paper-insights discover arxiv ... --json`, or `paper-insights ingest arxiv ... --json` without `--yes`, for the exact selectors requested. Continue only when the preview reports the canonical query, selected identifiers, exclusions, discovery errors and requested artifacts.
3. For one explicit paper already requested by the user, execute the corresponding ingestion after the successful preview. For a query, category, author or multiple identifiers, wait for explicit confirmation of that preview and then repeat the same ingestion with `--yes`.
4. Report the run ID plus created, updated, unchanged and failed counts. Completion requires every recorded failure to include its public code and source identifier.
5. Run `paper-insights doctor --json` again. Finish by reporting corpus health and whether the search index needs rebuilding.

Do not edit the corpus directly, bypass preview, broaden the query or download PDFs unless the preview and user request include them. A preview does not prove that anything was ingested.
