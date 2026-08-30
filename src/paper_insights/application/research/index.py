from __future__ import annotations

from dataclasses import dataclass

from paper_insights.application.ports.catalog import CatalogReader, CatalogRevisionGuard
from paper_insights.application.ports.search import SearchIndexBuilder
from paper_insights.domain.retrieval import IndexBuildRequest, PublishedIndex


@dataclass(frozen=True, slots=True)
class RebuildSearchIndex:
    catalog: CatalogReader
    builder: SearchIndexBuilder
    revision_guard: CatalogRevisionGuard

    def execute(self, *, chunk_schema_version: str) -> PublishedIndex:
        with self.catalog.snapshot() as snapshot:
            request = IndexBuildRequest(
                documents=snapshot.list_index_documents(),
                catalog_revision=snapshot.revision,
                chunk_schema_version=chunk_schema_version,
            )
        candidate = self.builder.build_candidate(request)
        try:
            published: PublishedIndex | None = None
            with self.revision_guard.hold_if_current(request.catalog_revision) as lease:
                published = self.builder.publish(candidate, lease)
            if published is None:
                raise RuntimeError("catalog revision lease suppressed search publication")
            return published
        except BaseException as primary_error:
            try:
                self.builder.discard(candidate)
            except BaseException as cleanup_error:
                primary_error.add_note(
                    f"search candidate cleanup failed: {type(cleanup_error).__name__}"
                )
            raise
