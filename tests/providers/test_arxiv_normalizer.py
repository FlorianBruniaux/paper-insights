from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from paper_insights.adapters.providers.arxiv.normalizer import normalized_metadata_payload
from paper_insights.adapters.providers.arxiv.parser import parse_arxiv_feed
from paper_insights.domain.acquisition import IdentifierScope, ObservedIdentifier

FIXTURES = Path(__file__).parents[1] / "fixtures" / "arxiv"


def test_normalized_hash_is_canonical_and_covers_version_metadata() -> None:
    parsed = parse_arxiv_feed((FIXTURES / "page-1.xml").read_bytes(), page_ordinal=0)
    observation = parsed.records[0].observation
    assert observation is not None

    payload = normalized_metadata_payload(observation)

    assert json.loads(payload)["source_version_key"] == "2608.01234v1"
    assert observation.normalized_sha256.value == hashlib.sha256(payload).hexdigest()
    assert b'": ' not in payload
    assert b'", "' not in payload


def test_raw_record_hash_tracks_the_exact_entry_bytes() -> None:
    payload = (FIXTURES / "page-1.xml").read_bytes()
    parsed = parse_arxiv_feed(payload, page_ordinal=0)

    first_raw = payload[payload.index(b"  <entry>") + 2 : payload.index(b"  </entry>") + 10]
    assert parsed.records[0].locator.raw_record_sha256.value == hashlib.sha256(
        first_raw
    ).hexdigest()


def test_identifier_scope_changes_canonical_payload_and_digest() -> None:
    parsed = parse_arxiv_feed((FIXTURES / "page-1.xml").read_bytes(), page_ordinal=0)
    observation = parsed.records[0].observation
    assert observation is not None
    paper_scoped = replace(
        observation,
        identifiers=(
            ObservedIdentifier(
                scheme="doi",
                canonical_value="10.1234/example.1",
                scope=IdentifierScope.PAPER,
            ),
        ),
    )
    version_scoped = replace(
        observation,
        identifiers=(
            ObservedIdentifier(
                scheme="doi",
                canonical_value="10.1234/example.1",
                scope=IdentifierScope.VERSION,
            ),
        ),
    )

    paper_payload = normalized_metadata_payload(paper_scoped)
    version_payload = normalized_metadata_payload(version_scoped)

    assert json.loads(paper_payload)["identifiers"][0]["scope"] == "paper"
    assert json.loads(version_payload)["identifiers"][0]["scope"] == "version"
    assert paper_payload != version_payload
    assert hashlib.sha256(paper_payload).digest() != hashlib.sha256(version_payload).digest()
