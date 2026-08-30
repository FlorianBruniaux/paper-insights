"""Synchronous application ports."""

from paper_insights.application.ports.analysis import (
    AnalysisBackend,
    AnalysisUnitOfWork,
    AnalysisUnitOfWorkFactory,
    FullTextProvider,
    TextExtractor,
)
from paper_insights.application.ports.artifacts import BlobStore
from paper_insights.application.ports.catalog import (
    CatalogReader,
    CatalogRevisionGuard,
    CatalogRevisionLease,
    CatalogSnapshot,
    CatalogUnitOfWork,
    CatalogUnitOfWorkFactory,
    CollectionRepository,
    CorpusRepository,
    IngestionRepository,
)
from paper_insights.application.ports.citations import CitationRenderer
from paper_insights.application.ports.clock import Clock
from paper_insights.application.ports.discovery import DiscoveryProvider
from paper_insights.application.ports.federation import EvidenceBundleWriter, FederatedCorpus
from paper_insights.application.ports.identity import (
    IdentityProvider,
    IdentityUnitOfWork,
    IdentityUnitOfWorkFactory,
)
from paper_insights.application.ports.ids import IdGenerator
from paper_insights.application.ports.monitoring import (
    WatchlistUnitOfWork,
    WatchlistUnitOfWorkFactory,
)
from paper_insights.application.ports.search import SearchIndexBuilder, SearchIndexReader

__all__ = (
    "AnalysisBackend",
    "AnalysisUnitOfWork",
    "AnalysisUnitOfWorkFactory",
    "BlobStore",
    "CatalogReader",
    "CatalogRevisionGuard",
    "CatalogRevisionLease",
    "CatalogSnapshot",
    "CatalogUnitOfWork",
    "CatalogUnitOfWorkFactory",
    "CitationRenderer",
    "Clock",
    "CollectionRepository",
    "CorpusRepository",
    "DiscoveryProvider",
    "EvidenceBundleWriter",
    "FederatedCorpus",
    "FullTextProvider",
    "IdGenerator",
    "IdentityProvider",
    "IdentityUnitOfWork",
    "IdentityUnitOfWorkFactory",
    "IngestionRepository",
    "SearchIndexBuilder",
    "SearchIndexReader",
    "TextExtractor",
    "WatchlistUnitOfWork",
    "WatchlistUnitOfWorkFactory",
)
