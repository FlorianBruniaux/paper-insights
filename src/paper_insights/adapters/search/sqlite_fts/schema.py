from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from paper_insights.domain.identifiers import Sha256
from paper_insights.domain.retrieval import CatalogRevision, IndexReceipt

INDEX_SCHEMA_VERSION = "fts-v2"
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)

SCHEMA_SQL = """
CREATE TABLE index_meta (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    index_schema_version TEXT NOT NULL,
    chunk_schema_version TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation >= 0),
    catalog_revision INTEGER NOT NULL CHECK (catalog_revision >= 0),
    document_count INTEGER NOT NULL CHECK (document_count >= 0),
    passage_count INTEGER NOT NULL CHECK (passage_count >= 0),
    content_sha256 TEXT NOT NULL CHECK (
        length(content_sha256) = 64 AND content_sha256 NOT GLOB '*[^0-9a-f]*'
    )
);

CREATE TABLE documents (
    paper_version_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    version_observation_id TEXT NOT NULL UNIQUE,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    abstract TEXT,
    artifact_sha256 TEXT NOT NULL,
    language TEXT,
    language_folded TEXT,
    submitted_at TEXT
);

CREATE TABLE document_authors (
    paper_version_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    name TEXT NOT NULL,
    name_folded TEXT NOT NULL,
    PRIMARY KEY (paper_version_id, position),
    FOREIGN KEY (paper_version_id) REFERENCES documents (paper_version_id)
);

CREATE INDEX ix_document_authors_name
ON document_authors (name_folded, paper_version_id);

CREATE TABLE document_categories (
    paper_version_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    category TEXT NOT NULL,
    PRIMARY KEY (paper_version_id, position),
    UNIQUE (paper_version_id, category),
    FOREIGN KEY (paper_version_id) REFERENCES documents (paper_version_id)
);

CREATE INDEX ix_document_categories_category
ON document_categories (category, paper_version_id);

CREATE TABLE document_collections (
    paper_version_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    collection_id TEXT NOT NULL,
    slug TEXT NOT NULL,
    PRIMARY KEY (paper_version_id, position),
    UNIQUE (paper_version_id, collection_id),
    UNIQUE (paper_version_id, slug),
    FOREIGN KEY (paper_version_id) REFERENCES documents (paper_version_id)
);

CREATE INDEX ix_document_collections_identity
ON document_collections (collection_id, slug, paper_version_id);

CREATE TABLE passages (
    passage_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    paper_version_id TEXT NOT NULL,
    version_observation_id TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    chunk_schema_version TEXT NOT NULL,
    section TEXT,
    ordinal INTEGER NOT NULL,
    normalized_text TEXT NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    FOREIGN KEY (paper_version_id) REFERENCES documents (paper_version_id)
);

CREATE VIRTUAL TABLE paper_fts USING fts5(
    paper_version_id UNINDEXED,
    title,
    abstract,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE VIRTUAL TABLE passage_fts USING fts5(
    passage_id UNINDEXED,
    normalized_text,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


def confined_absolute(corpus_root: Path, index_path: Path) -> tuple[Path, Path]:
    root = corpus_root.expanduser()
    path = index_path.expanduser()
    if not root.is_absolute() or not path.is_absolute():
        raise ValueError("corpus root and search index path must be absolute")
    root = Path(os.path.abspath(root))
    path = Path(os.path.abspath(path))
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ValueError("search index path is not confined to corpus root") from exc
    if not relative.parts:
        raise ValueError("search index path must name a file below corpus root")
    try:
        root_stat = os.lstat(root)
    except OSError as exc:
        raise ValueError("corpus root is unavailable") from exc
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise ValueError("corpus root cannot be a symbolic link and must be a directory")
    return root, path


def open_confined_parent(
    corpus_root: Path,
    index_path: Path,
    *,
    create: bool,
) -> tuple[int, str, Path, Path]:
    root, path = confined_absolute(corpus_root, index_path)
    relative = path.relative_to(root)
    try:
        descriptor = os.open(root, _DIRECTORY_FLAGS)
    except OSError as exc:
        raise ValueError("corpus root cannot be opened safely") from exc
    current_path = root
    try:
        assert_safe_directory_binding(descriptor, current_path)
        for part in relative.parts[:-1]:
            try:
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except OSError as exc:
                raise ValueError("search index parent contains a symbolic or unsafe path") from exc
            os.close(descriptor)
            descriptor = child
            current_path = current_path / part
            assert_safe_directory_binding(descriptor, current_path)
        return descriptor, relative.name, path, current_path
    except BaseException:
        os.close(descriptor)
        raise


def assert_safe_file_binding(parent_descriptor: int, filename: str, file_descriptor: int) -> None:
    opened = os.fstat(file_descriptor)
    try:
        current = os.stat(filename, dir_fd=parent_descriptor, follow_symlinks=False)
    except OSError as exc:
        raise ValueError("search index file binding is unavailable") from exc
    if not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(current.st_mode):
        raise ValueError("search index file cannot be a symbolic link")
    if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
        raise ValueError("search index file binding changed")


def assert_safe_target(parent_descriptor: int, filename: str) -> None:
    try:
        current = os.stat(filename, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ValueError("search index target is unavailable") from exc
    if not stat.S_ISREG(current.st_mode):
        raise ValueError("search index target cannot be a symbolic link")


def safe_target_exists(corpus_root: Path, index_path: Path) -> bool:
    try:
        parent_descriptor, filename, _, parent_path = open_confined_parent(
            corpus_root,
            index_path,
            create=False,
        )
    except FileNotFoundError:
        return False
    try:
        assert_safe_directory_binding(parent_descriptor, parent_path)
        try:
            current = os.stat(filename, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return False
        if not stat.S_ISREG(current.st_mode):
            raise ValueError("search index target cannot be a symbolic link")
        return True
    finally:
        os.close(parent_descriptor)


def assert_safe_directory_binding(descriptor: int, path: Path) -> None:
    opened = os.fstat(descriptor)
    try:
        current = os.lstat(path)
    except OSError as exc:
        raise ValueError("search index parent binding is unavailable") from exc
    if stat.S_ISLNK(current.st_mode) or not stat.S_ISDIR(current.st_mode):
        raise ValueError("search index parent cannot be a symbolic link")
    if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
        raise ValueError("search index parent binding changed")


def readonly_descriptor_uri(file_descriptor: int) -> str:
    descriptor_path = f"/dev/fd/{file_descriptor}"
    return f"file:{quote(descriptor_path, safe='/')}?mode=ro&immutable=1"


@contextmanager
def open_readonly(
    path: Path,
    *,
    corpus_root: Path,
    timeout_seconds: float = 1.0,
) -> Iterator[sqlite3.Connection]:
    parent_descriptor, filename, _, parent_path = open_confined_parent(
        corpus_root,
        path,
        create=False,
    )
    file_descriptor = -1
    connection: sqlite3.Connection | None = None
    try:
        assert_safe_target(parent_descriptor, filename)
        file_descriptor = os.open(filename, _READ_FLAGS, dir_fd=parent_descriptor)
        assert_safe_file_binding(parent_descriptor, filename, file_descriptor)
        connection = sqlite3.connect(
            readonly_descriptor_uri(file_descriptor),
            uri=True,
            timeout=timeout_seconds,
        )
        assert_safe_directory_binding(parent_descriptor, parent_path)
        assert_safe_file_binding(parent_descriptor, filename, file_descriptor)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        yield connection
    finally:
        if connection is not None:
            connection.close()
        if file_descriptor >= 0:
            os.close(file_descriptor)
        os.close(parent_descriptor)


def read_index_receipt(path: Path, *, corpus_root: Path) -> IndexReceipt:
    with open_readonly(path, corpus_root=corpus_root) as connection:
        return read_index_receipt_from_connection(connection)


def read_index_receipt_from_connection(connection: sqlite3.Connection) -> IndexReceipt:
    check = connection.execute("PRAGMA quick_check").fetchone()
    if check is None or check[0] != "ok":
        raise ValueError("search index failed quick_check")
    rows = connection.execute(
        "SELECT index_schema_version, chunk_schema_version, generation, "
        "catalog_revision, document_count, passage_count, content_sha256 "
        "FROM index_meta WHERE singleton_id = 1"
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("search index must contain one authoritative receipt")
    row = rows[0]
    if row["index_schema_version"] != INDEX_SCHEMA_VERSION:
        raise ValueError("unsupported search index schema")
    actual_documents = int(connection.execute("SELECT count(*) FROM documents").fetchone()[0])
    actual_passages = int(connection.execute("SELECT count(*) FROM passages").fetchone()[0])
    actual_paper_fts = int(connection.execute("SELECT count(*) FROM paper_fts").fetchone()[0])
    actual_passage_fts = int(connection.execute("SELECT count(*) FROM passage_fts").fetchone()[0])
    if int(row["document_count"]) != actual_documents or actual_documents != actual_paper_fts:
        raise ValueError("search index document counters disagree")
    if int(row["passage_count"]) != actual_passages or actual_passages != actual_passage_fts:
        raise ValueError("search index passage counters disagree")
    if _logical_content_sha256(connection) != str(row["content_sha256"]):
        raise ValueError("search index content fingerprint disagrees with its receipt")
    return IndexReceipt(
        index_schema_version=str(row["index_schema_version"]),
        chunk_schema_version=str(row["chunk_schema_version"]),
        generation=int(row["generation"]),
        catalog_revision=CatalogRevision(int(row["catalog_revision"])),
        document_count=int(row["document_count"]),
        passage_count=int(row["passage_count"]),
        content_sha256=Sha256(str(row["content_sha256"])),
    )


def _logical_content_sha256(connection: sqlite3.Connection) -> str:
    document_rows = connection.execute(
        "SELECT paper_id, paper_version_id, version_observation_id, source_id, title, abstract, "
        "artifact_sha256, language, language_folded, submitted_at FROM documents "
        "ORDER BY paper_id, paper_version_id, version_observation_id"
    ).fetchall()
    authors_by_version = _projection_rows(
        connection.execute(
            "SELECT paper_version_id, position, name, name_folded FROM document_authors "
            "ORDER BY paper_version_id, position"
        ).fetchall(),
        value_column="name",
    )
    categories_by_version = _projection_rows(
        connection.execute(
            "SELECT paper_version_id, position, category FROM document_categories "
            "ORDER BY paper_version_id, position"
        ).fetchall(),
        value_column="category",
    )
    collections_by_version = _ordered_collection_projection(connection)
    passage_rows = connection.execute(
        "SELECT passage_id, paper_id, paper_version_id, version_observation_id, "
        "artifact_sha256, chunk_schema_version, section, ordinal, normalized_text, "
        "start_offset, end_offset FROM passages "
        "ORDER BY paper_id, paper_version_id, ordinal, passage_id"
    ).fetchall()
    for row in document_rows:
        language = row["language"]
        expected_language = _fold(str(language)) if language is not None else None
        if row["language_folded"] != expected_language:
            raise ValueError("normalized search filter projection is inconsistent")
    fts_documents = tuple(
        tuple(item)
        for item in connection.execute(
            "SELECT paper_version_id, title, abstract FROM paper_fts ORDER BY rowid"
        ).fetchall()
    )
    expected_fts_documents = tuple(
        (item["paper_version_id"], item["title"], item["abstract"]) for item in document_rows
    )
    if fts_documents != expected_fts_documents:
        raise ValueError("paper FTS content differs from authoritative documents")
    fts_passages = tuple(
        tuple(item)
        for item in connection.execute(
            "SELECT passage_id, normalized_text FROM passage_fts ORDER BY rowid"
        ).fetchall()
    )
    expected_fts_passages = tuple(
        (item["passage_id"], item["normalized_text"]) for item in passage_rows
    )
    if fts_passages != expected_fts_passages:
        raise ValueError("passage FTS content differs from authoritative passages")
    payload = {
        "documents": [
            {
                "abstract": item["abstract"],
                "artifact_sha256": item["artifact_sha256"],
                "authors": authors_by_version.get(item["paper_version_id"], []),
                "categories": categories_by_version.get(item["paper_version_id"], []),
                "collections": collections_by_version.get(item["paper_version_id"], []),
                "language": item["language"],
                "paper_id": item["paper_id"],
                "paper_version_id": item["paper_version_id"],
                "source_id": item["source_id"],
                "submitted_at": item["submitted_at"],
                "title": item["title"],
                "version_observation_id": item["version_observation_id"],
            }
            for item in document_rows
        ],
        "passages": [
            {
                "artifact_sha256": item["artifact_sha256"],
                "chunk_schema_version": item["chunk_schema_version"],
                "end_offset": item["end_offset"],
                "normalized_text": item["normalized_text"],
                "ordinal": item["ordinal"],
                "paper_id": item["paper_id"],
                "paper_version_id": item["paper_version_id"],
                "passage_id": item["passage_id"],
                "section": item["section"],
                "start_offset": item["start_offset"],
                "version_observation_id": item["version_observation_id"],
            }
            for item in passage_rows
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _projection_rows(
    rows: list[sqlite3.Row],
    *,
    value_column: str,
) -> dict[str, list[str]]:
    if value_column not in {"name", "category"}:
        raise ValueError("unsupported search projection")
    projected: dict[str, list[str]] = {}
    for row in rows:
        if value_column == "name" and row["name_folded"] != _fold(str(row["name"])):
            raise ValueError("normalized search filter projection is inconsistent")
        projected.setdefault(str(row["paper_version_id"]), []).append(str(row[value_column]))
    return projected


def _fold(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _ordered_collection_projection(
    connection: sqlite3.Connection,
) -> dict[str, list[dict[str, str]]]:
    rows = connection.execute(
        "SELECT paper_version_id, position, collection_id, slug "
        "FROM document_collections ORDER BY paper_version_id, position"
    ).fetchall()
    projected: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        projected.setdefault(str(row["paper_version_id"]), []).append(
            {"collection_id": str(row["collection_id"]), "slug": str(row["slug"])}
        )
    return projected
