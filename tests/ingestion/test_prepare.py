from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from paper_insights.application.ingestion.prepare import PrepareDiscovery
from paper_insights.domain.acquisition import (
    DiscoveryBatch,
    DiscoveryPage,
    DiscoveryQuery,
    DiscoveryRecord,
    ObservedPaperVersion,
    RecordLocator,
)
from paper_insights.domain.identifiers import Sha256, SourceId

NOW = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)


class FrozenClock:
    def now(self) -> datetime:
        return NOW


class LocalProvider:
    source_id = SourceId("arxiv")

    def __init__(self, batch: DiscoveryBatch) -> None:
        self._batch = batch
        self.calls = 0
        self.last_query: DiscoveryQuery | None = None

    def discover(self, query: DiscoveryQuery) -> DiscoveryBatch:
        self.calls += 1
        self.last_query = query
        return self._batch


def _batch() -> DiscoveryBatch:
    query = DiscoveryQuery(text="paper agents", limit=2)
    records: list[DiscoveryRecord] = []
    observations: list[ObservedPaperVersion] = []
    for ordinal in range(2):
        source_item_id = f"2608.0000{ordinal + 1}"
        observation = ObservedPaperVersion(
            source_id=SourceId("arxiv"),
            source_item_id=source_item_id,
            source_version_key=f"{source_item_id}v1",
            title=f"Paper {ordinal + 1}",
            abstract=None,
            page_ordinal=0,
            record_ordinal=ordinal,
            normalized_sha256=Sha256(f"{ordinal + 1}" * 64),
        )
        observations.append(observation)
        records.append(
            DiscoveryRecord(
                locator=RecordLocator(
                    page_ordinal=0,
                    record_ordinal=ordinal,
                    source_item_id=source_item_id,
                    source_version_key=f"{source_item_id}v1",
                    raw_record_sha256=Sha256(f"{ordinal + 3}" * 64),
                ),
                observation=observation,
            )
        )
    page = DiscoveryPage(
        capture_id=UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a"),
        records=tuple(records),
        raw_payload=b"local fixture page",
        media_type="application/atom+xml",
        retrieved_at=NOW,
        request_fingerprint=Sha256("f" * 64),
        next_cursor=None,
    )
    return DiscoveryBatch(
        source_id=SourceId("arxiv"),
        query=query,
        pages=(page,),
        records=tuple(observations),
        issues=(),
    )


def test_prepare_calls_provider_once_and_returns_exact_immutable_manifest() -> None:
    batch = _batch()
    provider = LocalProvider(batch)

    prepared = PrepareDiscovery(provider=provider, clock=FrozenClock()).prepare(batch.query)

    assert provider.calls == 1
    assert provider.last_query == batch.query
    assert prepared.batch is batch
    assert prepared.prepared_at == NOW
    assert prepared.expires_at == NOW + timedelta(minutes=15)
    assert prepared.preview.selected_locators == tuple(
        record.locator for page in batch.pages for record in page.records
    )
    assert prepared.preview.selected_records == 2
    assert prepared.preview.digest == prepared.digest


def test_prepare_rejects_a_provider_batch_for_another_query_or_source() -> None:
    batch = _batch()
    wrong_query = DiscoveryBatch(
        source_id=batch.source_id,
        query=DiscoveryQuery(text="different", limit=2),
        pages=batch.pages,
        records=batch.records,
        issues=batch.issues,
    )
    provider = LocalProvider(wrong_query)

    try:
        PrepareDiscovery(provider=provider, clock=FrozenClock()).prepare(batch.query)
    except ValueError as exc:
        assert str(exc) == "provider batch differs from the discovery request"
    else:
        raise AssertionError("mismatched provider batch was accepted")
