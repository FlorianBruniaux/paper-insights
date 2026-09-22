# Critical source review

**Status:** Accepted product requirement; runtime not implemented.
**Design revision:** 1, 2026-09-22.
**Delivery:** Phase 5, WP-40 extension, after the existing prerequisite gates.

## Purpose

Help a reader choose which papers deserve attention for a stated research
question. A search match, recent publication, or faithful summary does not
establish scientific quality or editorial value.

The review must distinguish topic relevance, contribution, and evidential
support. It produces an explained recommendation, not a scientific truth
certificate. Repository publication does not activate this workflow.

## Two review stages

| Stage | Permitted input | Permitted conclusion |
| --- | --- | --- |
| Preliminary screening | Exact title, abstract, and bibliographic observation | Apparent relevance, stated contribution, and questions to investigate |
| Critical reading | Authorized extracted text and stable evidence passages | Bounded findings about the methods, results, and limitations actually inspected |

An abstract-only review cannot establish methodological soundness, prove a
claim, or declare that a paper adds nothing to the literature. Missing full
text is an evidence limitation, not a negative quality signal. Partial
extraction must list the inspected sections and omissions; it must never be
presented as a complete reading.

Screening may inform a discovery preview. It does not change the approved
`PreparedDiscovery` or silently prevent ingestion. Critical reading belongs
after source acquisition and passage extraction, before editorial selection
or synthesis. No review runs as a side effect of ordinary search or citation.

## Paper-specific rubric

Each dimension records a finding, supporting passages, uncertainty, and what
would resolve a missing observation. Use `supported`, `mixed`, or `UNKNOWN`
for evidential support, without collapsing the dimensions into one score.

| Dimension | Review question | Evidence boundary |
| --- | --- | --- |
| Relevance | Does the paper address the user's question and audience? | Relevance is separate from methodological quality |
| Contribution | What does it add relative to the explicitly compared sources? | Novelty outside that comparison set remains `UNKNOWN` |
| Methods | Do the design, baselines, and evaluation support the stated conclusion? | Check only accessible methods and results; record missing controls |
| Claims | Do the conclusions stay within the reported evidence? | Separate observations, author claims, and reviewer inferences |
| Reproducibility | Are data, code, protocols, and parameters available or described? | A linked artifact is not a verified reproduction |
| Editorial value | Does it add useful evidence, explanation, or a counterexample? | Replications and negative results can be useful without novelty |

Publication volume, venue, citation count, affiliation, author reputation, and
Hugging Face visibility are not sufficient grounds for a quality verdict.
Suspected duplication requires identified comparators and cited overlap.
Critique the work, not the author or their presumed intent.

## Recommendations and selection decisions

The proposed recommendation vocabulary is `retain`, `defer`,
`exclude_from_selection`, and `insufficient_evidence`. These are design terms,
not available CLI values.

- `retain`: recommend the source for this topic and use, with its limitations.
- `defer`: a concrete missing check prevents a useful decision.
- `exclude_from_selection`: recommend omitting it from this named selection,
  with reasons and evidence. This does not remove it from the corpus.
- `insufficient_evidence`: the input cannot support a recommendation. This is
  the required result when the evidence needed for the decision is unavailable.

Keep model recommendations separate from human selection events. The first
release is advisory: no automatic deletion, hidden search result, acquisition,
collection removal, or approved-selection change. A human may accept or
override a recommendation; both events remain visible with their reasons.
Review and selection changes are explicit mutations outside the read-only MCP.

Search remains able to find excluded sources. Reviewed exports must identify
retained, deferred, excluded, and unreviewed items, plus the decision history.
An exclusion applies only to its topic, audience, and selection revision.

## Evidence and review history

A future versioned, closed review record must bind:

- paper, version, observation, input artifact hashes, inspected passage IDs,
  review stage, extraction coverage, and missing sections;
- research question, intended audience, rubric version, comparison-source
  identities and versions, and declared comparison coverage;
- each finding, its dimension, cited evidence, uncertainties, counterevidence,
  recommendation, and reasons;
- prompt version and hash, model/provider, generation parameters, timestamp,
  stop reason, and validation result for a model-produced review;
- a separate human decision history with actor, time, reason, and superseded
  decision, without agents inventing human approvals.

Review statements must retain stable evidence under the existing
[analysis contract](ANALYSIS.md). A quotation proves what the source says,
not that its claim is independently true. Unresolved or mismatched evidence
prevents a completed review from being published.

Cache identity covers the exact input, coverage, topic, audience, comparison
set, rubric, prompt, model, and parameters. A changed source version or review
context makes the old recommendation stale; it remains available as history
but cannot silently carry over as a current decision. Invalid, truncated, or
failed attempts never replace a valid result or imply a negative verdict.

Review text and source content remain separate. Generated criticism is never
ingested as scientific evidence or used to reconstruct bibliographic fields.
Source text is untrusted data, including instructions embedded in PDFs.

## Bounded implementation order

1. Extend the domain and analysis contracts with review scope, dimensions,
   evidence, recommendations, and separate selection events. Freeze schemas
   and port changes before the WP-39 migration cut, or use a reviewed follow-up
   migration if that cut has already landed.
2. Implement immutable review history through the catalogue adapter and
   `AnalysisUnitOfWorkFactory`, with revision, rollback, replay, and stale-input
   checks. Keep raw retrieval and citation behavior unchanged.
3. Add a bounded analysis service with an injected backend and offline
   fixtures. Begin with explicitly requested single-source reviews. Resolve
   and validate passages before publishing any findings.
4. Expose review and override through the CLI application boundary. Show the
   reasons and inspected evidence; defer new MCP tools and unattended batch
   filtering to separately reviewed contracts.
5. Calibrate on a frozen, human-reviewed set before claiming review quality
   or opening batch selection. Record exact denominators, disagreements,
   abstentions, and false exclusions of useful sources. Thresholds must be
   agreed before evaluating the held-out set.

This extends [WP-40](../superpowers/plans/2026-08-28-complete-program-execution.md#wp-40-source-backed-analysis-and-cache).
It does not reorder the programme or open Gate 3 while Gate 2 is blocked.
The existing 30-query retrieval gate and 20-analysis usefulness/fidelity gate
remain independent; neither certifies this new review rubric. Human review
should use concise evidence cards, with optional access to the source, rather
than requiring a full-paper reading for every triage decision.

## Acceptance scenarios

- A relevant abstract with no methods available leaves methodological quality
  `UNKNOWN`; it cannot be auto-excluded as low quality.
- A well-supported replication or negative result can be retained.
- A novelty claim without identified comparators remains `UNKNOWN`.
- A claim contradicted by an inspected result cites both passages and states
  the conflict instead of rewriting the source.
- Invalid passage IDs, changed artifacts, prompt injection, malformed output,
  truncation, and backend failure cannot publish a completed review.
- A human override is replayable; neither override nor exclusion deletes a
  source, hides it from normal search, or changes its citation.
- Revisions invalidate current applicability without destroying past reviews.
- Ordinary search and citation never trigger an LLM or external lookup.
- Mocked backend and local fixtures prove mechanics; actual rubric quality
  remains `UNKNOWN` until the separate evaluation is complete.

## Companion project

[YouTube Insights](https://github.com/FlorianBruniaux/youtube-video-insights/blob/main/docs/superpowers/specs/2026-09-22-critical-source-review-design.md)
uses the same separation between recommendation, evidence, and selection.
Its rubric covers transcript evidence and timestamped demonstrations. A video
discussing a paper does not count as an independent scientific validation, and
the two projects do not share a database or a universal quality score.
