from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from paper_insights.domain.identifiers import PaperVersionId, Sha256
from paper_insights.domain.retrieval import PassageIdentity, passage_id


VERSION_ID = PaperVersionId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a"))


def test_passage_id_is_deterministic_and_covers_every_component() -> None:
    identity = PassageIdentity(
        paper_version_id=VERSION_ID,
        artifact_sha256=Sha256("a" * 64),
        chunk_schema_version="chunk-v1",
        section=None,
        ordinal=0,
        normalized_text="Evidence\nline",
        start_offset=0,
        end_offset=13,
    )
    baseline = passage_id(identity)

    assert baseline == passage_id(identity)
    variants = (
        replace(identity, artifact_sha256=Sha256("b" * 64)),
        replace(identity, chunk_schema_version="chunk-v2"),
        replace(identity, section="abstract"),
        replace(identity, ordinal=1),
        replace(identity, normalized_text="Other", end_offset=5),
        replace(identity, start_offset=1),
        replace(identity, end_offset=12),
    )
    assert all(passage_id(item) != baseline for item in variants)


def test_passage_text_is_normalized_before_hashing() -> None:
    composed = PassageIdentity(
        paper_version_id=VERSION_ID,
        artifact_sha256=Sha256("a" * 64),
        chunk_schema_version="chunk-v1",
        section=None,
        ordinal=0,
        normalized_text="Café\r\n",
        start_offset=0,
        end_offset=5,
    )
    decomposed = replace(composed, normalized_text="Cafe\u0301\n")

    assert passage_id(composed) == passage_id(decomposed)
