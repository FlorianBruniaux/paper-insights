from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Literal
from uuid import UUID

import pytest

from paper_insights.adapters.search.sqlite_fts.builder import SqliteFtsIndexBuilder
from paper_insights.adapters.search.sqlite_fts.schema import read_index_receipt
from paper_insights.application.research.index import RebuildSearchIndex
from paper_insights.domain.identifiers import (
    PaperId,
    PaperVersionId,
    Sha256,
    VersionObservationId,
)
from paper_insights.domain.retrieval import (
    CatalogRevision,
    IndexBuildRequest,
    IndexDocument,
)


@dataclass
class _Lease:
    revision: CatalogRevision

    def __enter__(self) -> _Lease:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc_type, exc, traceback
        return False


class _Snapshot:
    def __init__(self, request: IndexBuildRequest) -> None:
        self.revision = request.catalog_revision
        self._documents = request.documents
        self.closed = False

    def __enter__(self) -> _Snapshot:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc_type, exc, traceback
        self.closed = True
        return False

    def list_index_documents(self) -> tuple[IndexDocument, ...]:
        if self.closed:
            raise RuntimeError("snapshot is closed")
        return self._documents


class _Reader:
    def __init__(self, snapshot: _Snapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> _Snapshot:
        return self._snapshot


class _Guard:
    def __init__(self, revision: CatalogRevision) -> None:
        self._revision = revision

    def hold_if_current(self, expected: CatalogRevision) -> _Lease:
        if expected != self._revision:
            raise RuntimeError("stale catalog revision")
        return _Lease(self._revision)


def _request(revision: int, *, title: str = "Evidence agents") -> IndexBuildRequest:
    return IndexBuildRequest(
        documents=(
            IndexDocument(
                paper_id=PaperId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f51")),
                paper_version_id=PaperVersionId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5a")),
                version_observation_id=VersionObservationId(
                    UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f5b")
                ),
                title=title,
                abstract="Local proof with stable provenance.",
                metadata_artifact_sha256=Sha256("a" * 64),
            ),
        ),
        catalog_revision=CatalogRevision(revision),
        chunk_schema_version="chunk-v1",
    )


def _read_pragma(path: Path, pragma: str) -> object:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return connection.execute(f"PRAGMA {pragma}").fetchone()[0]
    finally:
        connection.close()


def test_candidate_is_a_closed_self_describing_single_file(tmp_path: Path) -> None:
    published_path = tmp_path / ".search" / "search-v1.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path)

    candidate = builder.build_candidate(_request(7))

    assert candidate.path.is_absolute()
    assert candidate.path.parent == published_path.parent
    assert candidate.receipt == read_index_receipt(candidate.path)
    assert candidate.receipt.catalog_revision == CatalogRevision(7)
    assert candidate.receipt.generation == 1
    assert candidate.receipt.document_count == 1
    assert candidate.receipt.passage_count == 2
    assert _read_pragma(candidate.path, "journal_mode") == "delete"
    assert _read_pragma(candidate.path, "quick_check") == "ok"
    assert not Path(f"{candidate.path}-wal").exists()
    assert not Path(f"{candidate.path}-shm").exists()


def test_same_logical_snapshot_has_the_same_content_digest(tmp_path: Path) -> None:
    builder = SqliteFtsIndexBuilder(tmp_path / "search-v1.sqlite3")

    first = builder.build_candidate(_request(4))
    second = builder.build_candidate(_request(4))

    assert first.content_sha256 == second.content_sha256
    assert first.receipt == second.receipt


def test_publish_replaces_only_after_revision_lease_is_valid(tmp_path: Path) -> None:
    published_path = tmp_path / "search-v1.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path)
    candidate = builder.build_candidate(_request(3))

    with pytest.raises(ValueError, match="revision lease"):
        builder.publish(candidate, _Lease(CatalogRevision(2)))

    assert candidate.path.exists()
    assert not published_path.exists()

    published = builder.publish(candidate, _Lease(CatalogRevision(3)))

    assert published.path == published_path.resolve()
    assert not candidate.path.exists()
    assert read_index_receipt(published_path).catalog_revision == CatalogRevision(3)


def test_publish_rejects_logical_content_tampered_after_candidate_verification(
    tmp_path: Path,
) -> None:
    published_path = tmp_path / "search-v1.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path)
    candidate = builder.build_candidate(_request(3))
    connection = sqlite3.connect(candidate.path)
    try:
        connection.execute("UPDATE documents SET title = 'tampered'")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match="content"):
        builder.publish(candidate, _Lease(CatalogRevision(3)))

    assert candidate.path.exists()
    assert not published_path.exists()


def test_injected_replace_crash_preserves_previously_published_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published_path = tmp_path / "search-v1.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path)
    first = builder.build_candidate(_request(1, title="Published evidence"))
    builder.publish(first, _Lease(CatalogRevision(1)))
    previous_bytes = published_path.read_bytes()
    next_candidate = builder.build_candidate(_request(2, title="Candidate evidence"))

    def crash_before_replace(source: Path, destination: Path) -> None:
        del source, destination
        raise OSError("injected publication crash")

    monkeypatch.setattr(
        "paper_insights.adapters.search.sqlite_fts.builder.os.replace",
        crash_before_replace,
    )

    with pytest.raises(OSError, match="injected publication crash"):
        builder.publish(next_candidate, _Lease(CatalogRevision(2)))

    assert published_path.read_bytes() == previous_bytes
    assert read_index_receipt(published_path).catalog_revision == CatalogRevision(1)
    assert next_candidate.path.exists()

    builder.discard(next_candidate)
    assert not next_candidate.path.exists()
    assert published_path.exists()


def test_rebuild_uses_one_snapshot_then_publishes_under_its_revision_guard(
    tmp_path: Path,
) -> None:
    request = _request(9)
    snapshot = _Snapshot(request)
    builder = SqliteFtsIndexBuilder(tmp_path / "search-v1.sqlite3")
    service = RebuildSearchIndex(
        catalog=_Reader(snapshot),
        builder=builder,
        revision_guard=_Guard(CatalogRevision(9)),
    )

    published = service.execute(chunk_schema_version="chunk-v1")

    assert snapshot.closed is True
    assert published.catalog_revision == CatalogRevision(9)
    assert read_index_receipt(published.path).catalog_revision == CatalogRevision(9)


def test_rebuild_discards_stale_candidate_without_touching_published_index(
    tmp_path: Path,
) -> None:
    published_path = tmp_path / "search-v1.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path)
    initial = builder.build_candidate(_request(1))
    builder.publish(initial, _Lease(CatalogRevision(1)))
    previous_bytes = published_path.read_bytes()
    service = RebuildSearchIndex(
        catalog=_Reader(_Snapshot(_request(2))),
        builder=builder,
        revision_guard=_Guard(CatalogRevision(3)),
    )

    with pytest.raises(RuntimeError, match="stale catalog revision"):
        service.execute(chunk_schema_version="chunk-v1")

    assert published_path.read_bytes() == previous_bytes
    assert tuple(published_path.parent.glob("*.candidate-*.sqlite3")) == ()


def test_rebuild_does_not_mask_stale_revision_when_candidate_cleanup_also_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = SqliteFtsIndexBuilder(tmp_path / "search-v1.sqlite3")
    service = RebuildSearchIndex(
        catalog=_Reader(_Snapshot(_request(2))),
        builder=builder,
        revision_guard=_Guard(CatalogRevision(3)),
    )

    def cleanup_crash(candidate: object) -> None:
        del candidate
        raise OSError("injected cleanup crash")

    monkeypatch.setattr(builder, "discard", cleanup_crash)

    with pytest.raises(RuntimeError, match="stale catalog revision") as caught:
        service.execute(chunk_schema_version="chunk-v1")

    assert any("cleanup failed" in note for note in caught.value.__notes__)
