from __future__ import annotations

import json
import re

from paper_insights.application.ports.catalog import CatalogReader
from paper_insights.application.ports.citations import CitationRenderer
from paper_insights.domain.corpus import (
    CitationFormat,
    CitationInput,
    CitationResult,
    CitationSelector,
    CitationWarning,
)
from paper_insights.domain.identifiers import PaperSelector, PaperVersionId
from paper_insights.domain.retrieval import CoverageStatus

_BIBTEX_ESCAPES = {
    "#": r"\#",
    "$": r"\$",
    "%": r"\%",
    "&": r"\&",
    "\\": r"\textbackslash{}",
    "^": r"\textasciicircum{}",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
}


class CitationNotFoundError(LookupError):
    def __init__(self) -> None:
        super().__init__("exact paper or version was not found")


class AmbiguousCitationMetadataError(ValueError):
    def __init__(self) -> None:
        super().__init__("observed DOI is ambiguous")


class CitationService:
    def __init__(self, reader: CatalogReader, renderer: CitationRenderer) -> None:
        self._reader = reader
        self._renderer = renderer

    def render(
        self,
        paper: PaperSelector,
        format: CitationFormat,
        *,
        paper_version_id: PaperVersionId | None = None,
    ) -> CitationResult:
        selector = CitationSelector(paper=paper, paper_version_id=paper_version_id)
        with self._reader.snapshot() as snapshot:
            citation = snapshot.get_citation_input(selector)
        if citation is None:
            raise CitationNotFoundError
        return self._renderer.render(citation, format)


class SourceBackedCitationRenderer:
    def render(self, citation: CitationInput, format: CitationFormat) -> CitationResult:
        if format is CitationFormat.BIBTEX:
            return self._render_bibtex(citation)
        if format is CitationFormat.MARKDOWN:
            return self._render_markdown(citation)
        if format is CitationFormat.CSL_JSON:
            return self._render_csl_json(citation)
        raise ValueError(f"unsupported citation format: {format}")

    def _render_bibtex(self, citation: CitationInput) -> CitationResult:
        observed = citation.observation.observed
        fields: list[tuple[str, str]] = []
        missing: list[str] = []
        warnings: set[CitationWarning] = set()

        if observed.authors:
            author_field = " and ".join(
                _escape_bibtex(author.raw_name) for author in observed.authors
            )
            fields.append(("author", author_field))
            if any(not author.given_name or not author.family_name for author in observed.authors):
                warnings.add(CitationWarning.LITERAL_AUTHOR)
        else:
            missing.append("author")

        doi = _observed_doi(citation)
        if doi is not None:
            fields.append(("doi", _escape_bibtex(doi)))
        fields.append(("title", _escape_bibtex(observed.title)))
        if observed.source_url is not None:
            fields.append(("url", _escape_bibtex(observed.source_url)))
        if observed.submitted_at is not None:
            fields.append(("year", str(observed.submitted_at.year)))
        else:
            missing.append("year")

        if missing:
            warnings.add(CitationWarning.MISSING_REQUIRED_FIELD)
        key = _bibtex_key(citation)
        body = "\n".join(f"  {name} = {{{value}}}," for name, value in fields)
        return _result(
            citation,
            format=CitationFormat.BIBTEX,
            media_type="application/x-bibtex",
            content=f"@misc{{{key},\n{body}\n}}",
            missing_fields=tuple(sorted(missing)),
            warnings=tuple(sorted(warnings, key=lambda warning: warning.value)),
        )

    def _render_markdown(self, citation: CitationInput) -> CitationResult:
        observed = citation.observation.observed
        segments: list[str] = []
        missing: list[str] = []
        warnings: set[CitationWarning] = set()
        if observed.authors:
            segments.append(
                "; ".join(_escape_markdown(author.raw_name) for author in observed.authors)
            )
            if any(not author.given_name or not author.family_name for author in observed.authors):
                warnings.add(CitationWarning.LITERAL_AUTHOR)
        else:
            missing.append("author")
        segments.append(f"**{_escape_markdown(observed.title)}**")
        if observed.submitted_at is not None:
            segments.append(str(observed.submitted_at.year))
        else:
            missing.append("year")
        doi = _observed_doi(citation)
        if doi is not None:
            segments.append(f"DOI: `{doi}`")
        if observed.source_url is not None:
            segments.append(f"Source: <{observed.source_url}>")
        reference = ". ".join(segments) + "."
        provenance = (
            f"> Provenance: `{citation.source_id}:{citation.source_item_id}`; "
            f"snapshot `{citation.snapshot_id}`; record `{citation.record_ordinal}`; "
            f"retrieved `{_utc_z(citation.retrieved_at.isoformat())}`."
        )
        if missing:
            warnings.add(CitationWarning.MISSING_REQUIRED_FIELD)
        return _result(
            citation,
            format=CitationFormat.MARKDOWN,
            media_type="text/markdown",
            content=f"{reference}\n\n{provenance}",
            missing_fields=tuple(sorted(missing)),
            warnings=tuple(sorted(warnings, key=lambda warning: warning.value)),
        )

    def _render_csl_json(self, citation: CitationInput) -> CitationResult:
        observed = citation.observation.observed
        authors: list[dict[str, str]] = []
        has_literal_author = False
        missing: list[str] = []
        for author in observed.authors:
            if author.family_name and author.given_name:
                authors.append({"family": author.family_name, "given": author.given_name})
            else:
                authors.append({"literal": author.raw_name})
                has_literal_author = True
        payload: dict[str, object] = {
            "id": f"{citation.source_id}:{observed.source_version_key}",
            "title": observed.title,
            "type": "article",
        }
        if authors:
            payload["author"] = authors
        else:
            missing.append("author")
        if observed.submitted_at is not None:
            payload["issued"] = {
                "date-parts": [
                    [
                        observed.submitted_at.year,
                        observed.submitted_at.month,
                        observed.submitted_at.day,
                    ]
                ]
            }
        else:
            missing.append("issued")
        doi = _observed_doi(citation)
        if doi is not None:
            payload["DOI"] = doi
        if observed.source_url is not None:
            payload["URL"] = observed.source_url
        warnings: set[CitationWarning] = set()
        if has_literal_author:
            warnings.add(CitationWarning.LITERAL_AUTHOR)
        if missing:
            warnings.add(CitationWarning.MISSING_REQUIRED_FIELD)
        return _result(
            citation,
            format=CitationFormat.CSL_JSON,
            media_type="application/vnd.citationstyles.csl+json",
            content=json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            missing_fields=tuple(sorted(missing)),
            warnings=tuple(sorted(warnings, key=lambda warning: warning.value)),
        )


def _escape_bibtex(value: str) -> str:
    return "".join(_BIBTEX_ESCAPES.get(character, character) for character in value)


def _escape_markdown(value: str) -> str:
    return "".join(f"\\{character}" if character in r"\`*_[]" else character for character in value)


def _utc_z(value: str) -> str:
    return value.removesuffix("+00:00") + "Z"


def _bibtex_key(citation: CitationInput) -> str:
    observed = citation.observation.observed
    exact_identifier = f"{citation.source_id.value}_{observed.source_version_key}"
    return re.sub(r"[^A-Za-z0-9]+", "_", exact_identifier).strip("_")


def _observed_doi(citation: CitationInput) -> str | None:
    values = {
        identifier.canonical_value
        for identifier in citation.observation.observed.identifiers
        if identifier.scheme.lower() == "doi"
    }
    if len(values) > 1:
        raise AmbiguousCitationMetadataError
    return next(iter(values), None)


def _result(
    citation: CitationInput,
    *,
    format: CitationFormat,
    media_type: str,
    content: str,
    missing_fields: tuple[str, ...],
    warnings: tuple[CitationWarning, ...],
) -> CitationResult:
    observation = citation.observation
    return CitationResult(
        schema_version="citation-v1",
        paper_id=citation.paper_id,
        paper_version_id=observation.paper_version_id,
        version_observation_id=observation.observation_id,
        format=format,
        media_type=media_type,
        content=content,
        missing_fields=missing_fields,
        source_id=citation.source_id,
        source_item_id=citation.source_item_id,
        snapshot_id=citation.snapshot_id,
        record_ordinal=citation.record_ordinal,
        retrieved_at=citation.retrieved_at,
        coverage=CoverageStatus.COMPLETE,
        warnings=warnings,
    )
