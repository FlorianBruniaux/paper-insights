from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import unicodedata
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

from .schema import INDEX_SCHEMA_VERSION, SCHEMA_SQL, read_index_receipt


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
    def __init__(self, published_path: Path) -> None:
        self._published_path = published_path.expanduser().resolve(strict=False)
        self._owned_candidates: set[Path] = set()

    def build_candidate(self, request: IndexBuildRequest) -> IndexCandidate:
        parent = self._published_path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
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
        descriptor, candidate_name = tempfile.mkstemp(
            prefix=f".{self._published_path.name}.candidate-",
            suffix=".sqlite3",
            dir=parent,
        )
        candidate_path = Path(candidate_name).resolve()
        os.close(descriptor)
        os.chmod(candidate_path, 0o600)
        try:
            self._write_candidate(candidate_path, documents, passages, receipt)
            self._reject_sidecars(candidate_path)
            self._fsync_file(candidate_path)
            actual_receipt = read_index_receipt(candidate_path)
            if actual_receipt != receipt:
                raise ValueError("search index receipt differs after verification")
        except BaseException:
            candidate_path.unlink(missing_ok=True)
            raise
        self._owned_candidates.add(candidate_path)
        return IndexCandidate(
            path=candidate_path,
            catalog_revision=request.catalog_revision,
            generation=generation,
            content_sha256=content_sha256,
            receipt=receipt,
        )

    def publish(self, candidate: IndexCandidate, lease: CatalogRevisionLease) -> PublishedIndex:
        candidate_path = candidate.path.resolve()
        if candidate_path not in self._owned_candidates:
            raise ValueError("search index candidate is not owned by this builder")
        if lease.revision != candidate.catalog_revision:
            raise ValueError("revision lease does not match search index candidate")
        if candidate_path.parent != self._published_path.parent:
            raise ValueError("search index candidate is not a sibling of the published index")
        self._reject_sidecars(candidate_path)
        if read_index_receipt(candidate_path) != candidate.receipt:
            raise ValueError("search index candidate changed before publication")
        os.replace(candidate_path, self._published_path)
        self._owned_candidates.discard(candidate_path)
        self._fsync_directory(self._published_path.parent)
        return PublishedIndex(
            path=self._published_path,
            catalog_revision=candidate.catalog_revision,
            generation=candidate.generation,
        )

    def discard(self, candidate: IndexCandidate) -> None:
        candidate_path = candidate.path.resolve()
        if candidate_path not in self._owned_candidates:
            raise ValueError("search index candidate is not owned by this builder")
        candidate_path.unlink(missing_ok=True)
        Path(f"{candidate_path}-wal").unlink(missing_ok=True)
        Path(f"{candidate_path}-shm").unlink(missing_ok=True)
        self._owned_candidates.discard(candidate_path)

    def _next_generation(self) -> int:
        if not self._published_path.exists():
            return 1
        return read_index_receipt(self._published_path).generation + 1

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
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _reject_sidecars(path: Path) -> None:
        if Path(f"{path}-wal").exists() or Path(f"{path}-shm").exists():
            raise ValueError("closed search index candidate cannot have WAL sidecars")

    @staticmethod
    def _fsync_file(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
