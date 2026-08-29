from __future__ import annotations

from pathlib import Path

from paper_insights.adapters.providers.arxiv.parser import parse_arxiv_feed


FIXTURES = Path(__file__).parents[1] / "fixtures" / "arxiv"


def test_parser_handles_default_namespaces_and_preserves_ordered_metadata() -> None:
    parsed = parse_arxiv_feed((FIXTURES / "page-1.xml").read_bytes(), page_ordinal=0)

    assert parsed.total_results == 3
    assert parsed.start_index == 0
    assert parsed.items_per_page == 2
    assert parsed.issues == ()
    first = parsed.records[0]
    assert first.observation is not None
    assert first.observation.source_item_id == "2608.01234"
    assert first.observation.source_version_key == "2608.01234v1"
    assert first.observation.title == "Reliable Paper Agents"
    assert first.observation.abstract == "Evidence-backed scientific workflows."
    assert tuple(author.raw_name for author in first.observation.authors) == (
        "Alice Example",
        "Bob Researcher",
    )
    assert first.observation.authors[0].affiliation_raw == "Example University"
    assert tuple(
        (category.value, category.is_primary) for category in first.observation.categories
    ) == (("cs.AI", True), ("cs.LG", False))
    assert tuple(
        (identifier.scheme, identifier.canonical_value)
        for identifier in first.observation.identifiers
    ) == (("arxiv", "2608.01234"), ("doi", "10.1234/example.1"))
    assert first.observation.comment == "12 pages, 3 figures"
    assert first.observation.journal_reference == "Journal of Fixtures 1 (2026)"
    assert first.observation.source_url == "https://arxiv.org/abs/2608.01234v1"


def test_parser_handles_prefixed_atom_namespace_and_absent_doi() -> None:
    parsed = parse_arxiv_feed(
        (FIXTURES / "page-2-overlap.xml").read_bytes(), page_ordinal=1
    )

    observation = parsed.records[1].observation
    assert observation is not None
    assert observation.source_version_key == "2608.09999v1"
    assert tuple(item.scheme for item in observation.identifiers) == ("arxiv",)
    assert observation.comment is None
    assert observation.journal_reference is None


def test_parser_keeps_v1_and_v2_as_distinct_versions() -> None:
    first = parse_arxiv_feed((FIXTURES / "page-1.xml").read_bytes(), page_ordinal=0)
    revised = parse_arxiv_feed((FIXTURES / "revision-v2.xml").read_bytes(), page_ordinal=1)

    assert first.records[0].observation is not None
    assert revised.records[0].observation is not None
    assert (
        first.records[0].observation.source_item_id
        == revised.records[0].observation.source_item_id
    )
    assert first.records[0].observation.source_version_key == "2608.01234v1"
    assert revised.records[0].observation.source_version_key == "2608.01234v2"


def test_invalid_entry_becomes_a_bounded_record_issue() -> None:
    payload = b"""<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'>
      <entry><id>https://arxiv.org/abs/not-an-id</id><title>Broken</title></entry>
    </feed>"""

    parsed = parse_arxiv_feed(payload, page_ordinal=0)

    assert len(parsed.records) == 1
    assert parsed.records[0].observation is None
    assert parsed.records[0].locator.page_ordinal == 0
    assert parsed.records[0].locator.record_ordinal == 0
    assert len(parsed.issues) == 1
    assert parsed.issues[0].message == "arXiv entry is invalid"
