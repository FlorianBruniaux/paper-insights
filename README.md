# Paper Insights

<table>
  <tr>
    <td width="64">
      <a href="https://www.florian.bruniaux.com/about/?utm_source=github&amp;utm_medium=readme&amp;utm_campaign=paper-insights"><img src="https://cc.bruniaux.com/author.png" width="56" height="56" alt="Florian Bruniaux" /></a>
    </td>
    <td>
      <strong><a href="https://www.florian.bruniaux.com/about/?utm_source=github&amp;utm_medium=readme&amp;utm_campaign=paper-insights">Florian BRUNIAUX</a></strong> &middot; AI Founding Engineer @ <a href="https://methode-aristote.fr/">Méthode Aristote</a><br />
      13 years from developer to CTO / VP Eng &middot; <a href="https://www.florian.bruniaux.com/blog/?utm_source=github&amp;utm_medium=readme&amp;utm_campaign=paper-insights">Blog &#8599;</a> &middot; <a href="https://www.florian.bruniaux.com/projects/?utm_source=github&amp;utm_medium=readme&amp;utm_campaign=paper-insights">Projects &#8599;</a>
    </td>
  </tr>
</table>

[![CI](https://github.com/FlorianBruniaux/paper-insights/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/FlorianBruniaux/paper-insights/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![SQLite FTS5](https://img.shields.io/badge/search-SQLite%20FTS5-003B57)](https://www.sqlite.org/fts5.html)
[![Status: Experimental](https://img.shields.io/badge/status-experimental-orange)](#project-status)

Build a local scientific literature corpus with traceable sources. Discover and ingest arXiv metadata, search titles and abstracts with SQLite FTS5, organize papers into collections, and export citations from stored bibliographic observations.

Paper Insights is the scientific literature companion to [YouTube Video Insights](https://github.com/FlorianBruniaux/youtube-video-insights), which covers video transcripts and timestamped evidence. Each project keeps its own corpus and provenance. Cross-corpus federation is planned.

![Paper Insights workflow: preview arXiv metadata, confirm ingestion, preserve the SQLite catalog and source snapshots, index titles and abstracts with FTS5, search papers and passages, and export BibTeX, Markdown, or CSL-JSON citations. Human relevance review is pending; later features are marked as planned.](docs/assets/paper-insights-workflow.png)

The infographic shows the current CLI workflow and separates planned features in the footer. Human relevance review remains pending. The branching workflow is available as [Mermaid source](docs/assets/paper-insights-workflow.mmd).

## Project status

The `main` branch contains the Gate 0 contracts, Gate 1 local foundation, prepared arXiv ingestion, FTS5 search, collections, citations, and the Gate 2 CLI. These behaviors pass tests against local fixtures without network access.

Gate 2 remains blocked on human relevance review, currently **0 of 30 reviews completed**. A candidate corpus of 120 real arXiv metadata records and its FTS5 index ran 30 queries with complete coverage: 25 placed at least one expected paper in the top five, with no raw misses across the six must-find queries. These measurements do not replace the 30 human verdicts or final gate approval.

The MCP server, watchlists, full-text acquisition, LLM analysis, enriched author identity, and federation remain target contracts. **This project is experimental.**

## Goals

- Search for papers by topic, author, category, or identifier.
- Monitor queries and categories for new publications.
- Preserve metadata, versions, artifacts, and their provenance.
- Index titles, abstracts, and authorized full text with SQLite FTS5.
- Produce analyses linked to the passages that support them.
- Export verifiable citations for articles.
- Enrich author records with ORCID, OpenAlex, and institutional pages.
- Expose a local, read-only MCP interface.

## Initial boundaries

- arXiv is the first source; the domain model remains source-independent.
- The initial version is local and single-user.
- SQLite serves the storage and search needs until measurements justify PostgreSQL or Redis.
- PDF analysis follows reliable metadata and abstract collection.
- A name alone never confirms a LinkedIn identity match.
- LinkedIn scraping is out of scope.

## Target architecture

```text
providers -> application services -> domain + ports
adapters  -> application ports
CLI / MCP -> application services
bootstrap -> interfaces + services + adapters
```

This simplified view shows dependency direction. The relational catalog stores entities and provenance. A separate FTS5 index contains reproducible passages. Analyses reference passage identifiers and the fingerprint of the source artifact.

## Documentation

| Document | Purpose |
| --- | --- |
| [Vision](docs/VISION.md) | Problem, users, and intended outcomes |
| [Architecture](docs/ARCHITECTURE.md) | Components, dependencies, and data flows |
| [Roadmap](docs/ROADMAP.md) | Phases and exit criteria |
| [Product specification](docs/specs/PRODUCT.md) | Use cases and requirements |
| [Data model](docs/specs/DATA-MODEL.md) | Entities, identifiers, and provenance |
| [Ingestion](docs/specs/INGESTION.md) | Discovery, recovery, and idempotency |
| [Application ports](docs/specs/PORTS.md) | Synchronous signatures and frozen DTOs |
| [Search and MCP](docs/specs/SEARCH-AND-MCP.md) | FTS5, citations, and MCP tools |
| [Human relevance review](docs/benchmarks/SEARCH-RELEVANCE-GATE.md) | Offline Gate 2 protocol |
| [Capability and evidence matrix](docs/evidence/capability-matrix.json) | Verifiable status, exclusions, claim limits, and next evaluations |
| [Evidence governance plan](docs/superpowers/plans/2026-09-05-evidence-governance-optimization.md) | Cross-cutting extension to the complete plan |
| [Watchlists](docs/specs/WATCHLISTS.md) | Cursors, overlap, finalization, and digests |
| [Analysis](docs/specs/ANALYSIS.md) | Full text, passages, cache, claims, and evidence |
| [Author identity](docs/specs/AUTHOR-IDENTITY.md) | Observations, reversible decisions, and manual LinkedIn confirmation |
| [Federation](docs/specs/FEDERATION.md) | Cross-corpus contract and partial coverage |
| [Python and SQLite decision](docs/decisions/ADR-0001-python-sqlite.md) | Initial technical choices |
| [Observations and provenance decision](docs/decisions/ADR-0002-versioned-observations-and-provenance.md) | Version authority, snapshots, and evidence |
| [Manifest and publication decision](docs/decisions/ADR-0003-preview-manifest-and-publication.md) | Confirmed batches, revisions, and atomic publication |
| [Modular monolith decision](docs/decisions/ADR-0004-modular-monolith-ports.md) | Layers, ports, and dependencies |

## Agent configuration

- `AGENTS.md` defines shared rules for Codex and other agents.
- `CLAUDE.md` adds Claude Code conventions.
- `.claude/agents/` contains specialized roles.
- `.agents/skills/` contains portable workflows.
- `.claude/skills` points to the same directory to avoid divergent copies.
- `.claude/hooks/` contains tested local guards.

## Scaffold validation

```bash
python3 scripts/validate_project.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

These commands do not install dependencies or access the network.

## Explore the ecosystem

Related tools for the wider research and publishing workflow:

| Project | Use it for |
| --- | --- |
| [YouTube Video Insights](https://github.com/FlorianBruniaux/youtube-video-insights) | Build a local corpus of video transcripts, search timestamped evidence, and export cited research dossiers. Use it alongside Paper Insights when a topic spans papers and talks. |
| [Claude Code Ultimate Guide](https://github.com/FlorianBruniaux/claude-code-ultimate-guide) | Learn agent workflows, skills, hooks, and MCP usage for research and development. |
| [Google Search Console MCP](https://github.com/FlorianBruniaux/google-search-console-mcp) | Query Search Console and analytics when measuring the visibility of articles published from your research. |

These projects run independently. The links describe complementary uses; they do not imply an implemented Paper Insights integration.

[Browse Florian's open-source projects](https://github.com/FlorianBruniaux#open-source-galaxy) or visit the [project portfolio](https://www.florian.bruniaux.com/projects/?utm_source=github&utm_medium=readme&utm_campaign=paper-insights).

## Initial official sources

- [arXiv Computer Science help](https://info.arxiv.org/help/cs/index.html)
- [Recent artificial intelligence papers](https://arxiv.org/list/cs.AI/recent)

## License

The source code is published in the public [FlorianBruniaux/paper-insights](https://github.com/FlorianBruniaux/paper-insights) repository. No public license has been granted at this stage.
