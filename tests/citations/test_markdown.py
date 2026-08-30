from test_identifier_resolution import SNAPSHOT_ID, make_citation_input

from paper_insights.application.research.citations import SourceBackedCitationRenderer
from paper_insights.domain.corpus import CitationFormat, CitationWarning


def test_markdown_has_a_readable_reference_and_separate_exact_provenance() -> None:
    result = SourceBackedCitationRenderer().render(make_citation_input(), CitationFormat.MARKDOWN)

    assert result.content == (
        "Ada Lovelace; Research Group. **Agents & {Evidence} \\\\ Systems\\_**. "
        "2026. DOI: `10.1000/agents_evidence`. "
        "Source: <https://arxiv.org/abs/2608.01234v2>.\n\n"
        f"> Provenance: `arxiv:2608.01234`; snapshot `{SNAPSHOT_ID}`; "
        "record `1`; retrieved `2026-08-29T07:30:00Z`."
    )
    assert result.warnings == (CitationWarning.LITERAL_AUTHOR,)
    assert result.media_type == "text/markdown"


def test_markdown_omits_missing_segments_without_orphan_punctuation() -> None:
    result = SourceBackedCitationRenderer().render(
        make_citation_input(
            title="Observed title",
            authors=(),
            identifiers=(),
            source_url=None,
            submitted_at=None,
        ),
        CitationFormat.MARKDOWN,
    )

    assert result.content == (
        "**Observed title**.\n\n"
        f"> Provenance: `arxiv:2608.01234`; snapshot `{SNAPSHOT_ID}`; "
        "record `1`; retrieved `2026-08-29T07:30:00Z`."
    )
    assert result.missing_fields == ("author", "year")
    assert result.warnings == (CitationWarning.MISSING_REQUIRED_FIELD,)
