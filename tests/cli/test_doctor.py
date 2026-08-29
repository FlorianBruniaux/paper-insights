from __future__ import annotations

import io
import json
import socket
import sqlite3
from pathlib import Path

import pytest

from paper_insights.adapters.artifacts.filesystem.store import FilesystemBlobStore
from paper_insights.domain.corpus import BlobWrite
from paper_insights.interfaces.cli.app import main
from paper_insights.paths import CorpusPaths


def _tree_snapshot(root: Path) -> tuple[tuple[str, int, int, int], ...]:
    if not root.exists():
        return ()
    return tuple(
        sorted(
            (
                path.relative_to(root).as_posix(),
                path.lstat().st_mode,
                path.lstat().st_size,
                path.lstat().st_mtime_ns,
            )
            for path in root.rglob("*")
        )
    )


def test_doctor_json_on_absent_root_is_read_only_and_network_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "absent"
    stdout = io.StringIO()
    stderr = io.StringIO()

    def reject_network(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("doctor attempted network access")

    monkeypatch.setattr(socket, "socket", reject_network)

    exit_code = main(
        ["doctor", "--json"],
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(data_root)},
        stdout=stdout,
        stderr=stderr,
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload == {
        "coverage": {"status": "unknown"},
        "data": {
            "checks": [
                {"code": "data_root_absent", "name": "data_root", "status": "UNKNOWN"},
                {"code": "catalog_unavailable", "name": "catalog", "status": "UNKNOWN"},
                {"code": "orphan_proof_unavailable", "name": "orphaned_blobs", "status": "UNKNOWN"},
            ],
            "orphaned_blob_count": None,
            "status": "UNKNOWN",
        },
        "errors": [],
        "operation": "doctor",
        "schema_version": "paper-insights.cli.v1",
        "truncated": False,
    }
    assert stderr.getvalue() == ""
    assert not data_root.exists()


def test_doctor_reports_orphaned_blob_without_mutating_corpus(tmp_path: Path) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    store = FilesystemBlobStore(paths)
    referenced = store.put(BlobWrite(content=b"referenced", media_type="text/plain"))
    orphan = store.put(BlobWrite(content=b"orphan", media_type="text/plain"))
    connection = sqlite3.connect(paths.catalog)
    connection.execute(
        "CREATE TABLE stored_blobs (sha256 TEXT NOT NULL, relative_path TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO stored_blobs (sha256, relative_path) VALUES (?, ?)",
        (str(referenced.sha256), referenced.relative_path.as_posix()),
    )
    connection.commit()
    connection.close()
    before = _tree_snapshot(paths.data_root)
    stdout = io.StringIO()

    exit_code = main(
        ["doctor", "--json"],
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(paths.data_root)},
        stdout=stdout,
        stderr=io.StringIO(),
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["data"]["status"] == "OK"
    assert payload["data"]["orphaned_blob_count"] == 1
    assert payload["data"]["checks"][-1] == {
        "code": "orphaned_blobs_found",
        "name": "orphaned_blobs",
        "status": "OK",
    }
    assert _tree_snapshot(paths.data_root) == before
    assert paths.confined(orphan.relative_path).exists()
    assert not tuple(paths.data_root.rglob("*-wal"))
    assert not tuple(paths.data_root.rglob("*-shm"))


def test_doctor_invalid_configuration_does_not_echo_secret_value(tmp_path: Path) -> None:
    credential_value = "".join(("super", "-secret-token-value"))
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = main(
        ["doctor", "--json"],
        environ={
            "PAPER_INSIGHTS_DATA_ROOT": str(tmp_path / "corpus"),
            "PAPER_INSIGHTS_API_TOKEN": credential_value,
        },
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert credential_value not in stderr.getvalue()
    assert json.loads(stderr.getvalue()) == {
        "error": {"code": "invalid_configuration"},
        "schema_version": "paper-insights.error.v1",
    }
    assert not (tmp_path / "corpus").exists()


def test_doctor_identifies_non_directory_data_root(tmp_path: Path) -> None:
    data_root = tmp_path / "not-a-directory"
    data_root.write_text("invalid", encoding="utf-8")
    stdout = io.StringIO()

    exit_code = main(
        ["doctor", "--json"],
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(data_root)},
        stdout=stdout,
        stderr=io.StringIO(),
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code == 6
    assert payload["data"]["checks"][0] == {
        "code": "data_root_invalid",
        "name": "data_root",
        "status": "INVALID",
    }


def test_doctor_fails_closed_without_touching_a_live_wal(tmp_path: Path) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    paths.data_root.mkdir()
    connection = sqlite3.connect(paths.catalog)
    assert connection.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    connection.execute(
        "CREATE TABLE stored_blobs (sha256 TEXT NOT NULL, relative_path TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO stored_blobs (sha256, relative_path) VALUES (?, ?)",
        ("a" * 64, "blobs/aa/aa/" + "a" * 64 + ".blob"),
    )
    connection.commit()
    assert Path(f"{paths.catalog}-wal").stat().st_size > 0
    before = _tree_snapshot(paths.data_root)
    stdout = io.StringIO()

    try:
        exit_code = main(
            ["doctor", "--json"],
            environ={"PAPER_INSIGHTS_DATA_ROOT": str(paths.data_root)},
            stdout=stdout,
            stderr=io.StringIO(),
        )
        after = _tree_snapshot(paths.data_root)
    finally:
        connection.close()

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert payload["data"]["status"] == "UNKNOWN"
    assert payload["data"]["checks"][1] == {
        "code": "catalog_wal_unchecked",
        "name": "catalog",
        "status": "UNKNOWN",
    }
    assert after == before
