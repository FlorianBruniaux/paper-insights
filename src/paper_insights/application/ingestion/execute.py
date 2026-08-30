from __future__ import annotations

import hashlib
from collections.abc import Callable

from paper_insights.application.ports.artifacts import BlobStore
from paper_insights.application.ports.catalog import CatalogUnitOfWorkFactory
from paper_insights.application.ports.clock import Clock
from paper_insights.application.ports.ids import IdGenerator
from paper_insights.domain.acquisition import (
    ObservedPaperVersion,
    PreparedDiscovery,
    RecordLocator,
    prepared_discovery_digest,
)
from paper_insights.domain.corpus import (
    AttachPreparedRun,
    BlobWrite,
    IngestionFailureStage,
    IngestionSummary,
    MetadataBlobRef,
    PreparedSnapshotAttachment,
    RecordIngestionFailure,
    RecordIngestionItem,
    RecordObservation,
    SnapshotRecordAttachment,
)
from paper_insights.domain.errors import ErrorCode
from paper_insights.domain.identifiers import RunId, Sha256

MetadataPayload = Callable[[ObservedPaperVersion], bytes]


class IngestionExecutionError(ValueError):
    def __init__(self, code: ErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


class ExecutePreparedIngestion:
    def __init__(
        self,
        *,
        blobs: BlobStore,
        catalog: CatalogUnitOfWorkFactory,
        clock: Clock,
        ids: IdGenerator,
        metadata_payload: MetadataPayload,
    ) -> None:
        self._blobs = blobs
        self._catalog = catalog
        self._clock = clock
        self._ids = ids
        self._metadata_payload = metadata_payload

    def execute(
        self,
        prepared: PreparedDiscovery,
        *,
        confirmation: Sha256,
    ) -> IngestionSummary:
        self._validate_confirmation(prepared, confirmation)
        metadata = self._validated_metadata(prepared)
        page_blobs = tuple(
            self._blobs.put(BlobWrite(content=page.raw_payload, media_type=page.media_type))
            for page in prepared.batch.pages
        )
        metadata_blobs = {
            locator: MetadataBlobRef(
                blob=self._blobs.put(BlobWrite(content=payload, media_type="application/json")),
                normalized_sha256=Sha256(hashlib.sha256(payload).hexdigest()),
            )
            for locator, payload in metadata.items()
        }
        run_id = RunId(self._ids.new())
        attach = AttachPreparedRun(
            run_id=run_id,
            prepared=prepared,
            pages=tuple(
                PreparedSnapshotAttachment(
                    page_ordinal=page_ordinal,
                    capture_id=page.capture_id,
                    blob=page_blobs[page_ordinal],
                    request_fingerprint=page.request_fingerprint,
                    retrieved_at=page.retrieved_at,
                    next_cursor=page.next_cursor,
                    records=tuple(
                        SnapshotRecordAttachment(locator=record.locator) for record in page.records
                    ),
                )
                for page_ordinal, page in enumerate(prepared.batch.pages)
            ),
        )
        with self._catalog.begin() as unit:
            attached = unit.ingestion.attach_prepared_run(attach)
            unit.commit()

        for locator in prepared.preview.selected_locators:
            source_record = prepared.batch.pages[locator.page_ordinal].records[
                locator.record_ordinal
            ]
            observed = source_record.observation
            if source_record.locator != locator or observed is None:
                raise IngestionExecutionError(ErrorCode.PREVIEW_MISMATCH)
            record = RecordIngestionItem(
                run_id=run_id,
                record=RecordObservation(
                    snapshot_id=attached.snapshot_id_for(locator.page_ordinal),
                    record_ordinal=locator.record_ordinal,
                    observed=observed,
                    metadata_blob=metadata_blobs[locator],
                ),
            )
            failure = self._record_item(record)
            if failure is not None:
                with self._catalog.begin() as unit:
                    unit.ingestion.record_failure(failure)
                    unit.commit()

        with self._catalog.begin() as unit:
            summary = unit.ingestion.finalize_run(run_id)
            unit.commit()
        return summary

    def _validate_confirmation(self, prepared: PreparedDiscovery, confirmation: Sha256) -> None:
        expected = prepared_discovery_digest(
            prepared.batch,
            prepared.preview.selected_locators,
        )
        if confirmation != prepared.digest or expected != prepared.digest:
            raise IngestionExecutionError(ErrorCode.PREVIEW_MISMATCH)
        if self._clock.now() >= prepared.expires_at:
            raise IngestionExecutionError(ErrorCode.PREVIEW_EXPIRED)

    def _validated_metadata(self, prepared: PreparedDiscovery) -> dict[RecordLocator, bytes]:
        result: dict[RecordLocator, bytes] = {}
        for locator in prepared.preview.selected_locators:
            record = prepared.batch.pages[locator.page_ordinal].records[locator.record_ordinal]
            if record.locator != locator or record.observation is None:
                raise IngestionExecutionError(ErrorCode.PREVIEW_MISMATCH)
            try:
                payload = self._metadata_payload(record.observation)
            except (TypeError, ValueError) as exc:
                raise IngestionExecutionError(ErrorCode.ARTIFACT_INVALID) from exc
            digest = Sha256(hashlib.sha256(payload).hexdigest())
            if digest != record.observation.normalized_sha256:
                raise IngestionExecutionError(ErrorCode.ARTIFACT_INVALID)
            result[locator] = payload
        return result

    def _record_item(self, command: RecordIngestionItem) -> RecordIngestionFailure | None:
        code: ErrorCode | None = None
        with self._catalog.begin() as unit:
            try:
                unit.ingestion.record_item(command)
            except Exception as exc:
                code = self._item_failure_code(exc)
                if code is None:
                    raise
                unit.rollback()
            else:
                unit.commit()
        if code is None:
            return None
        return RecordIngestionFailure.from_code(
            run_id=command.run_id,
            snapshot_id=command.record.snapshot_id,
            record_ordinal=command.record.record_ordinal,
            stage=IngestionFailureStage.CATALOG_WRITE,
            code=code,
            occurred_at=self._clock.now(),
        )

    @staticmethod
    def _item_failure_code(error: Exception) -> ErrorCode | None:
        if isinstance(error, ValueError):
            return ErrorCode.RECORD_INVALID
        if error.args == (ErrorCode.CATALOG_CONFLICT.value,):
            return ErrorCode.CATALOG_CONFLICT
        return None
