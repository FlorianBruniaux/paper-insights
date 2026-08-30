from __future__ import annotations

from collections.abc import Mapping
from enum import IntEnum, StrEnum
from types import MappingProxyType


class ErrorCode(StrEnum):
    SOURCE_CONNECTION_FAILED = "source_connection_failed"
    SOURCE_TIMEOUT = "source_timeout"
    SOURCE_RATE_LIMITED = "source_rate_limited"
    SOURCE_RESPONSE_TOO_LARGE = "source_response_too_large"
    SOURCE_INVALID_PAYLOAD = "source_invalid_payload"
    SOURCE_REDIRECT_REFUSED = "source_redirect_refused"
    RECORD_INVALID = "record_invalid"
    ARTIFACT_INVALID = "artifact_invalid"
    CATALOG_CONFLICT = "catalog_conflict"
    PREVIEW_EXPIRED = "preview_expired"
    PREVIEW_MISMATCH = "preview_mismatch"
    INTERRUPTED = "interrupted"


class ExitCode(IntEnum):
    SUCCESS = 0
    INVALID = 2
    CONFIRMATION_REQUIRED = 3
    PARTIAL = 4
    SOURCE_UNAVAILABLE = 5
    CORPUS_INVALID = 6


PUBLIC_ERROR_MESSAGES: Mapping[ErrorCode, str] = MappingProxyType(
    {
        ErrorCode.SOURCE_CONNECTION_FAILED: "source connection failed",
        ErrorCode.SOURCE_TIMEOUT: "source timeout",
        ErrorCode.SOURCE_RATE_LIMITED: "source rate limited",
        ErrorCode.SOURCE_RESPONSE_TOO_LARGE: "source response too large",
        ErrorCode.SOURCE_INVALID_PAYLOAD: "source payload invalid",
        ErrorCode.SOURCE_REDIRECT_REFUSED: "source redirect refused",
        ErrorCode.RECORD_INVALID: "record invalid",
        ErrorCode.ARTIFACT_INVALID: "artifact invalid",
        ErrorCode.CATALOG_CONFLICT: "catalog conflict",
        ErrorCode.PREVIEW_EXPIRED: "preview expired",
        ErrorCode.PREVIEW_MISMATCH: "preview mismatch",
        ErrorCode.INTERRUPTED: "record interrupted before completion",
    }
)


ERROR_EXIT_CODES: dict[ErrorCode, ExitCode] = {
    ErrorCode.SOURCE_CONNECTION_FAILED: ExitCode.SOURCE_UNAVAILABLE,
    ErrorCode.SOURCE_TIMEOUT: ExitCode.SOURCE_UNAVAILABLE,
    ErrorCode.SOURCE_RATE_LIMITED: ExitCode.SOURCE_UNAVAILABLE,
    ErrorCode.SOURCE_RESPONSE_TOO_LARGE: ExitCode.SOURCE_UNAVAILABLE,
    ErrorCode.SOURCE_INVALID_PAYLOAD: ExitCode.SOURCE_UNAVAILABLE,
    ErrorCode.SOURCE_REDIRECT_REFUSED: ExitCode.SOURCE_UNAVAILABLE,
    ErrorCode.RECORD_INVALID: ExitCode.CORPUS_INVALID,
    ErrorCode.ARTIFACT_INVALID: ExitCode.CORPUS_INVALID,
    ErrorCode.CATALOG_CONFLICT: ExitCode.CORPUS_INVALID,
    ErrorCode.PREVIEW_EXPIRED: ExitCode.INVALID,
    ErrorCode.PREVIEW_MISMATCH: ExitCode.INVALID,
    ErrorCode.INTERRUPTED: ExitCode.CORPUS_INVALID,
}
