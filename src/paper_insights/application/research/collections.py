from __future__ import annotations

from paper_insights.application.ports.catalog import CatalogReader, CatalogUnitOfWorkFactory
from paper_insights.domain.corpus import (
    AddCollectionPaper,
    CollectionView,
    CreateCollection,
    RemoveCollectionPaper,
    RenameCollection,
)
from paper_insights.domain.identifiers import CollectionId, PaperSelector


class CollectionService:
    def __init__(self, unit_of_work: CatalogUnitOfWorkFactory, reader: CatalogReader) -> None:
        self._unit_of_work = unit_of_work
        self._reader = reader

    def create(self, *, slug: str, title: str) -> CollectionView:
        with self._unit_of_work.begin() as uow:
            collection = uow.collections.create(CreateCollection(slug=slug, title=title))
            uow.commit()
        return collection

    def rename(self, collection_id: CollectionId, *, title: str) -> CollectionView:
        with self._unit_of_work.begin() as uow:
            collection = uow.collections.rename(
                RenameCollection(collection_id=collection_id, title=title)
            )
            uow.commit()
        return collection

    def add(
        self,
        collection_id: CollectionId,
        paper: PaperSelector,
        *,
        note: str | None = None,
    ) -> CollectionView:
        with self._unit_of_work.begin() as uow:
            collection = uow.collections.add(
                AddCollectionPaper(collection_id=collection_id, selector=paper, note=note)
            )
            uow.commit()
        return collection

    def remove(self, collection_id: CollectionId, paper: PaperSelector) -> CollectionView:
        with self._unit_of_work.begin() as uow:
            collection = uow.collections.remove(
                RemoveCollectionPaper(collection_id=collection_id, selector=paper)
            )
            uow.commit()
        return collection

    def list(self) -> tuple[CollectionView, ...]:
        with self._reader.snapshot() as snapshot:
            collections = snapshot.list_collections()
        return collections
