from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from xml.etree import ElementTree

from paper_insights.domain.acquisition import (
    ObservedAuthor,
    ObservedCategory,
    ObservedIdentifier,
    ObservedPaperVersion,
)
from paper_insights.domain.identifiers import Sha256, SourceId


ATOM = "http://www.w3.org/2005/Atom"
ARXIV = "http://arxiv.org/schemas/atom"
ARXIV_SOURCE = SourceId("arxiv")
_VERSIONED_ID = re.compile(
    r"^(?P<paper>(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5}))v(?P<version>[1-9]\d*)$"
)


def _collapsed_text(element: ElementTree.Element, path: str) -> str | None:
    child = element.find(path)
    if child is None:
        return None
    value = " ".join("".join(child.itertext()).split())
    return value or None


def _parse_datetime(value: str | None, field: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid arXiv {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"arXiv {field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _metadata_data(observation: ObservedPaperVersion) -> dict[str, object]:
    return {
        "abstract": observation.abstract,
        "announced_at": (
            observation.announced_at.isoformat().replace("+00:00", "Z")
            if observation.announced_at
            else None
        ),
        "authors": [
            {
                "affiliation_raw": author.affiliation_raw,
                "family_name": author.family_name,
                "given_name": author.given_name,
                "raw_name": author.raw_name,
            }
            for author in observation.authors
        ],
        "categories": [
            {"is_primary": category.is_primary, "value": category.value}
            for category in observation.categories
        ],
        "comment": observation.comment,
        "identifiers": [
            {"canonical_value": item.canonical_value, "scheme": item.scheme}
            for item in observation.identifiers
        ],
        "journal_reference": observation.journal_reference,
        "language": observation.language,
        "source_id": str(observation.source_id),
        "source_item_id": observation.source_item_id,
        "source_url": observation.source_url,
        "source_version_key": observation.source_version_key,
        "submitted_at": (
            observation.submitted_at.isoformat().replace("+00:00", "Z")
            if observation.submitted_at
            else None
        ),
        "title": observation.title,
    }


def normalized_metadata_payload(observation: ObservedPaperVersion) -> bytes:
    return json.dumps(
        _metadata_data(observation),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def normalize_arxiv_entry(
    entry: ElementTree.Element,
    *,
    page_ordinal: int,
    record_ordinal: int,
) -> ObservedPaperVersion:
    raw_id = _collapsed_text(entry, f"{{{ATOM}}}id")
    if raw_id is None:
        raise ValueError("arXiv entry has no identifier")
    version_key = raw_id.rstrip("/").rsplit("/", 1)[-1]
    match = _VERSIONED_ID.fullmatch(version_key)
    if match is None:
        raise ValueError("arXiv entry identifier is not versioned")
    paper_id = match.group("paper")

    title = _collapsed_text(entry, f"{{{ATOM}}}title")
    if title is None:
        raise ValueError("arXiv entry has no title")
    abstract = _collapsed_text(entry, f"{{{ATOM}}}summary")

    authors = tuple(
        ObservedAuthor(
            raw_name=name,
            affiliation_raw=_collapsed_text(author, f"{{{ARXIV}}}affiliation"),
        )
        for author in entry.findall(f"{{{ATOM}}}author")
        if (name := _collapsed_text(author, f"{{{ATOM}}}name")) is not None
    )
    primary = None
    primary_element = entry.find(f"{{{ARXIV}}}primary_category")
    if primary_element is not None:
        primary = primary_element.get("term")
    categories = tuple(
        ObservedCategory(value=term, is_primary=term == primary)
        for category in entry.findall(f"{{{ATOM}}}category")
        if (term := category.get("term"))
    )

    identifiers: list[ObservedIdentifier] = [
        ObservedIdentifier(scheme="arxiv", canonical_value=paper_id)
    ]
    doi = _collapsed_text(entry, f"{{{ARXIV}}}doi")
    if doi is not None:
        identifiers.append(ObservedIdentifier(scheme="doi", canonical_value=doi.lower()))

    source_url = None
    for link in entry.findall(f"{{{ATOM}}}link"):
        if link.get("rel") == "alternate" and link.get("href"):
            source_url = link.get("href")
            break

    placeholder = ObservedPaperVersion(
        source_id=ARXIV_SOURCE,
        source_item_id=paper_id,
        source_version_key=version_key,
        title=title,
        abstract=abstract,
        page_ordinal=page_ordinal,
        record_ordinal=record_ordinal,
        normalized_sha256=Sha256("0" * 64),
        authors=authors,
        categories=categories,
        identifiers=tuple(identifiers),
        comment=_collapsed_text(entry, f"{{{ARXIV}}}comment"),
        journal_reference=_collapsed_text(entry, f"{{{ARXIV}}}journal_ref"),
        source_url=source_url,
        submitted_at=_parse_datetime(
            _collapsed_text(entry, f"{{{ATOM}}}published"), "published timestamp"
        ),
        announced_at=_parse_datetime(
            _collapsed_text(entry, f"{{{ATOM}}}updated"), "updated timestamp"
        ),
    )
    digest = Sha256(hashlib.sha256(normalized_metadata_payload(placeholder)).hexdigest())
    return ObservedPaperVersion(
        source_id=placeholder.source_id,
        source_item_id=placeholder.source_item_id,
        source_version_key=placeholder.source_version_key,
        title=placeholder.title,
        abstract=placeholder.abstract,
        page_ordinal=placeholder.page_ordinal,
        record_ordinal=placeholder.record_ordinal,
        normalized_sha256=digest,
        authors=placeholder.authors,
        categories=placeholder.categories,
        identifiers=placeholder.identifiers,
        comment=placeholder.comment,
        journal_reference=placeholder.journal_reference,
        language=placeholder.language,
        source_url=placeholder.source_url,
        submitted_at=placeholder.submitted_at,
        announced_at=placeholder.announced_at,
    )
