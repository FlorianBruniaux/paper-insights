from __future__ import annotations

from typing import Protocol

from paper_insights.domain.federation import (
    CorpusCapabilities,
    CorpusId,
    EvidenceBundle,
    EvidenceBundleReceipt,
    EvidenceItem,
    EvidenceRef,
    FederatedSearchQuery,
    NativeCorpusResult,
)


class FederatedCorpus(Protocol):
    corpus_id: CorpusId

    def capabilities(self) -> CorpusCapabilities: ...

    def search(self, query: FederatedSearchQuery) -> NativeCorpusResult: ...

    def resolve_evidence(self, ref: EvidenceRef) -> EvidenceItem | None: ...


class EvidenceBundleWriter(Protocol):
    def write(self, bundle: EvidenceBundle) -> EvidenceBundleReceipt: ...
