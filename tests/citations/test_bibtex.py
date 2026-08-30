from test_identifier_resolution import make_citation_input

from paper_insights.application.research.citations import SourceBackedCitationRenderer
from paper_insights.domain.corpus import CitationFormat, CitationWarning
from paper_insights.domain.retrieval import CoverageStatus


def test_bibtex_uses_exact_source_version_author_order_and_deterministic_escaping() -> None:
    result = SourceBackedCitationRenderer().render(make_citation_input(), CitationFormat.BIBTEX)

    assert result.content == (
        "@misc{arxiv_2608_01234v2,\n"
        "  author = {Ada Lovelace and Research Group},\n"
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
