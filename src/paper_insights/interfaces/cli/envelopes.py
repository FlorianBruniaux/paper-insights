from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

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


class CoverageEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["complete", "partial", "unavailable", "unknown"]


class SuccessError(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: Literal["ingestion_items_failed"]
    count: int = Field(gt=0)


class CliEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    _DATA_SHAPES: ClassVar[dict[str, tuple[frozenset[str], ...]]] = {
        "discover": (frozenset({"preview", "records"}),),
        "ingest": (
            frozenset({"preview", "records"}),
            frozenset({"run_id", "counters"}),
        ),
        "collections.create": (frozenset({"collection"}),),
        "collections.rename": (frozenset({"collection"}),),
        "collections.add": (frozenset({"collection"}),),
        "collections.remove": (frozenset({"collection"}),),
        "collections.list": (frozenset({"collections"}),),
        "search.papers": (
            frozenset({"catalog_revision", "index_revision", "applied_limit", "hits"}),
        ),
        "search.passages": (
            frozenset({"catalog_revision", "index_revision", "applied_limit", "hits"}),
        ),
        "index.rebuild": (frozenset({"path", "catalog_revision", "generation"}),),
        "cite": (
            frozenset(
                {
                    "schema_version",
                    "paper_id",
                    "paper_version_id",
                    "version_observation_id",
                    "format",
                    "media_type",
                    "content",
                    "missing_fields",
                    "source_id",
                    "source_item_id",
                    "snapshot_id",
                    "record_ordinal",
                    "retrieved_at",
                    "coverage",
                    "warnings",
                }
            ),
        ),
        "repair.interrupted-runs": (
            frozenset({"cutoff", "candidates"}),
            frozenset({"results"}),
        ),
    }

    schema_version: Literal["paper-insights.cli.v1"]
    operation: CliOperation
    data: dict[str, JsonValue]
    coverage: CoverageEnvelope
    errors: list[SuccessError] = Field(default_factory=list)
    truncated: bool = False
    returned: int | None = Field(default=None, ge=0)
    available: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_operation_shape(self) -> CliEnvelope:
        if frozenset(self.data) not in self._DATA_SHAPES[self.operation]:
            raise ValueError("operation data keys are incomplete or unsupported")
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


class ErrorData(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: PublicCliErrorCode


class CliErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["paper-insights.error.v1"]
    error: ErrorData
