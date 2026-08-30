from __future__ import annotations

import io
import json
import os
import socket
import sqlite3
from pathlib import Path

import pytest

from paper_insights.adapters.artifacts.filesystem.store import FilesystemBlobStore
from paper_insights.adapters.diagnostics.sqlite import SqliteCatalogDiagnostics
from paper_insights.bootstrap import main
from paper_insights.domain.corpus import BlobWrite
from paper_insights.domain.identifiers import Sha256
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


def _create_catalog(paths: CorpusPaths, rows: tuple[tuple[str, int, str, str], ...]) -> None:
    connection = sqlite3.connect(paths.catalog)
    connection.execute(
        "CREATE TABLE stored_blobs ("
        "sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, "
        "media_type TEXT NOT NULL, relative_path TEXT NOT NULL)"
    )
    connection.executemany(
        "INSERT INTO stored_blobs (sha256, size_bytes, media_type, relative_path) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )
    connection.commit()
    connection.close()


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
    assert exit_code == 6
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
    _create_catalog(
        paths,
        (
            (
                str(referenced.sha256),
                referenced.size_bytes,
                referenced.media_type,
                referenced.relative_path.as_posix(),
            ),
        ),
    )
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


@pytest.mark.parametrize("blob_state", ["missing", "corrupt"])
def test_doctor_fails_closed_for_an_invalid_referenced_blob(
    tmp_path: Path, blob_state: str
) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    store = FilesystemBlobStore(paths)
    ref = store.put(BlobWrite(content=b"trusted", media_type="text/plain"))
    if blob_state == "missing":
        paths.confined(ref.relative_path).unlink()
    else:
        paths.confined(ref.relative_path).write_bytes(b"corrupt")
    _create_catalog(
        paths,
        ((str(ref.sha256), ref.size_bytes, ref.media_type, ref.relative_path.as_posix()),),
    )
    before = _tree_snapshot(paths.data_root)
    stdout = io.StringIO()

    exit_code = main(
        ["doctor", "--json"],
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(paths.data_root)},
        stdout=stdout,
        stderr=io.StringIO(),
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code == 6
    assert payload["data"]["status"] == "INVALID"
    assert payload["data"]["checks"][-1] == {
        "code": f"referenced_blob_{blob_state}",
        "name": "referenced_blobs",
        "status": "INVALID",
    }
    assert _tree_snapshot(paths.data_root) == before


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
        "CREATE TABLE stored_blobs ("
        "sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, "
        "media_type TEXT NOT NULL, relative_path TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO stored_blobs (sha256, size_bytes, media_type, relative_path) "
        "VALUES (?, ?, ?, ?)",
        ("a" * 64, 1, "application/octet-stream", "blobs/aa/aa/" + "a" * 64 + ".blob"),
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
    assert exit_code == 6
    assert payload["data"]["status"] == "UNKNOWN"
    assert payload["data"]["checks"][1] == {
        "code": "catalog_wal_unchecked",
        "name": "catalog",
        "status": "UNKNOWN",
    }
    assert after == before


def test_catalog_diagnostic_reports_unknown_when_read_access_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    paths.data_root.mkdir()
    _create_catalog(paths, ())

    def deny_catalog_read(catalog: Path) -> tuple[object, ...]:
        raise PermissionError("injected catalog access denial")

    monkeypatch.setattr(
        SqliteCatalogDiagnostics, "_read_references", staticmethod(deny_catalog_read)
    )

    probe = SqliteCatalogDiagnostics(paths).inspect()

    assert probe.status == "UNKNOWN"
    assert probe.checks[-1].status == "UNKNOWN"
    assert probe.checks[-1].code == "catalog_read_unavailable"


def test_catalog_diagnostic_reports_invalid_when_corruption_is_proven(tmp_path: Path) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    paths.data_root.mkdir()
    paths.catalog.write_bytes(b"this is not a sqlite catalog")

    probe = SqliteCatalogDiagnostics(paths).inspect()

    assert probe.status == "INVALID"
    assert probe.checks[-1].status == "INVALID"
    assert probe.checks[-1].code == "catalog_read_failed"


def test_doctor_reports_unknown_when_a_referenced_blob_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    store = FilesystemBlobStore(paths)
    ref = store.put(BlobWrite(content=b"referenced", media_type="text/plain"))
    _create_catalog(
        paths,
        ((str(ref.sha256), ref.size_bytes, ref.media_type, ref.relative_path.as_posix()),),
    )
    real_open = os.open

    def deny_blob_open(
        path: str | bytes | Path, flags: int, *args: object, **kwargs: object
    ) -> int:
        if path == ref.relative_path.name and kwargs.get("dir_fd") is not None:
            raise PermissionError("injected blob access denial")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", deny_blob_open)
    stdout = io.StringIO()

    exit_code = main(
        ["doctor", "--json"],
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(paths.data_root)},
        stdout=stdout,
        stderr=io.StringIO(),
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code == 6
    assert payload["data"]["status"] == "UNKNOWN"
    assert payload["data"]["checks"][-1] == {
        "code": "referenced_blob_unavailable",
        "name": "referenced_blobs",
        "status": "UNKNOWN",
    }


def test_doctor_reports_invalid_for_a_stable_blob_tree_symlink(tmp_path: Path) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    store = FilesystemBlobStore(paths)
    ref = store.put(BlobWrite(content=b"referenced", media_type="text/plain"))
    _create_catalog(
        paths,
        ((str(ref.sha256), ref.size_bytes, ref.media_type, ref.relative_path.as_posix()),),
    )
    moved = tmp_path / "moved-blobs"
    outside = tmp_path / "outside"
    outside.mkdir()
    paths.blobs.rename(moved)
    paths.blobs.symlink_to(outside, target_is_directory=True)
    stdout = io.StringIO()

    exit_code = main(
        ["doctor", "--json"],
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(paths.data_root)},
        stdout=stdout,
        stderr=io.StringIO(),
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code == 6
    assert payload["data"]["status"] == "INVALID"
    assert payload["data"]["checks"][-1] == {
        "code": "referenced_blob_corrupt",
        "name": "referenced_blobs",
        "status": "INVALID",
    }


def test_doctor_reports_invalid_for_a_stable_blob_file_symlink(tmp_path: Path) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    store = FilesystemBlobStore(paths)
    ref = store.put(BlobWrite(content=b"referenced", media_type="text/plain"))
    _create_catalog(
        paths,
        ((str(ref.sha256), ref.size_bytes, ref.media_type, ref.relative_path.as_posix()),),
    )
    target = paths.confined(ref.relative_path)
    moved = tmp_path / "moved-blob"
    outside = tmp_path / "outside-blob"
    outside.write_bytes(b"outside")
    target.rename(moved)
    target.symlink_to(outside)
    stdout = io.StringIO()

    exit_code = main(
        ["doctor", "--json"],
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(paths.data_root)},
        stdout=stdout,
        stderr=io.StringIO(),
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code == 6
    assert payload["data"]["status"] == "INVALID"
    assert payload["data"]["checks"][-1] == {
        "code": "referenced_blob_corrupt",
        "name": "referenced_blobs",
        "status": "INVALID",
    }


def test_doctor_reports_unknown_when_orphan_scan_binding_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    store = FilesystemBlobStore(paths)
    referenced = store.put(BlobWrite(content=b"referenced", media_type="text/plain"))
    orphan = store.put(BlobWrite(content=b"orphan", media_type="text/plain"))
    assert str(referenced.sha256)[:2] != str(orphan.sha256)[:2]
    _create_catalog(
        paths,
        (
            (
                str(referenced.sha256),
                referenced.size_bytes,
                referenced.media_type,
                referenced.relative_path.as_posix(),
            ),
        ),
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    target_name = str(orphan.sha256)[:2]
    target = paths.blobs / target_name
    moved = tmp_path / "moved-blob-directory"
    real_open = os.open
    swapped = False

    def swap_before_open(
        path: str | bytes | Path, flags: int, *args: object, **kwargs: object
    ) -> int:
        nonlocal swapped
        if path == target_name and kwargs.get("dir_fd") is not None and not swapped:
            target.rename(moved)
            target.symlink_to(outside, target_is_directory=True)
            swapped = True
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap_before_open)
    stdout = io.StringIO()

    exit_code = main(
        ["doctor", "--json"],
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(paths.data_root)},
        stdout=stdout,
        stderr=io.StringIO(),
    )

    payload = json.loads(stdout.getvalue())
    assert swapped
    assert exit_code == 6
    assert payload["data"]["status"] == "UNKNOWN"
    assert payload["data"]["checks"][-1] == {
        "code": "orphan_proof_unavailable",
        "name": "orphaned_blobs",
        "status": "UNKNOWN",
    }
    assert tuple(outside.iterdir()) == ()


def test_doctor_rechecks_referenced_blobs_after_orphan_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    store = FilesystemBlobStore(paths)
    ref = store.put(BlobWrite(content=b"referenced", media_type="text/plain"))
    _create_catalog(
        paths,
        ((str(ref.sha256), ref.size_bytes, ref.media_type, ref.relative_path.as_posix()),),
    )
    target = paths.confined(ref.relative_path)
    real_find_orphans = FilesystemBlobStore.find_orphans

    def corrupt_after_scan(
        blob_store: FilesystemBlobStore, referenced: frozenset[Sha256]
    ) -> tuple[Path, ...]:
        result = real_find_orphans(blob_store, referenced)
        target.write_bytes(b"corrupt after scan")
        return result

    monkeypatch.setattr(FilesystemBlobStore, "find_orphans", corrupt_after_scan)
    stdout = io.StringIO()

    exit_code = main(
        ["doctor", "--json"],
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(paths.data_root)},
        stdout=stdout,
        stderr=io.StringIO(),
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code == 6
    assert payload["data"]["status"] == "INVALID"
    assert payload["data"]["checks"][-1] == {
        "code": "referenced_blob_corrupt",
        "name": "referenced_blobs",
        "status": "INVALID",
    }


def test_doctor_reports_unknown_when_catalog_binding_changes_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    paths.data_root.mkdir()
    _create_catalog(paths, ())
    outside_catalog = tmp_path / "outside.sqlite3"
    outside_connection = sqlite3.connect(outside_catalog)
    outside_connection.execute(
        "CREATE TABLE stored_blobs ("
        "sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, "
        "media_type TEXT NOT NULL, relative_path TEXT NOT NULL)"
    )
    outside_connection.commit()
    outside_connection.close()
    original_catalog = tmp_path / "original-catalog.sqlite3"
    real_connect = sqlite3.connect
    swapped = False

    def swap_catalog_before_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        nonlocal swapped
        if not swapped:
            paths.catalog.rename(original_catalog)
            paths.catalog.symlink_to(outside_catalog)
            swapped = True
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", swap_catalog_before_connect)
    stdout = io.StringIO()

    exit_code = main(
        ["doctor", "--json"],
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(paths.data_root)},
        stdout=stdout,
        stderr=io.StringIO(),
    )

    payload = json.loads(stdout.getvalue())
    assert swapped
    assert exit_code == 6
    assert payload["data"]["status"] == "UNKNOWN"
    assert payload["data"]["checks"][1] == {
        "code": "catalog_read_unavailable",
        "name": "catalog",
        "status": "UNKNOWN",
    }


def test_catalog_diagnostic_gives_sqlite_a_preopened_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    paths.data_root.mkdir()
    _create_catalog(paths, ())
    real_connect = sqlite3.connect
    opened_database = ""

    def record_database(*args: object, **kwargs: object) -> sqlite3.Connection:
        nonlocal opened_database
        opened_database = str(args[0])
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", record_database)

    probe = SqliteCatalogDiagnostics(paths).inspect()

    assert probe.status == "OK"
    assert opened_database.startswith("file:///dev/fd/")


def test_catalog_diagnostic_is_unknown_when_data_root_changes_during_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    paths.data_root.mkdir()
    _create_catalog(paths, ())
    replacement_paths = CorpusPaths.from_data_root(tmp_path / "replacement")
    replacement_paths.data_root.mkdir()
    _create_catalog(replacement_paths, ())
    moved = tmp_path / "moved-corpus"
    real_open = os.open
    swapped = False

    def swap_before_open(
        path: str | bytes | Path, flags: int, *args: object, **kwargs: object
    ) -> int:
        nonlocal swapped
        if path == paths.data_root.name and kwargs.get("dir_fd") is not None and not swapped:
            paths.data_root.rename(moved)
            replacement_paths.data_root.rename(paths.data_root)
            swapped = True
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap_before_open)

    probe = SqliteCatalogDiagnostics(paths).inspect()

    assert swapped
    assert probe.status == "UNKNOWN"
    assert probe.checks[-1].code == "catalog_read_unavailable"
