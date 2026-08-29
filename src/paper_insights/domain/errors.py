from __future__ import annotations

from enum import Enum, IntEnum


class ErrorCode(str, Enum):
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


ERROR_EXIT_CODES: dict[ErrorCode, ExitCode] = {
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
