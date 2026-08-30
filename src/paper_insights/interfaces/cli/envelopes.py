from __future__ import annotations

from typing import Literal

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


class CoverageEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["complete", "partial", "unavailable", "unknown"]


class CliEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["paper-insights.cli.v1"]
    operation: CliOperation
    data: dict[str, object]
    coverage: CoverageEnvelope
    errors: list[str] = Field(default_factory=list)
    truncated: bool = False
    returned: int | None = Field(default=None, ge=0)
    available: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> CliEnvelope:
        if self.returned is None and self.available is not None:
            raise ValueError("available requires returned")
        if self.returned is not None and self.available is not None:
            if self.available < self.returned:
                raise ValueError("available cannot be less than returned")
        return self


class ErrorData(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: str = Field(min_length=1)


class CliErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["paper-insights.error.v1"]
    error: ErrorData
