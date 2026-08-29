from __future__ import annotations

from uuid import UUID

import pytest

from paper_insights.domain.identifiers import (
    AuthorId,
    PaperId,
    PaperSelector,
    PaperVersionId,
    Sha256,
    SourceId,
    VersionSelector,
)


UUID7 = UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")


def test_identifiers_accept_canonical_values() -> None:
    assert str(SourceId("arxiv")) == "arxiv"
    assert PaperId(UUID7).value.version == 7
    assert PaperVersionId(UUID7).value.version == 7
    assert AuthorId(UUID7).value.version == 7
    assert str(Sha256("a" * 64)) == "a" * 64


@pytest.mark.parametrize("value", ["", "ArXiv", "ar xiv", "../arxiv", "a" * 65])
def test_source_id_rejects_noncanonical_values(value: str) -> None:
    with pytest.raises(ValueError):
        SourceId(value)


def test_uuid_wrappers_reject_non_v7_values() -> None:
    with pytest.raises(ValueError):
        PaperId(UUID("12345678-1234-4234-9234-123456789abc"))


@pytest.mark.parametrize("value", ["A" * 64, "f" * 63, "g" * 64])
def test_sha256_rejects_noncanonical_values(value: str) -> None:
    with pytest.raises(ValueError):
        Sha256(value)


def test_paper_and_version_selectors_are_exact_and_exclusive() -> None:
    paper = PaperSelector.by_arxiv("2608.01234")
    version = VersionSelector.by_source_version(SourceId("arxiv"), "2608.01234v2")

    assert paper.arxiv_id == "2608.01234"
    assert version.source_version_key == "2608.01234v2"

    with pytest.raises(ValueError):
        PaperSelector(paper_id=PaperId(UUID7), doi="10.1000/example")
    with pytest.raises(ValueError):
        VersionSelector(
            paper_version_id=None,
            source_id=None,
            source_version_key=None,
            current=False,
        )
