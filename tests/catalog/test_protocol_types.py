from __future__ import annotations

from pathlib import Path

import pytest
from mypy import api as mypy_api


def test_concrete_catalog_uow_types_satisfy_protocols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = Path(__file__).with_name("protocol_probe.py")
    monkeypatch.setenv("MYPYPATH", str(Path(__file__).resolve().parents[2] / "src"))

    stdout, stderr, status = mypy_api.run(["--strict", str(probe)])

    assert status == 0, stdout + stderr
