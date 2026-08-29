from __future__ import annotations

from paper_insights.domain.errors import ERROR_EXIT_CODES, ErrorCode, ExitCode


def test_public_codes_are_unique_and_mapping_is_exhaustive() -> None:
    assert len({item.value for item in ErrorCode}) == len(ErrorCode)
    assert len({item.value for item in ExitCode}) == len(ExitCode)
    assert set(ERROR_EXIT_CODES) == set(ErrorCode)


def test_exit_code_values_are_frozen() -> None:
    assert {item.name: item.value for item in ExitCode} == {
        "SUCCESS": 0,
        "INVALID": 2,
        "CONFIRMATION_REQUIRED": 3,
        "PARTIAL": 4,
        "SOURCE_UNAVAILABLE": 5,
        "CORPUS_INVALID": 6,
    }
