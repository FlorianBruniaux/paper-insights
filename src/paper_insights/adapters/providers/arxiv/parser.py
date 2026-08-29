from __future__ import annotations

import hashlib
from dataclasses import dataclass
from xml.etree import ElementTree
from xml.parsers import expat

from paper_insights.adapters.providers.arxiv.normalizer import ATOM, normalize_arxiv_entry
from paper_insights.domain.acquisition import DiscoveryIssue, DiscoveryRecord, RecordLocator
from paper_insights.domain.errors import ErrorCode
from paper_insights.domain.identifiers import Sha256


OPENSEARCH = "http://a9.com/-/spec/opensearch/1.1/"


@dataclass(frozen=True, slots=True)
class ParsedArxivFeed:
    records: tuple[DiscoveryRecord, ...]
    issues: tuple[DiscoveryIssue, ...]
    total_results: int | None
    start_index: int | None
    items_per_page: int | None


def _entry_slices(payload: bytes) -> tuple[bytes, ...]:
    parser = expat.ParserCreate()
    starts: list[int] = []
    entries: list[bytes] = []

    def start(name: str, _attributes: dict[str, str]) -> None:
        if name.rsplit(":", 1)[-1] == "entry":
            starts.append(parser.CurrentByteIndex)

    def end(name: str) -> None:
        if name.rsplit(":", 1)[-1] != "entry":
            return
        if not starts:
            raise ValueError("unbalanced arXiv entry")
        closing = payload.find(b">", parser.CurrentByteIndex)
        if closing < 0:
            raise ValueError("unterminated arXiv entry")
        entries.append(payload[starts.pop() : closing + 1])

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    try:
        parser.Parse(payload, True)
    except expat.ExpatError as exc:
        raise ValueError("invalid arXiv Atom XML") from exc
    return tuple(entries)


def _integer_text(root: ElementTree.Element, name: str) -> int | None:
    text = root.findtext(f"{{{OPENSEARCH}}}{name}")
    if text is None:
        return None
    try:
        value = int(text.strip())
    except ValueError as exc:
        raise ValueError(f"invalid arXiv {name}") from exc
    if value < 0:
        raise ValueError(f"invalid arXiv {name}")
    return value


def parse_arxiv_feed(payload: bytes, *, page_ordinal: int) -> ParsedArxivFeed:
    if page_ordinal < 0:
        raise ValueError("page ordinal cannot be negative")
    lowered = payload.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("arXiv XML declarations are not allowed")
    raw_entries = _entry_slices(payload)
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise ValueError("invalid arXiv Atom XML") from exc
    entries = tuple(root.findall(f"{{{ATOM}}}entry"))
    if len(entries) != len(raw_entries):
        raise ValueError("arXiv entry provenance is incomplete")

    records: list[DiscoveryRecord] = []
    issues: list[DiscoveryIssue] = []
    for record_ordinal, (entry, raw_entry) in enumerate(zip(entries, raw_entries, strict=True)):
        raw_sha = Sha256(hashlib.sha256(raw_entry).hexdigest())
        try:
            observation = normalize_arxiv_entry(
                entry,
                page_ordinal=page_ordinal,
                record_ordinal=record_ordinal,
            )
            locator = RecordLocator(
                page_ordinal=page_ordinal,
                record_ordinal=record_ordinal,
                source_item_id=observation.source_item_id,
                source_version_key=observation.source_version_key,
                raw_record_sha256=raw_sha,
            )
        except ValueError:
            observation = None
            locator = RecordLocator(
                page_ordinal=page_ordinal,
                record_ordinal=record_ordinal,
                source_item_id=None,
                source_version_key=None,
                raw_record_sha256=raw_sha,
            )
            issues.append(
                DiscoveryIssue(
                    code=ErrorCode.RECORD_INVALID,
                    message="arXiv entry is invalid",
                    page_ordinal=page_ordinal,
                    record_ordinal=record_ordinal,
                )
            )
        records.append(DiscoveryRecord(locator=locator, observation=observation))

    return ParsedArxivFeed(
        records=tuple(records),
        issues=tuple(issues),
        total_results=_integer_text(root, "totalResults"),
        start_index=_integer_text(root, "startIndex"),
        items_per_page=_integer_text(root, "itemsPerPage"),
    )
