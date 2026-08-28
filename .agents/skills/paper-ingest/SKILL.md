---
name: paper-ingest
description: Preview and ingest papers from supported sources into the local Paper Insights corpus. Use for adding an arXiv paper, collecting a query or running a watchlist. Do not use for read-only corpus research.
---

# Ingest scientific papers

Keep ingestion in the main session because it can access the network and mutate the local corpus.

## Workflow

1. Run `paper-insights doctor --json`. Stop on failed required checks without exposing configuration values.
2. Run the requested `discover` or `ingest` command in preview mode with `--json`.
3. Report source, canonical query, selected identifiers, exclusions, discovery errors, requested artifacts and output root.
4. For one explicit paper already requested by the user, execute the corresponding ingestion after a successful preview.
5. For a query, category, author, watchlist or multiple identifiers, wait for explicit confirmation. Repeat the same command with `--yes` only after confirmation.
6. Report run id, created, updated, unchanged and failed counts. List each failure code and source identifier.
7. Run the read-only status command and report whether the catalogue needs a search-index rebuild.

Do not edit the corpus directly, bypass preview, broaden the query or download PDFs unless the preview and user request include them. A preview does not prove that anything was ingested.

The CLI is planned but not implemented in the initial scaffold. Until `paper-insights doctor` exists, stop after reporting that the ingestion workflow is unavailable.
