from __future__ import annotations

import hashlib
import io
import os
import stat
import tempfile
from pathlib import Path
from typing import BinaryIO

from paper_insights.domain.corpus import BlobInspection, BlobWrite, StoredBlobRef
from paper_insights.domain.identifiers import Sha256
from paper_insights.paths import CorpusPaths, PathBoundaryError


class BlobStoreError(OSError):
    """A blob could not be safely read or published."""


class FilesystemBlobStore:
    def __init__(self, paths: CorpusPaths) -> None:
        self.paths = paths

    def put(self, blob: BlobWrite) -> StoredBlobRef:
        digest = hashlib.sha256(blob.content).hexdigest()
        relative_path = self._relative_path(digest)
        ref = StoredBlobRef(
            sha256=Sha256(digest),
            size_bytes=len(blob.content),
            media_type=blob.media_type,
            relative_path=relative_path,
        )
        try:
            final_path = self._confined(relative_path)
            self._ensure_directory(final_path.parent)
            if final_path.exists() or final_path.is_symlink():
                if self._verified_bytes(ref) != blob.content:
                    raise BlobStoreError("existing blob verification failed")
                return ref
            self._publish(final_path, blob.content, digest)
            if self._verified_bytes(ref) != blob.content:
                raise BlobStoreError("published blob verification failed")
        except BlobStoreError:
            raise
        except (OSError, PathBoundaryError) as exc:
            raise BlobStoreError("could not publish blob") from exc
        return ref

    def open_verified(self, ref: StoredBlobRef) -> BinaryIO:
        return io.BytesIO(self._verified_bytes(ref))

    def inspect(self, ref: StoredBlobRef) -> BlobInspection:
        try:
            path = self._confined(ref.relative_path)
        except (BlobStoreError, PathBoundaryError):
            return BlobInspection(exists=True, valid=False, sha256=ref.sha256, size_bytes=None)
        if not path.exists() and not path.is_symlink():
            return BlobInspection(exists=False, valid=False, sha256=ref.sha256, size_bytes=None)
        try:
            content = self._verified_bytes(ref)
        except BlobStoreError:
            try:
                size = path.stat(follow_symlinks=False).st_size
            except OSError:
                size = None
            return BlobInspection(exists=True, valid=False, sha256=ref.sha256, size_bytes=size)
        return BlobInspection(
            exists=True,
            valid=True,
            sha256=ref.sha256,
            size_bytes=len(content),
        )

    def find_orphans(self, referenced: frozenset[Sha256]) -> tuple[Path, ...]:
        if not self.paths.blobs.exists():
            return ()
        if self.paths.blobs.is_symlink():
            raise BlobStoreError("unsafe blob path")
        referenced_values = {str(digest) for digest in referenced}
        orphans: list[Path] = []
        for root, directories, files in os.walk(self.paths.blobs, followlinks=False):
            root_path = Path(root)
            for directory in directories:
                if (root_path / directory).is_symlink():
                    raise BlobStoreError("unsafe blob path")
            for filename in files:
                path = root_path / filename
                if path.is_symlink():
                    raise BlobStoreError("unsafe blob path")
                if not filename.endswith(".blob"):
                    continue
                digest = filename.removesuffix(".blob")
                try:
                    Sha256(digest)
                except ValueError as exc:
                    raise BlobStoreError("invalid blob filename") from exc
                if digest not in referenced_values:
                    orphans.append(path.relative_to(self.paths.data_root))
        return tuple(sorted(orphans, key=lambda path: path.as_posix()))

    @staticmethod
    def _relative_path(digest: str) -> Path:
        return Path("blobs") / digest[:2] / digest[2:4] / f"{digest}.blob"

    def _confined(self, relative_path: Path) -> Path:
        if not relative_path.parts or relative_path.parts[0] != "blobs":
            raise BlobStoreError("unsafe blob path")
        try:
            return self.paths.confined(relative_path)
        except PathBoundaryError as exc:
            raise BlobStoreError("unsafe blob path") from exc

    def _ensure_directory(self, directory: Path) -> None:
        self.paths.data_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        relative = directory.relative_to(self.paths.data_root)
        current = self.paths.data_root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise BlobStoreError("unsafe blob path")
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                if not current.is_dir() or current.is_symlink():
                    raise BlobStoreError("unsafe blob path") from None

    def _publish(self, final_path: Path, content: bytes, digest: str) -> None:
        descriptor = -1
        temporary_name: str | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{digest}.",
                suffix=".tmp",
                dir=final_path.parent,
            )
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                descriptor = -1
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            temporary_path = Path(temporary_name)
            if self._hash_file(temporary_path) != digest:
                raise BlobStoreError("temporary blob verification failed")
            os.replace(temporary_path, final_path)
            temporary_name = None
            self._fsync_directory(final_path.parent)
        except BlobStoreError:
            raise
        except OSError as exc:
            raise BlobStoreError("could not publish blob") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary_name is not None:
                try:
                    Path(temporary_name).unlink(missing_ok=True)
                except OSError:
                    pass

    def _verified_bytes(self, ref: StoredBlobRef) -> bytes:
        try:
            path = self._confined(ref.relative_path)
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode):
                    raise BlobStoreError("blob verification failed")
                with os.fdopen(descriptor, "rb", closefd=False) as stream:
                    content = stream.read()
            finally:
                os.close(descriptor)
        except BlobStoreError:
            raise
        except (OSError, PathBoundaryError) as exc:
            raise BlobStoreError("blob verification failed") from exc
        digest = hashlib.sha256(content).hexdigest()
        if digest != str(ref.sha256) or len(content) != ref.size_bytes:
            raise BlobStoreError("blob verification failed")
        return content

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
