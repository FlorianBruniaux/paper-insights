from test_identifier_resolution import make_citation_input

from paper_insights.application.research.citations import SourceBackedCitationRenderer
from paper_insights.domain.acquisition import ObservedAuthor
from paper_insights.domain.corpus import CitationFormat, CitationWarning
from paper_insights.domain.retrieval import CoverageStatus


def test_bibtex_uses_exact_source_version_author_order_and_deterministic_escaping() -> None:
    result = SourceBackedCitationRenderer().render(make_citation_input(), CitationFormat.BIBTEX)

    assert result.content == (
        "@misc{paperinsights_61727869763a323630382e30313233347632,\n"
        "  author = {Lovelace, Ada and {Research Group}},\n"
        "  doi = {10.1000/agents\\_evidence},\n"
        "  title = {Agents \\& \\{Evidence\\} \\textbackslash{} Systems\\_},\n"
        "  url = {https://arxiv.org/abs/2608.01234v2},\n"
        "  year = {2026},\n"
        "}"
    )
    assert result.missing_fields == ()
    assert result.warnings == (CitationWarning.LITERAL_AUTHOR,)
    assert result.coverage is CoverageStatus.COMPLETE
    assert result.media_type == "application/x-bibtex"


def test_bibtex_omits_unobserved_required_fields_and_reports_them() -> None:
    result = SourceBackedCitationRenderer().render(
        make_citation_input(authors=(), submitted_at=None), CitationFormat.BIBTEX
    )

    assert "author =" not in result.content
    assert "year =" not in result.content
    assert result.missing_fields == ("author", "year")
    assert result.warnings == (CitationWarning.MISSING_REQUIRED_FIELD,)


def test_bibtex_groups_literal_authors_that_contain_the_separator_word() -> None:
    result = SourceBackedCitationRenderer().render(
        make_citation_input(
            authors=(
                ObservedAuthor(
                    raw_name="Grace Hopper",
                    given_name="Grace",
                    family_name="Hopper",
                ),
                ObservedAuthor(raw_name="Research and Development"),
            )
        ),
        CitationFormat.BIBTEX,
    )

    assert "author = {Hopper, Grace and {Research and Development}}," in result.content
    assert result.warnings == (CitationWarning.LITERAL_AUTHOR,)


def test_bibtex_keys_do_not_collide_when_exact_identifiers_have_different_separators() -> None:
    renderer = SourceBackedCitationRenderer()
    slash = renderer.render(make_citation_input(source_version_key="x/y"), CitationFormat.BIBTEX)
    underscore = renderer.render(
        make_citation_input(source_version_key="x_y"), CitationFormat.BIBTEX
    )

    assert slash.content.startswith("@misc{paperinsights_61727869763a782f79,")
    assert underscore.content.startswith("@misc{paperinsights_61727869763a785f79,")
    assert slash.content.splitlines()[0] != underscore.content.splitlines()[0]
