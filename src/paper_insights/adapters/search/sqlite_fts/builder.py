from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from paper_insights.application.ports.catalog import CatalogRevisionLease
from paper_insights.domain.identifiers import Sha256
from paper_insights.domain.retrieval import (
    IndexBuildRequest,
    IndexCandidate,
    IndexDocument,
    IndexReceipt,
    PassageIdentity,
    PassageView,
    PublishedIndex,
    passage_id,
)

from .schema import (
    INDEX_SCHEMA_VERSION,
    SCHEMA_SQL,
    assert_safe_directory_binding,
    assert_safe_file_binding,
    assert_safe_target,
    confined_absolute,
    open_confined_parent,
    read_index_receipt,
    read_index_receipt_from_connection,
    safe_target_exists,
)

_CREATE_FLAGS = (
    os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
)
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
_REAL_OS_REPLACE = os.replace


@dataclass(slots=True)
class _CandidateBinding:
    path: Path
    filename: str
    parent_path: Path
    parent_descriptor: int
    file_descriptor: int


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


def passages_for_document(
    document: IndexDocument, chunk_schema_version: str
) -> tuple[PassageView, ...]:
    values = (("title", 0, document.title), ("abstract", 1, document.abstract))
    passages: list[PassageView] = []
    for section, ordinal, raw_text in values:
        if raw_text is None:
            continue
        normalized_text = _normalize(raw_text)
        if not normalized_text.strip():
            continue
        identity = PassageIdentity(
            paper_version_id=document.paper_version_id,
            artifact_sha256=document.metadata_artifact_sha256,
            chunk_schema_version=chunk_schema_version,
            section=section,
            ordinal=ordinal,
            normalized_text=normalized_text,
            start_offset=0,
            end_offset=len(normalized_text),
        )
        passages.append(
            PassageView(
                passage_id=passage_id(identity),
                identity=identity,
                paper_id=document.paper_id,
                version_observation_id=document.version_observation_id,
                text=normalized_text,
            )
        )
    return tuple(passages)


class SqliteFtsIndexBuilder:
    def __init__(self, published_path: Path, *, corpus_root: Path) -> None:
        self._corpus_root, self._published_path = confined_absolute(corpus_root, published_path)
        parent_descriptor, filename, _, _ = open_confined_parent(
            self._corpus_root,
            self._published_path,
            create=True,
        )
        try:
            assert_safe_target(parent_descriptor, filename)
        finally:
            os.close(parent_descriptor)
        self._published_name = filename
        self._owned_candidates: dict[Path, _CandidateBinding] = {}

    def build_candidate(self, request: IndexBuildRequest) -> IndexCandidate:
        generation = self._next_generation()
        documents = tuple(
            sorted(
                request.documents,
                key=lambda item: (
                    str(item.paper_id),
                    str(item.paper_version_id),
                    str(item.version_observation_id),
                ),
            )
        )
        passages = tuple(
            passage
            for document in documents
            for passage in passages_for_document(document, request.chunk_schema_version)
        )
        content_sha256 = self._logical_content_sha256(documents, passages)
        receipt = IndexReceipt(
            index_schema_version=INDEX_SCHEMA_VERSION,
            chunk_schema_version=request.chunk_schema_version,
            generation=generation,
            catalog_revision=request.catalog_revision,
            document_count=len(documents),
            passage_count=len(passages),
            content_sha256=content_sha256,
        )
        binding = self._create_candidate_binding()
        candidate_path = binding.path
        try:
            self._write_candidate(candidate_path, documents, passages, receipt)
            self._assert_binding(binding)
            self._reject_sidecars(binding)
            os.fsync(binding.file_descriptor)
            actual_receipt = read_index_receipt(
                candidate_path,
                corpus_root=self._corpus_root,
            )
            self._assert_binding(binding)
            if actual_receipt != receipt:
                raise ValueError("search index receipt differs after verification")
        except BaseException as primary_error:
            self._cleanup_failed_build(binding, primary_error)
            raise
        self._owned_candidates[candidate_path] = binding
        return IndexCandidate(
            path=candidate_path,
            catalog_revision=request.catalog_revision,
            generation=generation,
            content_sha256=content_sha256,
            receipt=receipt,
        )

    def publish(self, candidate: IndexCandidate, lease: CatalogRevisionLease) -> PublishedIndex:
        candidate_path = candidate.path
        binding = self._owned_candidates.get(candidate_path)
        if binding is None:
            raise ValueError("search index candidate is not owned by this builder")
        if lease.revision != candidate.catalog_revision:
            raise ValueError("revision lease does not match search index candidate")
        if candidate_path.parent != self._published_path.parent:
            raise ValueError("search index candidate is not a sibling of the published index")
        previous_receipt = self._assert_expected_published_generation(candidate.generation - 1)
        self._assert_binding(binding)
        self._reject_sidecars(binding)
        if read_index_receipt(candidate_path, corpus_root=self._corpus_root) != candidate.receipt:
            raise ValueError("search index candidate changed before publication")
        self._assert_binding(binding)
        staging = self._copy_to_private_binding(
            binding.file_descriptor,
            binding.parent_descriptor,
            binding.parent_path,
            purpose="publish",
        )
        rollback: _CandidateBinding | None = None
        try:
            rollback = self._backup_published(binding, previous_receipt)
            self._assert_binding(binding)
            self._assert_binding(staging)
            if (
                read_index_receipt(
                    staging.path,
                    corpus_root=self._corpus_root,
                )
                != candidate.receipt
            ):
                raise ValueError("private publication copy differs from search index candidate")
            self._assert_binding(staging)
            assert_safe_target(staging.parent_descriptor, self._published_name)
            try:
                os.replace(
                    staging.filename,
                    self._published_name,
                    src_dir_fd=staging.parent_descriptor,
                    dst_dir_fd=staging.parent_descriptor,
                )
                assert_safe_directory_binding(
                    staging.parent_descriptor,
                    staging.parent_path,
                )
                assert_safe_file_binding(
                    staging.parent_descriptor,
                    self._published_name,
                    staging.file_descriptor,
                )
                if (
                    read_index_receipt(
                        self._published_path,
                        corpus_root=self._corpus_root,
                    )
                    != candidate.receipt
                ):
                    raise ValueError("published search index differs from validated candidate")
                assert_safe_directory_binding(
                    staging.parent_descriptor,
                    staging.parent_path,
                )
                assert_safe_file_binding(
                    staging.parent_descriptor,
                    self._published_name,
                    staging.file_descriptor,
                )
                os.fsync(staging.parent_descriptor)
            except BaseException as primary_error:
                try:
                    parent_was_displaced = not self._directory_binding_is_current(staging)
                    if parent_was_displaced:
                        primary_error.add_note(
                            "displaced search publication cleanup unavailable: "
                            "POSIX has no atomic unlink-by-inode operation"
                        )
                    self._restore_previous(rollback, previous_receipt)
                except BaseException as rollback_error:
                    primary_error.add_note(
                        "search index rollback failed: "
                        f"{type(rollback_error).__name__}: {rollback_error}"
                    )
                raise
            self._assert_binding(binding)
            os.unlink(binding.filename, dir_fd=binding.parent_descriptor)
            self._unlink_sidecars(binding)
            self._close_binding(candidate_path, binding)
        finally:
            self._cleanup_private_binding(staging)
            if rollback is not None:
                self._cleanup_private_binding(rollback)
        return PublishedIndex(
            path=self._published_path,
            catalog_revision=candidate.catalog_revision,
            generation=candidate.generation,
        )

    @staticmethod
    def _directory_binding_is_current(binding: _CandidateBinding) -> bool:
        try:
            assert_safe_directory_binding(binding.parent_descriptor, binding.parent_path)
        except (OSError, ValueError):
            return False
        return True

    def discard(self, candidate: IndexCandidate) -> None:
        candidate_path = candidate.path
        binding = self._owned_candidates.get(candidate_path)
        if binding is None:
            raise ValueError("search index candidate is not owned by this builder")
        try:
            assert_safe_file_binding(
                binding.parent_descriptor,
                binding.filename,
                binding.file_descriptor,
            )
            os.unlink(binding.filename, dir_fd=binding.parent_descriptor)
            self._unlink_sidecars(binding)
        finally:
            self._close_binding(candidate_path, binding)

    def _backup_published(
        self,
        candidate_binding: _CandidateBinding,
        expected_receipt: IndexReceipt | None,
    ) -> _CandidateBinding | None:
        if expected_receipt is None:
            return None
        published_descriptor = os.open(
            self._published_name,
            _READ_FLAGS,
            dir_fd=candidate_binding.parent_descriptor,
        )
        try:
            assert_safe_file_binding(
                candidate_binding.parent_descriptor,
                self._published_name,
                published_descriptor,
            )
            backup = self._copy_to_private_binding(
                published_descriptor,
                candidate_binding.parent_descriptor,
                candidate_binding.parent_path,
                purpose="rollback",
            )
            assert_safe_file_binding(
                candidate_binding.parent_descriptor,
                self._published_name,
                published_descriptor,
            )
        finally:
            os.close(published_descriptor)
        try:
            if (
                read_index_receipt(
                    backup.path,
                    corpus_root=self._corpus_root,
                )
                != expected_receipt
            ):
                raise ValueError("rollback copy differs from previous published index")
            self._assert_binding(backup)
        except BaseException:
            self._cleanup_private_binding(backup)
            raise
        return backup

    def _restore_previous(
        self,
        rollback: _CandidateBinding | None,
        expected_receipt: IndexReceipt | None,
    ) -> None:
        parent_descriptor, filename, _, parent_path = open_confined_parent(
            self._corpus_root,
            self._published_path,
            create=True,
        )
        restoration: _CandidateBinding | None = None
        try:
            assert_safe_directory_binding(parent_descriptor, parent_path)
            if rollback is None:
                try:
                    os.unlink(filename, dir_fd=parent_descriptor)
                except FileNotFoundError:
                    pass
                os.fsync(parent_descriptor)
                return
            restoration = self._copy_to_private_binding(
                rollback.file_descriptor,
                parent_descriptor,
                parent_path,
                purpose="restore",
            )
            if (
                read_index_receipt(
                    restoration.path,
                    corpus_root=self._corpus_root,
                )
                != expected_receipt
            ):
                raise ValueError("restoration copy differs from previous published index")
            self._assert_binding(restoration)
            _REAL_OS_REPLACE(
                restoration.filename,
                filename,
                src_dir_fd=restoration.parent_descriptor,
                dst_dir_fd=restoration.parent_descriptor,
            )
            assert_safe_directory_binding(restoration.parent_descriptor, parent_path)
            assert_safe_file_binding(
                restoration.parent_descriptor,
                filename,
                restoration.file_descriptor,
            )
            os.fsync(restoration.parent_descriptor)
            if (
                read_index_receipt(
                    self._published_path,
                    corpus_root=self._corpus_root,
                )
                != expected_receipt
            ):
                raise ValueError("restored search index differs from rollback copy")
        finally:
            if restoration is not None:
                self._cleanup_private_binding(restoration)
            os.close(parent_descriptor)

    def _next_generation(self) -> int:
        if not safe_target_exists(self._corpus_root, self._published_path):
            return 1
        return (
            read_index_receipt(
                self._published_path,
                corpus_root=self._corpus_root,
            ).generation
            + 1
        )

    def _assert_expected_published_generation(self, expected: int) -> IndexReceipt | None:
        exists = safe_target_exists(self._corpus_root, self._published_path)
        if expected == 0:
            if exists:
                raise ValueError("published search index generation changed")
            return None
        if not exists:
            raise ValueError("published search index generation is missing")
        current = read_index_receipt(
            self._published_path,
            corpus_root=self._corpus_root,
        )
        if current.generation != expected:
            raise ValueError(
                f"published search index generation is {current.generation}, expected {expected}"
            )
        return current

    def _create_candidate_binding(self) -> _CandidateBinding:
        parent_descriptor, _, _, parent_path = open_confined_parent(
            self._corpus_root,
            self._published_path,
            create=True,
        )
        for _ in range(128):
            filename = f".{self._published_name}.candidate-{secrets.token_hex(12)}.sqlite3"
            try:
                file_descriptor = os.open(
                    filename,
                    _CREATE_FLAGS,
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            binding = _CandidateBinding(
                path=parent_path / filename,
                filename=filename,
                parent_path=parent_path,
                parent_descriptor=parent_descriptor,
                file_descriptor=file_descriptor,
            )
            self._assert_binding(binding)
            return binding
        os.close(parent_descriptor)
        raise FileExistsError("could not allocate a private search index candidate")

    def _copy_to_private_binding(
        self,
        source_descriptor: int,
        parent_descriptor: int,
        parent_path: Path,
        *,
        purpose: str,
    ) -> _CandidateBinding:
        owned_parent_descriptor = os.dup(parent_descriptor)
        try:
            assert_safe_directory_binding(owned_parent_descriptor, parent_path)
            for _ in range(128):
                filename = f".{self._published_name}.{purpose}-{secrets.token_hex(12)}.sqlite3"
                try:
                    file_descriptor = os.open(
                        filename,
                        _CREATE_FLAGS,
                        0o600,
                        dir_fd=owned_parent_descriptor,
                    )
                except FileExistsError:
                    continue
                private = _CandidateBinding(
                    path=parent_path / filename,
                    filename=filename,
                    parent_path=parent_path,
                    parent_descriptor=owned_parent_descriptor,
                    file_descriptor=file_descriptor,
                )
                try:
                    self._copy_descriptor(source_descriptor, file_descriptor)
                    self._assert_binding(private)
                    os.fsync(file_descriptor)
                    if self._descriptor_sha256(source_descriptor) != self._descriptor_sha256(
                        file_descriptor
                    ):
                        raise ValueError("private search index copy has a different binary digest")
                except BaseException:
                    self._cleanup_private_binding(private)
                    owned_parent_descriptor = -1
                    raise
                return private
        except BaseException:
            if owned_parent_descriptor >= 0:
                os.close(owned_parent_descriptor)
            raise
        os.close(owned_parent_descriptor)
        raise FileExistsError("could not allocate a private search index copy")

    @staticmethod
    def _copy_descriptor(source_descriptor: int, destination_descriptor: int) -> None:
        source_size = os.fstat(source_descriptor).st_size
        offset = 0
        while offset < source_size:
            block = os.pread(source_descriptor, min(1024 * 1024, source_size - offset), offset)
            if not block:
                raise OSError("validated search index descriptor ended during copy")
            written = 0
            while written < len(block):
                written += os.write(destination_descriptor, block[written:])
            offset += len(block)
        os.ftruncate(destination_descriptor, source_size)

    @staticmethod
    def _descriptor_sha256(descriptor: int) -> str:
        digest = hashlib.sha256()
        size = os.fstat(descriptor).st_size
        offset = 0
        while offset < size:
            block = os.pread(descriptor, min(1024 * 1024, size - offset), offset)
            if not block:
                raise OSError("validated search index descriptor ended during hashing")
            digest.update(block)
            offset += len(block)
        return digest.hexdigest()

    @staticmethod
    def _cleanup_private_binding(binding: _CandidateBinding) -> None:
        try:
            opened = os.fstat(binding.file_descriptor)
            try:
                current = os.stat(
                    binding.filename,
                    dir_fd=binding.parent_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                return
            if (opened.st_dev, opened.st_ino) == (current.st_dev, current.st_ino):
                os.unlink(binding.filename, dir_fd=binding.parent_descriptor)
        finally:
            os.close(binding.file_descriptor)
            os.close(binding.parent_descriptor)

    @staticmethod
    def _assert_binding(binding: _CandidateBinding) -> None:
        assert_safe_directory_binding(binding.parent_descriptor, binding.parent_path)
        assert_safe_file_binding(
            binding.parent_descriptor,
            binding.filename,
            binding.file_descriptor,
        )

    def _cleanup_failed_build(
        self,
        binding: _CandidateBinding,
        primary_error: BaseException,
    ) -> None:
        try:
            self._assert_binding(binding)
            os.unlink(binding.filename, dir_fd=binding.parent_descriptor)
            self._unlink_sidecars(binding)
        except BaseException as cleanup_error:
            primary_error.add_note(
                f"search candidate cleanup failed: {type(cleanup_error).__name__}"
            )
        finally:
            os.close(binding.file_descriptor)
            os.close(binding.parent_descriptor)

    def _close_binding(self, path: Path, binding: _CandidateBinding) -> None:
        self._owned_candidates.pop(path, None)
        os.close(binding.file_descriptor)
        os.close(binding.parent_descriptor)

    @staticmethod
    def _reject_sidecars(binding: _CandidateBinding) -> None:
        for suffix in ("-wal", "-shm"):
            try:
                os.stat(
                    f"{binding.filename}{suffix}",
                    dir_fd=binding.parent_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                continue
            raise ValueError("closed search index candidate cannot have WAL sidecars")

    @staticmethod
    def _unlink_sidecars(binding: _CandidateBinding) -> None:
        for suffix in ("-wal", "-shm"):
            try:
                os.unlink(f"{binding.filename}{suffix}", dir_fd=binding.parent_descriptor)
            except FileNotFoundError:
                pass

    @staticmethod
    def _logical_content_sha256(
        documents: tuple[IndexDocument, ...], passages: tuple[PassageView, ...]
    ) -> Sha256:
        payload = {
            "documents": [
                {
                    "abstract": item.abstract,
                    "artifact_sha256": str(item.metadata_artifact_sha256),
                    "paper_id": str(item.paper_id),
                    "paper_version_id": str(item.paper_version_id),
                    "title": item.title,
                    "version_observation_id": str(item.version_observation_id),
                }
                for item in documents
            ],
            "passages": [
                {
                    "artifact_sha256": str(item.identity.artifact_sha256),
                    "chunk_schema_version": item.identity.chunk_schema_version,
                    "end_offset": item.identity.end_offset,
                    "normalized_text": item.identity.normalized_text,
                    "ordinal": item.identity.ordinal,
                    "paper_id": str(item.paper_id),
                    "paper_version_id": str(item.identity.paper_version_id),
                    "passage_id": str(item.passage_id),
                    "section": item.identity.section,
                    "start_offset": item.identity.start_offset,
                    "version_observation_id": str(item.version_observation_id),
                }
                for item in passages
            ],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return Sha256(hashlib.sha256(encoded).hexdigest())

    @staticmethod
    def _write_candidate(
        path: Path,
        documents: tuple[IndexDocument, ...],
        passages: tuple[PassageView, ...],
        receipt: IndexReceipt,
    ) -> None:
        connection = sqlite3.connect(path)
        try:
            connection.row_factory = sqlite3.Row
            journal_mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
            if str(journal_mode).lower() != "delete":
                raise ValueError("search candidate must use journal_mode=DELETE")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA synchronous = FULL")
            connection.executescript(SCHEMA_SQL)
            connection.execute("BEGIN IMMEDIATE")
            for document in documents:
                connection.execute(
                    "INSERT INTO documents "
                    "(paper_version_id, paper_id, version_observation_id, title, abstract, "
                    "artifact_sha256) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        str(document.paper_version_id),
                        str(document.paper_id),
                        str(document.version_observation_id),
                        document.title,
                        document.abstract,
                        str(document.metadata_artifact_sha256),
                    ),
                )
                connection.execute(
                    "INSERT INTO paper_fts (paper_version_id, title, abstract) VALUES (?, ?, ?)",
                    (str(document.paper_version_id), document.title, document.abstract),
                )
            for passage in passages:
                identity = passage.identity
                connection.execute(
                    "INSERT INTO passages "
                    "(passage_id, paper_id, paper_version_id, version_observation_id, "
                    "artifact_sha256, chunk_schema_version, section, ordinal, normalized_text, "
                    "start_offset, end_offset) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(passage.passage_id),
                        str(passage.paper_id),
                        str(identity.paper_version_id),
                        str(passage.version_observation_id),
                        str(identity.artifact_sha256),
                        identity.chunk_schema_version,
                        identity.section,
                        identity.ordinal,
                        identity.normalized_text,
                        identity.start_offset,
                        identity.end_offset,
                    ),
                )
                connection.execute(
                    "INSERT INTO passage_fts (passage_id, normalized_text) VALUES (?, ?)",
                    (str(passage.passage_id), identity.normalized_text),
                )
            connection.execute(
                "INSERT INTO index_meta "
                "(singleton_id, index_schema_version, chunk_schema_version, generation, "
                "catalog_revision, document_count, passage_count, content_sha256) "
                "VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
                (
                    receipt.index_schema_version,
                    receipt.chunk_schema_version,
                    receipt.generation,
                    receipt.catalog_revision.value,
                    receipt.document_count,
                    receipt.passage_count,
                    str(receipt.content_sha256),
                ),
            )
            transaction_receipt = read_index_receipt_from_connection(connection)
            if transaction_receipt != receipt:
                raise ValueError("search candidate differs before commit")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
