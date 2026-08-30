import pytest
from markdown_it import MarkdownIt
from test_identifier_resolution import SNAPSHOT_ID, make_citation_input

from paper_insights.application.research.citations import (
    SourceBackedCitationRenderer,
    UnsafeCitationValueError,
)
from paper_insights.domain.acquisition import IdentifierScope, ObservedAuthor, ObservedIdentifier
from paper_insights.domain.corpus import CitationFormat, CitationWarning


def test_markdown_has_a_readable_reference_and_separate_exact_provenance() -> None:
    result = SourceBackedCitationRenderer().render(make_citation_input(), CitationFormat.MARKDOWN)

    assert result.content == (
        "Ada Lovelace; Research Group. **Agents &amp; {Evidence} \\\\ Systems\\_**. "
        "2026. DOI: `10.1000/agents_evidence`. "
        "Source: <https://arxiv.org/abs/2608.01234v2>.\n\n"
        f"> Provenance: source `arxiv`; item `2608.01234`; snapshot `{SNAPSHOT_ID}`; "
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
        f"> Provenance: source `arxiv`; item `2608.01234`; snapshot `{SNAPSHOT_ID}`; "
        "record `1`; retrieved `2026-08-29T07:30:00Z`."
    )
    assert result.missing_fields == ("author", "year")
    assert result.warnings == (CitationWarning.MISSING_REQUIRED_FIELD,)


def test_markdown_escapes_html_uses_dynamic_code_spans_and_rejects_non_https_url() -> None:
    result = SourceBackedCitationRenderer().render(
        make_citation_input(
            title="<script>*unsafe*</script> & evidence",
            authors=(ObservedAuthor(raw_name="<Research & Development>"),),
            identifiers=(
                ObservedIdentifier(
                    scheme="doi",
                    canonical_value="10.1000/a``b",
                    scope=IdentifierScope.VERSION,
                ),
            ),
            source_url="http://example.com/<unsafe>",
            source_item_id="item`id",
        ),
        CitationFormat.MARKDOWN,
    )

    assert result.content.startswith(
        "&lt;Research &amp; Development&gt;. "
        "**&lt;script&gt;\\*unsafe\\*&lt;/script&gt; &amp; evidence**. "
        "2026. DOI: ```10.1000/a``b```.\n\n"
    )
    assert (
        f"> Provenance: source `arxiv`; item ``item`id``; snapshot `{SNAPSHOT_ID}`; "
        "record `1`; retrieved `2026-08-29T07:30:00Z`."
    ) in result.content
    assert "Source:" not in result.content
    assert "http://" not in result.content
    assert result.missing_fields == ()
    assert result.warnings == (CitationWarning.LITERAL_AUTHOR,)


def test_markdown_neutralizes_block_markers_controls_and_unicode_formatting() -> None:
    result = SourceBackedCitationRenderer().render(
        make_citation_input(
            title="<b>Title\x7f\u202e</b>",
            authors=(
                ObservedAuthor(
                    raw_name=(
                        "    # heading\n> quote\r\n- item\n1. item\n```fence\n---\n    code\u202e"
                    )
                ),
            ),
        ),
        CitationFormat.MARKDOWN,
    )

    assert result.content.startswith(
        "&#32;&#32;&#32;&#32;\\# heading\\\\u000A&gt; quote\\\\u000D"
        "\\\\u000A\\- item\\\\u000A1\\. item\\\\u000A"
        "\\`\\`\\`fence\\\\u000A\\-\\-\\-\\\\u000A    code\\\\u202E. "
        "**&lt;b&gt;Title\\\\u007F\\\\u202E&lt;/b&gt;**."
    )
    assert result.content.count("\n") == 2
    assert "\r" not in result.content
    assert "\x7f" not in result.content
    assert "\u202e" not in result.content


@pytest.mark.parametrize(
    "source_url",
    (
        "https://example.test/path\x7fhidden",
        "https://example.test/path\u202eevil",
    ),
)
def test_markdown_omits_urls_containing_unicode_controls_or_formatting(
    source_url: str,
) -> None:
    result = SourceBackedCitationRenderer().render(
        make_citation_input(source_url=source_url), CitationFormat.MARKDOWN
    )

    assert "Source:" not in result.content
    assert result.missing_fields == ()
    assert result.warnings == (CitationWarning.LITERAL_AUTHOR,)


def test_markdown_rejects_provenance_identifiers_with_line_endings() -> None:
    citation = make_citation_input(source_item_id="item\nidentifier")

    with pytest.raises(UnsafeCitationValueError, match="unsafe control or formatting"):
        SourceBackedCitationRenderer().render(citation, CitationFormat.MARKDOWN)


def test_markdown_preserves_title_edge_spaces_inside_valid_commonmark_emphasis() -> None:
    result = SourceBackedCitationRenderer().render(
        make_citation_input(title="  Observed title  "), CitationFormat.MARKDOWN
    )

    inline = next(
        token for token in MarkdownIt("commonmark").parse(result.content) if token.children
    )
    children = inline.children or []
    strong_open = next(index for index, token in enumerate(children) if token.type == "strong_open")
    strong_close = next(
        index
        for index, token in enumerate(children[strong_open + 1 :], start=strong_open + 1)
        if token.type == "strong_close"
    )
    visible_title = "".join(
        token.content for token in children[strong_open + 1 : strong_close] if token.type == "text"
    )

    assert visible_title == "  Observed title  "
    assert "**&#32;&#32;Observed title&#32;&#32;**" in result.content
