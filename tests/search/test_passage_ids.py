from __future__ import annotations

from uuid import UUID

from paper_insights.adapters.search.sqlite_fts.builder import passages_for_document
from paper_insights.domain.identifiers import (
    PaperId,
    PaperVersionId,
    Sha256,
    VersionObservationId,
)
from paper_insights.domain.retrieval import IndexDocument


def test_title_and_abstract_passages_have_stable_normalized_identities() -> None:
    document = IndexDocument(
        paper_id=PaperId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f51")),
        paper_version_id=PaperVersionId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")),
        version_observation_id=VersionObservationId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5b")),
        title="Cafe\u0301\r\nagents",
        abstract="  Evidence stays linked.  ",
        metadata_artifact_sha256=Sha256("a" * 64),
    )

    title, abstract = passages_for_document(document, "chunk-v1")

    assert str(title.passage_id) == (
        "2d75fae55d600a9d02bba467c1716e148267ffff3ae774d749182593487a6bdb"
    )
    assert title.identity.normalized_text == "Caf\u00e9\nagents"
    assert title.identity.section == "title"
    assert title.identity.ordinal == 0
    assert (title.identity.start_offset, title.identity.end_offset) == (0, 11)
    assert abstract.identity.section == "abstract"
    assert abstract.identity.ordinal == 1
    assert abstract.text == "  Evidence stays linked.  "


def test_blank_abstract_does_not_create_an_unsearchable_passage() -> None:
    document = IndexDocument(
        paper_id=PaperId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f51")),
        paper_version_id=PaperVersionId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")),
        version_observation_id=VersionObservationId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5b")),
        title="Evidence",
        abstract=" \n ",
        metadata_artifact_sha256=Sha256("a" * 64),
    )

    passages = passages_for_document(document, "chunk-v1")

    assert tuple(passage.identity.section for passage in passages) == ("title",)
