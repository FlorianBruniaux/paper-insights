from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from paper_insights.adapters.artifacts.filesystem.store import (
    BlobStoreError,
    FilesystemBlobStore,
)
from paper_insights.domain.corpus import BlobWrite, StoredBlobRef
from paper_insights.domain.identifiers import Sha256
from paper_insights.paths import CorpusPaths


def test_put_publishes_verified_content_at_a_confined_content_address(tmp_path: Path) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")
    store = FilesystemBlobStore(paths)
    content = b"immutable paper metadata"
    digest = hashlib.sha256(content).hexdigest()

    ref = store.put(BlobWrite(content=content, media_type="application/json"))

    assert ref.sha256 == Sha256(digest)
    assert ref.relative_path == Path("blobs") / digest[:2] / digest[2:4] / f"{digest}.blob"
    assert ref.size_bytes == len(content)
    assert paths.confined(ref.relative_path).read_bytes() == content
    assert paths.confined(ref.relative_path).stat().st_mode & 0o777 == 0o600
    assert store.inspect(ref).valid
    with store.open_verified(ref) as stream:
        assert stream.read() == content


def test_put_reuses_existing_blob_without_replacing_it(tmp_path: Path) -> None:
    store = FilesystemBlobStore(CorpusPaths.from_data_root(tmp_path / "corpus"))
    blob = BlobWrite(content=b"same bytes", media_type="text/plain")

    first = store.put(blob)
    first_path = store.paths.confined(first.relative_path)
    first_inode = first_path.stat().st_ino
    second = store.put(blob)

    assert second == first
    assert first_path.stat().st_ino == first_inode


def test_put_cleans_private_temporary_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FilesystemBlobStore(CorpusPaths.from_data_root(tmp_path / "corpus"))
    content = b"not published"
    digest = hashlib.sha256(content).hexdigest()

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(BlobStoreError, match="could not publish blob"):
        store.put(BlobWrite(content=content, media_type="text/plain"))

    parent = store.paths.blobs / digest[:2] / digest[2:4]
    assert not (parent / f"{digest}.blob").exists()
    assert tuple(parent.glob(f".{digest}.*.tmp")) == ()


def test_put_rejects_symlink_escape_without_touching_target(tmp_path: Path) -> None:
    data_root = tmp_path / "corpus"
    outside = tmp_path / "outside"
    data_root.mkdir()
    outside.mkdir()
    (data_root / "blobs").symlink_to(outside, target_is_directory=True)
    store = FilesystemBlobStore(CorpusPaths.from_data_root(data_root))

    with pytest.raises(BlobStoreError, match="unsafe blob path"):
        store.put(BlobWrite(content=b"escape", media_type="text/plain"))

    assert tuple(outside.iterdir()) == ()


def test_open_verified_rejects_content_changed_after_publication(tmp_path: Path) -> None:
    store = FilesystemBlobStore(CorpusPaths.from_data_root(tmp_path / "corpus"))
    ref = store.put(BlobWrite(content=b"trusted", media_type="text/plain"))
    store.paths.confined(ref.relative_path).write_bytes(b"tampered")

    inspection = store.inspect(ref)

    assert inspection.exists
    assert not inspection.valid
    with pytest.raises(BlobStoreError, match="blob verification failed"):
        store.open_verified(ref)


def test_inspect_missing_blob_is_read_only(tmp_path: Path) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "absent")
    store = FilesystemBlobStore(paths)
    ref = StoredBlobRef(
        sha256=Sha256("a" * 64),
        size_bytes=3,
        media_type="text/plain",
        relative_path=Path("blobs/aa/aa/") / f"{'a' * 64}.blob",
    )

    inspection = store.inspect(ref)

    assert not inspection.exists
    assert not inspection.valid
    assert inspection.size_bytes is None
    assert not paths.data_root.exists()


def test_find_orphans_reports_without_deleting(tmp_path: Path) -> None:
    store = FilesystemBlobStore(CorpusPaths.from_data_root(tmp_path / "corpus"))
    referenced = store.put(BlobWrite(content=b"referenced", media_type="text/plain"))
    orphan = store.put(BlobWrite(content=b"orphan", media_type="text/plain"))

    found = store.find_orphans(frozenset({referenced.sha256}))

    assert found == (orphan.relative_path,)
    assert store.paths.confined(orphan.relative_path).exists()
