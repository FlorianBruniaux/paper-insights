#!/usr/bin/env python3
"""Add workflow context for paper research and ingestion prompts."""

from __future__ import annotations

import json
import re
import sys

PAPER_CONTEXT = re.compile(
    r"\b(arxiv|bibtex|csl(?:-json)?|doi|paper|papers|papier|papiers|publication|publications|preprint|preprints)\b",
    re.IGNORECASE,
)
INGEST_INTENT = re.compile(
    r"\b(ingest|collect|download|fetch|add|watch|veille|ajout|ajouter|récup|recup|télécharg|telecharg)\w*\b",
    re.IGNORECASE,
)
RESEARCH_INTENT = re.compile(
    r"\b(search|find|compare|cherche|recherche|trouve|compare|source)\w*\b",
    re.IGNORECASE,
)
CITATION_INTENT = re.compile(
    r"\b(cite|citer|citation|bibtex|csl(?:-json)?|référence|reference)\w*\b",
    re.IGNORECASE,
)


def context_for(prompt: str) -> str | None:
    if not PAPER_CONTEXT.search(prompt):
        return None
    if INGEST_INTENT.search(prompt):
        return (
            "[paper-insights routing] This is an ingestion or monitoring request. "
            "Use the paper-ingest skill. Preview first, keep network access and corpus mutation "
            "in the main session, and require confirmation for queries, watchlists or "
            "multiple papers."
        )
    if RESEARCH_INTENT.search(prompt):
        return (
            "[paper-insights routing] This is a read-only corpus research request. "
            "Use the paper-research skill and paper-researcher agent. Return source-backed "
            "metadata "
            "and passages, and state local corpus coverage limits."
        )
    if CITATION_INTENT.search(prompt):
        return (
            "[paper-insights routing] This is a standalone citation export request. "
            "Use the paper-citation skill and the read-only Gate 2 CLI. Return the exact "
            "stored citation with provenance and missing fields; do not infer metadata or "
            "acquire a paper."
        )
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0
    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        return 0
    context = context_for(prompt)
    if context is None:
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context,
                }
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
