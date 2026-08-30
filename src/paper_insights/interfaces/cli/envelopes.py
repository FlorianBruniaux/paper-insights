from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CliOperation = Literal[
    "discover",
    "ingest",
    "collections.create",
    "collections.rename",
    "collections.add",
    "collections.remove",
    "collections.list",
    "search.papers",
    "search.passages",
    "index.rebuild",
    "cite",
    "repair.interrupted-runs",
]
PublicCliErrorCode = Literal[
    "invalid_configuration",
    "invalid_request",
    "runtime_unavailable",
    "corpus_unavailable",
    "source_connection_failed",
    "source_timeout",
    "source_rate_limited",
    "source_response_too_large",
    "source_invalid_payload",
    "source_redirect_refused",
    "record_invalid",
    "artifact_invalid",
    "catalog_conflict",
    "preview_expired",
    "preview_mismatch",
    "interrupted",
]


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DiscoveryQueryData(_ClosedModel):
    authors: list[str]
    categories: list[str]
    cursor: str | None
    date_from: str | None
    date_to: str | None
    identifiers: list[str]
    limit: int = Field(ge=1)
    text: str | None


class LocatorData(_ClosedModel):
    page_ordinal: int = Field(ge=0)
    raw_record_sha256: str
    record_ordinal: int = Field(ge=0)
    source_item_id: str | None
    source_version_key: str | None


class DiscoveryIssueData(_ClosedModel):
    code: str
    message: str
    page_ordinal: int | None
    record_ordinal: int | None


class DiscoveryPreviewData(_ClosedModel):
    schema_version: Literal["discovery-preview-v1"]
    source_id: str
    query: DiscoveryQueryData
    requested_records: int = Field(ge=0)
    discovered_records: int = Field(ge=0)
    selected_records: int = Field(ge=0)
    selected_locators: list[LocatorData]
    issues: list[DiscoveryIssueData]
    prepared_at: str
    expires_at: str
    digest: str


class AuthorData(_ClosedModel):
    raw_name: str
    given_name: str | None
    family_name: str | None
    affiliation_raw: str | None


class CategoryData(_ClosedModel):
    value: str
    is_primary: bool


class IdentifierData(_ClosedModel):
    scheme: str
    canonical_value: str
    scope: Literal["paper", "version"]


class DiscoveryRecordData(_ClosedModel):
    source_id: str
    source_item_id: str
    source_version_key: str
    title: str
    abstract: str | None
    authors: list[AuthorData]
    categories: list[CategoryData]
    identifiers: list[IdentifierData]
    page_ordinal: int = Field(ge=0)
    record_ordinal: int = Field(ge=0)
    source_url: str | None


class DiscoverData(_ClosedModel):
    preview: DiscoveryPreviewData
    records: list[DiscoveryRecordData]


class IngestionCountersData(_ClosedModel):
    selected_records: int = Field(ge=0)
    new_papers: int = Field(ge=0)
    new_versions: int = Field(ge=0)
    metadata_updates: int = Field(ge=0)
    unchanged_records: int = Field(ge=0)
    failed_records: int = Field(ge=0)
    status: Literal["succeeded", "partial", "failed"]


class IngestionResultData(_ClosedModel):
    run_id: str
    counters: IngestionCountersData


class CollectionData(_ClosedModel):
    collection_id: str
    slug: str
    title: str
    paper_count: int = Field(ge=0)
    created_at: str
    updated_at: str


class CollectionResultData(_ClosedModel):
    collection: CollectionData


class CollectionListData(_ClosedModel):
    collections: list[CollectionData]


class PaperHitData(_ClosedModel):
    paper_id: str
    paper_version_id: str
    version_observation_id: str
    title: str
    rank: int = Field(ge=1)
    bm25_score: float
    artifact_sha256: str
    source_id: str
    authors: list[str]
    identifiers: list[IdentifierData]


class PassageHitData(_ClosedModel):
    passage_id: str
    paper_id: str
    paper_version_id: str
    version_observation_id: str
    rank: int = Field(ge=1)
    bm25_score: float
    excerpt: str
    section: str | None
    ordinal: int = Field(ge=0)


class PaperSearchData(_ClosedModel):
    catalog_revision: int = Field(ge=0)
    index_revision: int = Field(ge=0)
    applied_limit: int = Field(ge=1)
    hits: list[PaperHitData]


class PassageSearchData(_ClosedModel):
    catalog_revision: int = Field(ge=0)
    index_revision: int = Field(ge=0)
    applied_limit: int = Field(ge=1)
    hits: list[PassageHitData]


class PublishedIndexData(_ClosedModel):
    path: str
    catalog_revision: int = Field(ge=0)
    generation: int = Field(ge=0)


class CitationData(_ClosedModel):
    schema_version: Literal["citation-v1"]
    paper_id: str
    paper_version_id: str
    version_observation_id: str
    format: Literal["bibtex", "markdown", "csl-json"]
    media_type: str
    content: str
    missing_fields: list[str]
    source_id: str
    source_item_id: str
    snapshot_id: str
    record_ordinal: int = Field(ge=0)
    retrieved_at: str
    coverage: Literal["complete", "partial", "unavailable", "unknown"]
    warnings: list[str]


class RepairCandidateData(_ClosedModel):
    run_id: str
    started_at: str
    selected_records: int = Field(ge=0)
    recorded_items: int = Field(ge=0)


class RepairPreviewData(_ClosedModel):
    cutoff: str
    candidates: list[RepairCandidateData]


class RepairResultData(_ClosedModel):
    run_id: str
    outcome: Literal["repaired", "not_eligible"]
    revision: int = Field(ge=0)


class RepairResultsData(_ClosedModel):
    results: list[RepairResultData]


EnvelopeData = (
    DiscoverData
    | IngestionResultData
    | CollectionResultData
    | CollectionListData
    | PaperSearchData
    | PassageSearchData
    | PublishedIndexData
    | CitationData
    | RepairPreviewData
    | RepairResultsData
)


class CoverageEnvelope(_ClosedModel):
    status: Literal["complete", "partial", "unavailable", "unknown"]


class SuccessError(_ClosedModel):
    code: Literal["ingestion_items_failed"]
    count: int = Field(gt=0)


class CliEnvelope(_ClosedModel):
    _DATA_TYPES: ClassVar[dict[str, tuple[type[BaseModel], ...]]] = {
        "discover": (DiscoverData,),
        "ingest": (DiscoverData, IngestionResultData),
        "collections.create": (CollectionResultData,),
        "collections.rename": (CollectionResultData,),
        "collections.add": (CollectionResultData,),
        "collections.remove": (CollectionResultData,),
        "collections.list": (CollectionListData,),
        "search.papers": (PaperSearchData,),
        "search.passages": (PassageSearchData,),
        "index.rebuild": (PublishedIndexData,),
        "cite": (CitationData,),
        "repair.interrupted-runs": (RepairPreviewData, RepairResultsData),
    }

    schema_version: Literal["paper-insights.cli.v1"]
    operation: CliOperation
    data: EnvelopeData
    coverage: CoverageEnvelope
    errors: list[SuccessError] = Field(default_factory=list)
    truncated: bool = False
    returned: int | None = Field(default=None, ge=0)
    available: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_operation_shape(self) -> CliEnvelope:
        if not isinstance(self.data, self._DATA_TYPES[self.operation]):
            raise ValueError("operation data type is unsupported")
        is_search = self.operation in {"search.papers", "search.passages"}
        if is_search != (self.returned is not None):
            raise ValueError("search operations require result counters")
        if not is_search and (self.available is not None or self.truncated):
            raise ValueError("non-search operations cannot expose search counters")
        if self.returned is not None and self.available is not None:
            if self.available < self.returned:
                raise ValueError("available cannot be less than returned")
        if self.errors and self.operation != "ingest":
            raise ValueError("recorded item errors belong only to ingestion")
        return self


class ErrorData(_ClosedModel):
    code: PublicCliErrorCode


class CliErrorEnvelope(_ClosedModel):
    schema_version: Literal["paper-insights.error.v1"]
    error: ErrorData
