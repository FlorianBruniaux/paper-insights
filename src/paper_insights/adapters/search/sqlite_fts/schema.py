from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from paper_insights.domain.identifiers import Sha256
from paper_insights.domain.retrieval import CatalogRevision, IndexReceipt

INDEX_SCHEMA_VERSION = "fts-v1"

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
    title TEXT NOT NULL,
    abstract TEXT,
    artifact_sha256 TEXT NOT NULL
);

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


def readonly_uri(path: Path) -> str:
    return f"file:{quote(str(path.resolve()), safe='/')}?mode=ro"


@contextmanager
def open_readonly(path: Path, *, timeout_seconds: float = 1.0) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(
        readonly_uri(path),
        uri=True,
        timeout=timeout_seconds,
    )
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        yield connection
    finally:
        connection.close()


def read_index_receipt(path: Path) -> IndexReceipt:
    with open_readonly(path) as connection:
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
        "SELECT paper_id, paper_version_id, version_observation_id, title, abstract, "
        "artifact_sha256 FROM documents "
        "ORDER BY paper_id, paper_version_id, version_observation_id"
    ).fetchall()
    passage_rows = connection.execute(
        "SELECT passage_id, paper_id, paper_version_id, version_observation_id, "
        "artifact_sha256, chunk_schema_version, section, ordinal, normalized_text, "
        "start_offset, end_offset FROM passages "
        "ORDER BY paper_id, paper_version_id, ordinal, passage_id"
    ).fetchall()
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
                "paper_id": item["paper_id"],
                "paper_version_id": item["paper_version_id"],
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
