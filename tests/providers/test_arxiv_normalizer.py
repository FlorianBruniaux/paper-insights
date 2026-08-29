from __future__ import annotations

import hashlib
import json
from pathlib import Path

from paper_insights.adapters.providers.arxiv.normalizer import normalized_metadata_payload
from paper_insights.adapters.providers.arxiv.parser import parse_arxiv_feed


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
