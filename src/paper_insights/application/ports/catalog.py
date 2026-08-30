from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import Protocol

from paper_insights.domain.corpus import (
    AddCollectionPaper,
    AttachPreparedRun,
    CitationInput,
    CitationSelector,
    CollectionView,
    CreateCollection,
    IngestionItemRef,
    IngestionRunRef,
    IngestionSummary,
    InterruptedRunCandidate,
    InterruptedRunRepairResult,
    PaperIdentity,
    PaperView,
    RecordIngestionFailure,
    RecordIngestionItem,
    RemoveCollectionPaper,
    RenameCollection,
    RepairInterruptedRun,
)
from paper_insights.domain.identifiers import PaperSelector, RunId
from paper_insights.domain.retrieval import CatalogRevision, IndexDocument


class CorpusRepository(Protocol):
    def resolve_paper(self, selector: PaperSelector) -> PaperIdentity | None: ...


class IngestionRepository(Protocol):
    def attach_prepared_run(self, command: AttachPreparedRun) -> IngestionRunRef: ...

    def record_item(self, command: RecordIngestionItem) -> IngestionItemRef: ...

    def record_failure(self, command: RecordIngestionFailure) -> IngestionItemRef: ...

    def repair_interrupted_run(
        self, command: RepairInterruptedRun
    ) -> InterruptedRunRepairResult: ...

    def finalize_run(self, run_id: RunId) -> IngestionSummary: ...


class CollectionRepository(Protocol):
    def create(self, command: CreateCollection) -> CollectionView: ...

    def rename(self, command: RenameCollection) -> CollectionView: ...

    def add(self, command: AddCollectionPaper) -> CollectionView: ...

    def remove(self, command: RemoveCollectionPaper) -> CollectionView: ...


class CatalogUnitOfWork(Protocol):
    corpus: CorpusRepository
    ingestion: IngestionRepository
    collections: CollectionRepository

    def __enter__(self) -> CatalogUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class CatalogUnitOfWorkFactory(Protocol):
    def begin(self) -> CatalogUnitOfWork: ...


class CatalogSnapshot(Protocol):
    revision: CatalogRevision

    def __enter__(self) -> CatalogSnapshot: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...

    def get_paper(self, selector: PaperSelector) -> PaperView | None: ...

    def list_index_documents(self) -> tuple[IndexDocument, ...]: ...

    def list_collections(self) -> tuple[CollectionView, ...]: ...

    def list_interrupted_runs(self, cutoff: datetime) -> tuple[InterruptedRunCandidate, ...]: ...

    def get_citation_input(self, selector: CitationSelector) -> CitationInput | None: ...


class CatalogReader(Protocol):
    def snapshot(self) -> CatalogSnapshot: ...


class CatalogRevisionLease(Protocol):
    revision: CatalogRevision

    def __enter__(self) -> CatalogRevisionLease: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...


class CatalogRevisionGuard(Protocol):
    def hold_if_current(self, expected: CatalogRevision) -> CatalogRevisionLease: ...
