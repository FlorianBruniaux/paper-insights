from __future__ import annotations

import hashlib
import io
import os
import secrets
import stat
from pathlib import Path
from typing import BinaryIO

from paper_insights.domain.corpus import BlobInspection, BlobWrite, StoredBlobRef
from paper_insights.domain.identifiers import Sha256
from paper_insights.paths import CorpusPaths, PathBoundaryError

_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)


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
        parent_descriptor = -1
        try:
            parent_descriptor = self._open_blob_parent(relative_path, create=True)
            self._assert_directory_binding(
                parent_descriptor, self.paths.data_root / relative_path.parent
            )
            filename = relative_path.name
            try:
                existing = self._verified_bytes_at(parent_descriptor, filename, ref)
            except FileNotFoundError:
                existing = None
            if existing is not None:
                if existing != blob.content:
                    raise BlobStoreError("existing blob verification failed")
                return ref
            self._publish_at(parent_descriptor, filename, blob.content, digest)
            self._assert_directory_binding(
                parent_descriptor, self.paths.data_root / relative_path.parent
            )
            if self._verified_bytes_at(parent_descriptor, filename, ref) != blob.content:
                raise BlobStoreError("published blob verification failed")
        except BlobStoreError:
            raise
        except (OSError, PathBoundaryError) as exc:
            raise BlobStoreError("unsafe blob path") from exc
        finally:
            if parent_descriptor >= 0:
                os.close(parent_descriptor)
        return ref

    def open_verified(self, ref: StoredBlobRef) -> BinaryIO:
        return io.BytesIO(self._verified_bytes(ref))

    def inspect(self, ref: StoredBlobRef) -> BlobInspection:
        try:
            content = self._verified_bytes(ref)
        except BlobStoreError:
            try:
                path = self._confined(ref.relative_path)
                size = path.stat(follow_symlinks=False).st_size
            except (BlobStoreError, OSError, PathBoundaryError):
                size = None
            exists = size is not None
            return BlobInspection(exists=exists, valid=False, sha256=ref.sha256, size_bytes=size)
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

    def _open_blob_parent(self, relative_path: Path, *, create: bool) -> int:
        if not relative_path.parts or relative_path.parts[0] != "blobs":
            raise BlobStoreError("unsafe blob path")
        current = self._open_absolute_directory(self.paths.data_root, create=create)
        try:
            for part in relative_path.parent.parts:
                current = self._open_child_directory(current, part, create=create)
            return current
        except BaseException:
            os.close(current)
            raise

    @staticmethod
    def _open_absolute_directory(path: Path, *, create: bool) -> int:
        if not path.is_absolute():
            raise BlobStoreError("unsafe blob path")
        current = os.open(path.anchor, _DIRECTORY_FLAGS)
        try:
            for part in path.parts[1:]:
                current = FilesystemBlobStore._open_child_directory(current, part, create=create)
            return current
        except BaseException:
            os.close(current)
            raise

    @staticmethod
    def _open_child_directory(parent_descriptor: int, name: str, *, create: bool) -> int:
        created = False
        child_descriptor = -1
        if create:
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
                created = True
            except FileExistsError:
                pass
        try:
            child_descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_descriptor)
            if created:
                os.fsync(parent_descriptor)
            os.close(parent_descriptor)
            return child_descriptor
        except BaseException:
            if child_descriptor >= 0:
                os.close(child_descriptor)
            raise

    @staticmethod
    def _assert_directory_binding(descriptor: int, path: Path) -> None:
        check_descriptor = -1
        try:
            check_descriptor = FilesystemBlobStore._open_absolute_directory(path, create=False)
            expected = os.fstat(descriptor)
            actual = os.fstat(check_descriptor)
            if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
                raise BlobStoreError("unsafe blob path")
        except BlobStoreError:
            raise
        except OSError as exc:
            raise BlobStoreError("unsafe blob path") from exc
        finally:
            if check_descriptor >= 0:
                os.close(check_descriptor)

    def _publish_at(
        self,
        parent_descriptor: int,
        filename: str,
        content: bytes,
        digest: str,
    ) -> None:
        temporary_name = f".{digest}.{secrets.token_hex(8)}.tmp"
        descriptor = -1
        temporary_exists = False
        try:
            descriptor = os.open(
                temporary_name,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_descriptor,
            )
            temporary_exists = True
            os.fchmod(descriptor, 0o600)
            view = memoryview(content)
            written = 0
            while written < len(view):
                written += os.write(descriptor, view[written:])
            os.fsync(descriptor)
            if self._hash_descriptor(descriptor) != digest:
                raise BlobStoreError("temporary blob verification failed")
            os.replace(
                temporary_name,
                filename,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            temporary_exists = False
            os.fsync(parent_descriptor)
        except BlobStoreError:
            raise
        except OSError as exc:
            raise BlobStoreError("could not publish blob") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary_exists:
                try:
                    os.unlink(temporary_name, dir_fd=parent_descriptor)
                except OSError:
                    pass

    def _verified_bytes(self, ref: StoredBlobRef) -> bytes:
        parent_descriptor = -1
        try:
            parent_descriptor = self._open_blob_parent(ref.relative_path, create=False)
            self._assert_directory_binding(
                parent_descriptor, self.paths.data_root / ref.relative_path.parent
            )
            content = self._verified_bytes_at(parent_descriptor, ref.relative_path.name, ref)
            self._assert_directory_binding(
                parent_descriptor, self.paths.data_root / ref.relative_path.parent
            )
            return content
        except BlobStoreError:
            raise
        except (OSError, PathBoundaryError) as exc:
            raise BlobStoreError("blob verification failed") from exc
        finally:
            if parent_descriptor >= 0:
                os.close(parent_descriptor)

    @staticmethod
    def _verified_bytes_at(parent_descriptor: int, filename: str, ref: StoredBlobRef) -> bytes:
        descriptor = os.open(filename, _READ_FLAGS, dir_fd=parent_descriptor)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise BlobStoreError("blob verification failed")
            chunks: list[bytes] = []
            digest = hashlib.sha256()
            while chunk := os.read(descriptor, 1024 * 1024):
                chunks.append(chunk)
                digest.update(chunk)
            content = b"".join(chunks)
        finally:
            os.close(descriptor)
        if digest.hexdigest() != str(ref.sha256) or len(content) != ref.size_bytes:
            raise BlobStoreError("blob verification failed")
        return content

    @staticmethod
    def _hash_descriptor(descriptor: int) -> str:
        os.lseek(descriptor, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        return digest.hexdigest()
