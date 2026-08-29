from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from paper_insights.domain.acquisition import (
    DiscoveryBatch,
    DiscoveryIssue,
    DiscoveryPage,
    DiscoveryQuery,
    DiscoveryRecord,
    ObservedPaperVersion,
    PreparedDiscovery,
    RecordLocator,
    prepared_discovery_digest,
)
from paper_insights.domain.errors import ErrorCode
from paper_insights.domain.identifiers import Sha256, SourceId

CAPTURE_ID = UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")
NOW = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)


def make_batch(*, payload: bytes = b"page", text: str = "agents") -> DiscoveryBatch:
    query = DiscoveryQuery(text=text, limit=10)
    observation = ObservedPaperVersion(
        source_id=SourceId("arxiv"),
        source_item_id="2608.01234",
        source_version_key="2608.01234v1",
        title="A paper",
        abstract="Evidence",
        page_ordinal=0,
        record_ordinal=0,
        normalized_sha256=Sha256("b" * 64),
    )
    record = DiscoveryRecord(
        locator=RecordLocator(
            page_ordinal=0,
            record_ordinal=0,
            source_item_id="2608.01234",
            source_version_key="2608.01234v1",
            raw_record_sha256=Sha256("c" * 64),
        ),
        observation=observation,
    )
    page = DiscoveryPage(
        capture_id=CAPTURE_ID,
        records=(record,),
        raw_payload=payload,
        media_type="application/atom+xml",
        retrieved_at=NOW,
        request_fingerprint=Sha256("d" * 64),
        next_cursor=None,
    )
    return DiscoveryBatch(
        source_id=SourceId("arxiv"),
        query=query,
        pages=(page,),
        records=(observation,),
        issues=(),
    )


def test_prepared_digest_is_deterministic_and_covers_query_locator_and_page() -> None:
    batch = make_batch()
    locator = batch.pages[0].records[0].locator
    digest = prepared_discovery_digest(batch, (locator,))

    assert digest == prepared_discovery_digest(batch, (locator,))
    assert digest != prepared_discovery_digest(make_batch(text="different"), (locator,))
    assert digest != prepared_discovery_digest(make_batch(payload=b"different"), (locator,))
    assert digest != prepared_discovery_digest(batch, (replace(locator, record_ordinal=1),))
    assert digest != prepared_discovery_digest(
        replace(
            batch,
            pages=(
                replace(
                    batch.pages[0],
                    capture_id=UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5b"),
                ),
            ),
        ),
        (locator,),
    )
    crossref_observation = replace(batch.records[0], source_id=SourceId("crossref"))
    crossref_record = replace(batch.pages[0].records[0], observation=crossref_observation)
    crossref_batch = replace(
        batch,
        source_id=SourceId("crossref"),
        pages=(replace(batch.pages[0], records=(crossref_record,)),),
        records=(crossref_observation,),
    )
    assert digest != prepared_discovery_digest(crossref_batch, (locator,))
    assert digest != prepared_discovery_digest(
        replace(
            batch,
            pages=(replace(batch.pages[0], retrieved_at=NOW + timedelta(seconds=1)),),
        ),
        (locator,),
    )
    assert digest != prepared_discovery_digest(
        replace(
            batch,
            pages=(replace(batch.pages[0], request_fingerprint=Sha256("e" * 64)),),
        ),
        (locator,),
    )


def test_discovery_batch_rejects_duplicate_capture_ids() -> None:
    batch = make_batch()
    first_page = batch.pages[0]
    second_observation = replace(
        batch.records[0],
        page_ordinal=1,
        source_item_id="2608.05678",
        source_version_key="2608.05678v1",
    )
    second_locator = replace(
        first_page.records[0].locator,
        page_ordinal=1,
        source_item_id="2608.05678",
        source_version_key="2608.05678v1",
    )
    second_page = replace(
        first_page,
        records=(DiscoveryRecord(second_locator, second_observation),),
    )

    with pytest.raises(ValueError, match="capture"):
        replace(
            batch,
            pages=(first_page, second_page),
            records=(batch.records[0], second_observation),
        )


def test_prepared_discovery_validates_expiry_and_manifest() -> None:
    batch = make_batch()
    prepared = PreparedDiscovery.prepare(
        batch=batch,
        selected_records=(batch.pages[0].records[0].locator,),
        prepared_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )

    assert prepared.preview.digest == prepared.digest
    assert prepared.preview.selected_records == 1

    with pytest.raises(ValueError):
        replace(prepared, expires_at=NOW)
    with pytest.raises(ValueError):
        replace(prepared, digest="0" * 64)
    with pytest.raises(ValueError):
        replace(prepared, preview=replace(prepared.preview, schema_version="future-v2"))
    with pytest.raises(ValueError):
        replace(prepared, preview=replace(prepared.preview, selected_records=0))
    with pytest.raises(ValueError):
        replace(
            prepared,
            preview=replace(
                prepared.preview,
                issues=(DiscoveryIssue(ErrorCode.RECORD_INVALID),),
            ),
        )
    with pytest.raises(ValueError):
        PreparedDiscovery.prepare(
            batch=batch,
            selected_records=(
                batch.pages[0].records[0].locator,
                batch.pages[0].records[0].locator,
            ),
            prepared_at=NOW,
            expires_at=NOW + timedelta(minutes=15),
        )


def test_discovery_batch_rejects_detached_or_inconsistent_records() -> None:
    batch = make_batch()
    with pytest.raises(ValueError):
        replace(batch, records=())
    with pytest.raises(ValueError):
        replace(batch, source_id=SourceId("crossref"))


def test_source_timestamps_must_be_utc() -> None:
    batch = make_batch()
    non_utc = NOW.astimezone(timezone(timedelta(hours=2)))

    with pytest.raises(ValueError):
        replace(batch.pages[0], retrieved_at=non_utc)


def test_selected_records_must_follow_page_order() -> None:
    batch = make_batch()
    first = batch.pages[0].records[0]
    second_observation = replace(
        first.observation,
        source_item_id="2608.09999",
        source_version_key="2608.09999v1",
        record_ordinal=1,
        normalized_sha256=Sha256("e" * 64),
    )
    second = DiscoveryRecord(
        locator=replace(
            first.locator,
            record_ordinal=1,
            source_item_id="2608.09999",
            source_version_key="2608.09999v1",
            raw_record_sha256=Sha256("f" * 64),
        ),
        observation=second_observation,
    )
    page = replace(batch.pages[0], records=(first, second))
    two_records = replace(
        batch,
        pages=(page,),
        records=(first.observation, second_observation),
    )

    with pytest.raises(ValueError):
        PreparedDiscovery.prepare(
            batch=two_records,
            selected_records=(second.locator, first.locator),
            prepared_at=NOW,
            expires_at=NOW + timedelta(minutes=15),
        )


def test_selected_record_requires_a_normalized_observation() -> None:
    batch = make_batch()
    failed = replace(batch.pages[0].records[0], observation=None)
    failed_batch = replace(batch, pages=(replace(batch.pages[0], records=(failed,)),), records=())

    with pytest.raises(ValueError):
        PreparedDiscovery.prepare(
            batch=failed_batch,
            selected_records=(failed.locator,),
            prepared_at=NOW,
            expires_at=NOW + timedelta(minutes=15),
        )
