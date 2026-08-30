import json

from test_identifier_resolution import make_citation_input

from paper_insights.application.research.citations import SourceBackedCitationRenderer
from paper_insights.domain.acquisition import ObservedAuthor
from paper_insights.domain.corpus import CitationFormat, CitationWarning


def test_csl_json_is_canonical_and_uses_only_observed_author_parts() -> None:
    result = SourceBackedCitationRenderer().render(make_citation_input(), CitationFormat.CSL_JSON)

    assert result.content == (
        '{"DOI":"10.1000/agents_evidence",'
        '"URL":"https://arxiv.org/abs/2608.01234v2",'
        '"author":[{"family":"Lovelace","given":"Ada"},{"literal":"Research Group"}],'
        '"id":"arxiv:2608.01234v2",'
        '"issued":{"date-parts":[[2026,8,28]]},'
        '"title":"Agents & {Evidence} \\\\ Systems_"}'
    )
    assert json.loads(result.content)["author"][1] == {"literal": "Research Group"}
    assert result.missing_fields == ("type",)
    assert result.warnings == (
        CitationWarning.LITERAL_AUTHOR,
        CitationWarning.MISSING_REQUIRED_FIELD,
    )
    assert result.media_type == "application/vnd.citationstyles.csl+json"


def test_csl_json_omits_unobserved_optional_and_required_values() -> None:
    result = SourceBackedCitationRenderer().render(
        make_citation_input(
            title="Observed title",
            authors=(),
            identifiers=(),
            source_url=None,
            submitted_at=None,
        ),
        CitationFormat.CSL_JSON,
    )

    assert result.content == '{"id":"arxiv:2608.01234v2","title":"Observed title"}'
    assert result.missing_fields == ("author", "issued", "type")
    assert result.warnings == (CitationWarning.MISSING_REQUIRED_FIELD,)


def test_csl_json_uses_literal_author_when_a_separated_part_is_blank() -> None:
    result = SourceBackedCitationRenderer().render(
        make_citation_input(
            authors=(
                ObservedAuthor(
                    raw_name="Observed Consortium",
                    given_name="",
                    family_name="Consortium",
                ),
            )
        ),
        CitationFormat.CSL_JSON,
    )

    assert json.loads(result.content)["author"] == [{"literal": "Observed Consortium"}]
    assert result.missing_fields == ("type",)
    assert result.warnings == (
        CitationWarning.LITERAL_AUTHOR,
        CitationWarning.MISSING_REQUIRED_FIELD,
    )
