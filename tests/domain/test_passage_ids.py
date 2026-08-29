from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest

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
        replace(identity, start_offset=1, end_offset=14),
    )
    assert all(passage_id(item) != baseline for item in variants)


def test_passage_id_uses_canonical_text() -> None:
    composed = PassageIdentity(
        paper_version_id=VERSION_ID,
        artifact_sha256=Sha256("a" * 64),
        chunk_schema_version="chunk-v1",
        section=None,
        ordinal=0,
        normalized_text="Café\n",
        start_offset=0,
        end_offset=5,
    )
    assert passage_id(composed) == passage_id(composed)


def test_passage_identity_rejects_noncanonical_text_and_invalid_offsets() -> None:
    with pytest.raises(ValueError):
        PassageIdentity(
            paper_version_id=VERSION_ID,
            artifact_sha256=Sha256("a" * 64),
            chunk_schema_version="chunk-v1",
            section=None,
            ordinal=0,
            normalized_text="line\r\n",
            start_offset=0,
            end_offset=5,
        )
    with pytest.raises(ValueError):
        PassageIdentity(
            paper_version_id=VERSION_ID,
            artifact_sha256=Sha256("a" * 64),
            chunk_schema_version="chunk-v1",
            section=None,
            ordinal=0,
            normalized_text="short",
            start_offset=0,
            end_offset=6,
        )
