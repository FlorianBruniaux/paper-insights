# Paper Insights workflow image

## Provenance

- Created: 2026-09-22.
- Tool: built-in `imagegen`; the tool did not expose a model version.
- Mode: adapt the reference infographic into a new project asset.
- Reference: [YouTube Video Insights workflow](https://github.com/FlorianBruniaux/youtube-video-insights/blob/main/docs/assets/yt-insights-workflow.jpg).
- Reference Git blob: `a4bb142cecdf29a665a2f95595fc489b8028f0b2`.
- Reference SHA-256: `ebbc89e3eeda54c5f26f1d9c0443436d323f474a71cc2963c2f51211f8d2a18d`.
- Output: [paper-insights-workflow.png](paper-insights-workflow.png), 1672 x 941 pixels.
- Output SHA-256: `7d575de6150b23fd3b85ae95574f8ec47b369f3a0cb83a70c3d04e7484148fb6`.
- Editable workflow: [paper-insights-workflow.mmd](paper-insights-workflow.mmd).
- Claim sources: [capability matrix](../evidence/capability-matrix.json), [product specification](../specs/PRODUCT.md), and the CLI help output.
- Visual review: six current stages, English labels, exact CLI command, pending human relevance review, and planned features kept separate.

## Generation prompt

```text
Use case: infographic-diagram.
Create a new Paper Insights adaptation of the supplied YouTube Video Insights workflow infographic. The attached image is a visual style and composition reference, not factual content to reuse. Preserve its near-black navy background, crisp electric-blue and cyan outline icons, bright white readable sans-serif typography, horizontal six-stage layout, thin light-gray arrows, generous spacing, understated rounded badges, terminal panel, and 16:9 landscape composition. Make a polished high-resolution GitHub README infographic in English.

Title centered at the top, large and bold: "paper-insights"
Subtitle: "Turn scientific papers into a local, source-backed research corpus"

Six equally spaced stages from left to right, connected by single directional arrows. Each has one large outline icon, a blue uppercase heading, and exactly two short white caption lines:
1. Icon: scientific paper with a magnifying glass.
   Heading: "DISCOVER"
   Captions: "arXiv metadata" / "Preview only"
2. Icon: person approving a checklist, cyan check mark.
   Heading: "CONFIRM"
   Captions: "Review exact selection" / "Approve ingestion"
3. Icon: database cylinder with a source document.
   Heading: "STORE"
   Captions: "SQLite catalog" / "Source snapshots"
4. Icon: document rows flowing into a compact search index.
   Heading: "INDEX"
   Captions: "Titles + abstracts" / "SQLite FTS5"
5. Icon: magnifying glass over result rows.
   Heading: "SEARCH"
   Captions: "Papers + passages" / "Collection filters"
6. Icon: bibliography page and quotation mark, with a small export arrow.
   Heading: "CITE"
   Captions: "BibTeX + Markdown" / "CSL-JSON"

Below the six stages, a thin centered provenance line:
"Source identifiers • Versioned metadata • Traceable citations"

Below that, a wide understated amber status strip, readable but secondary:
"EXPERIMENTAL • Human relevance review pending"

Then a terminal panel in the same style as the reference, showing exactly:
"uv run paper-insights --help"

Below the terminal, four pill-shaped badges:
"LOCAL-FIRST"
"CONFIRMED INGESTION"
"SOURCE-BACKED"
"NO LLM FOR SEARCH"

A separate muted footer row labeled exactly:
"PLANNED: MCP • watchlists • full text • LLM analysis • author identity • federation"
This is a roadmap row, visually separated from the current six-stage flow. Do not connect it as a currently available feature. MCP is not implemented, and there is no web app.

Bottom centered URL:
"github.com/FlorianBruniaux/paper-insights"

Constraints: all text must be sharp and spelled exactly as specified; large enough to read within a GitHub README. Preserve strong contrast and roomy alignment. Use only the text listed above. No fake UI screenshots, no YouTube logo, no paper PDF-download promise, no brain icon suggesting LLM-powered search, no automatic ingestion loops, no invented metrics, no watermarks, no extra labels. Do not reuse the YouTube project's command or feature claims. Keep the layout visually close to the reference while making all icons and labels relevant to scientific literature.
```

