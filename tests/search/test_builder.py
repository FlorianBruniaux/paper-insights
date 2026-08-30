from __future__ import annotations

import os
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Barrier, Lock
from types import TracebackType
from typing import Literal
from uuid import UUID

import pytest

import paper_insights.adapters.search.sqlite_fts.builder as builder_module
from paper_insights.adapters.search.sqlite_fts.builder import SqliteFtsIndexBuilder
from paper_insights.adapters.search.sqlite_fts.schema import (
    read_index_receipt,
    read_index_receipt_from_connection,
)
from paper_insights.application.research.index import RebuildSearchIndex
from paper_insights.domain.identifiers import (
    PaperId,
    PaperVersionId,
    Sha256,
    SourceId,
    VersionObservationId,
)
from paper_insights.domain.retrieval import (
    CatalogRevision,
    IndexBuildRequest,
    IndexCandidate,
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
    ) -> Literal[False]:
        del exc_type, exc, traceback
        return False


class _SerialLease(_Lease):
    def __init__(self, revision: CatalogRevision, lock: Lock) -> None:
        super().__init__(revision)
        self._lock = lock

    def __enter__(self) -> _SerialLease:
        self._lock.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc_type, exc, traceback
        self._lock.release()
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
                source_id=SourceId("arxiv"),
                title=title,
                abstract="Local proof with stable provenance.",
                metadata_artifact_sha256=Sha256("a" * 64),
                authors=("Alice Example",),
                language="en",
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
    builder = SqliteFtsIndexBuilder(published_path, corpus_root=tmp_path)

    candidate = builder.build_candidate(_request(7))

    assert candidate.path.is_absolute()
    assert candidate.path.parent == published_path.parent
    assert candidate.receipt == read_index_receipt(candidate.path, corpus_root=tmp_path)
    assert candidate.receipt.catalog_revision == CatalogRevision(7)
    assert candidate.receipt.generation == 1
    assert candidate.receipt.document_count == 1
    assert candidate.receipt.passage_count == 2
    assert _read_pragma(candidate.path, "journal_mode") == "delete"
    assert _read_pragma(candidate.path, "quick_check") == "ok"
    assert not Path(f"{candidate.path}-wal").exists()
    assert not Path(f"{candidate.path}-shm").exists()


def test_builder_refuses_an_index_parent_symlink_or_path_outside_corpus_root(
    tmp_path: Path,
) -> None:
    corpus_root = tmp_path / "corpus"
    outside = tmp_path / "outside"
    corpus_root.mkdir()
    outside.mkdir()
    (corpus_root / "search-link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match=r"confined|symbolic"):
        SqliteFtsIndexBuilder(
            corpus_root / "search-link" / "search.sqlite3",
            corpus_root=corpus_root,
        )
    with pytest.raises(ValueError, match="confined"):
        SqliteFtsIndexBuilder(outside / "search.sqlite3", corpus_root=corpus_root)


def test_same_logical_snapshot_has_the_same_content_digest(tmp_path: Path) -> None:
    builder = SqliteFtsIndexBuilder(
        tmp_path / "search-v1.sqlite3",
        corpus_root=tmp_path,
    )

    first = builder.build_candidate(_request(4))
    second = builder.build_candidate(_request(4))

    assert first.content_sha256 == second.content_sha256
    assert first.receipt == second.receipt


def test_filter_projection_changes_the_logical_content_digest(tmp_path: Path) -> None:
    first_request = _request(4)
    changed_request = replace(
        first_request,
        documents=(replace(first_request.documents[0], categories=("cs.AI",)),),
    )
    first_builder = SqliteFtsIndexBuilder(
        tmp_path / "first" / "search-v2.sqlite3",
        corpus_root=tmp_path,
    )
    changed_builder = SqliteFtsIndexBuilder(
        tmp_path / "changed" / "search-v2.sqlite3",
        corpus_root=tmp_path,
    )

    first = first_builder.build_candidate(first_request)
    changed = changed_builder.build_candidate(changed_request)

    assert first.content_sha256 != changed.content_sha256


def test_publish_replaces_only_after_revision_lease_is_valid(tmp_path: Path) -> None:
    published_path = tmp_path / "search-v1.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path, corpus_root=tmp_path)
    candidate = builder.build_candidate(_request(3))

    with pytest.raises(ValueError, match="revision lease"):
        builder.publish(candidate, _Lease(CatalogRevision(2)))

    assert candidate.path.exists()
    assert not published_path.exists()

    published = builder.publish(candidate, _Lease(CatalogRevision(3)))

    assert published.path == published_path.resolve()
    assert not candidate.path.exists()
    assert read_index_receipt(
        published_path,
        corpus_root=tmp_path,
    ).catalog_revision == CatalogRevision(3)


def test_publish_rejects_logical_content_tampered_after_candidate_verification(
    tmp_path: Path,
) -> None:
    published_path = tmp_path / "search-v1.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path, corpus_root=tmp_path)
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


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE document_authors SET name_folded = 'unrelated'",
        "UPDATE documents SET language_folded = 'unrelated'",
    ],
)
def test_publish_rejects_tampered_filter_shadow_columns(
    tmp_path: Path,
    statement: str,
) -> None:
    published_path = tmp_path / "search-v2.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path, corpus_root=tmp_path)
    candidate = builder.build_candidate(_request(3))
    connection = sqlite3.connect(candidate.path)
    try:
        connection.execute(statement)
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ValueError, match="normalized search filter projection"):
        builder.publish(candidate, _Lease(CatalogRevision(3)))

    assert candidate.path.exists()
    assert not published_path.exists()


def test_publish_rejects_candidate_symlink_swap_after_content_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published_path = tmp_path / "search-v1.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path, corpus_root=tmp_path)
    candidate = builder.build_candidate(_request(3))
    attacker = tmp_path / "attacker.sqlite3"
    shutil.copyfile(candidate.path, attacker)
    real_read_receipt = builder_module.read_index_receipt

    def swap_after_validation(path: Path, *args: object, **kwargs: object) -> object:
        receipt = real_read_receipt(path, *args, **kwargs)
        if path == candidate.path:
            candidate.path.unlink()
            candidate.path.symlink_to(attacker)
        return receipt

    monkeypatch.setattr(builder_module, "read_index_receipt", swap_after_validation)

    with pytest.raises(ValueError, match=r"binding|symbolic"):
        builder.publish(candidate, _Lease(CatalogRevision(3)))

    assert not published_path.exists()
    assert candidate.path.is_symlink()


def test_publish_rejects_parent_directory_swap_after_candidate_validation(
    tmp_path: Path,
) -> None:
    published_path = tmp_path / "search" / "search-v1.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path, corpus_root=tmp_path)
    candidate = builder.build_candidate(_request(3))
    original_parent = tmp_path / "original-search"
    published_path.parent.rename(original_parent)
    published_path.parent.mkdir()

    with pytest.raises(ValueError, match="parent binding changed"):
        builder.publish(candidate, _Lease(CatalogRevision(3)))

    assert not published_path.exists()
    assert (original_parent / candidate.path.name).exists()

    published_path.parent.rmdir()
    original_parent.rename(published_path.parent)
    builder.discard(candidate)


def test_injected_replace_crash_preserves_previously_published_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published_path = tmp_path / "search-v1.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path, corpus_root=tmp_path)
    first = builder.build_candidate(_request(1, title="Published evidence"))
    builder.publish(first, _Lease(CatalogRevision(1)))
    previous_bytes = published_path.read_bytes()
    next_candidate = builder.build_candidate(_request(2, title="Candidate evidence"))

    def crash_before_replace(
        source: Path | str,
        destination: Path | str,
        **options: object,
    ) -> None:
        del source, destination, options
        raise OSError("injected publication crash")

    monkeypatch.setattr(
        "paper_insights.adapters.search.sqlite_fts.builder.os.replace",
        crash_before_replace,
    )

    with pytest.raises(OSError, match="injected publication crash"):
        builder.publish(next_candidate, _Lease(CatalogRevision(2)))

    assert published_path.read_bytes() == previous_bytes
    assert read_index_receipt(
        published_path,
        corpus_root=tmp_path,
    ).catalog_revision == CatalogRevision(1)
    assert next_candidate.path.exists()

    builder.discard(next_candidate)
    assert not next_candidate.path.exists()
    assert published_path.exists()


def test_late_source_symlink_swap_restores_previous_published_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published_path = tmp_path / "search-v1.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path, corpus_root=tmp_path)
    initial = builder.build_candidate(_request(1, title="Stable published evidence"))
    builder.publish(initial, _Lease(CatalogRevision(1)))
    previous_bytes = published_path.read_bytes()
    candidate = builder.build_candidate(_request(2, title="Replacement evidence"))
    attacker = tmp_path / "attacker.sqlite3"
    shutil.copyfile(candidate.path, attacker)
    real_replace = builder_module.os.replace
    injected = False

    def swap_source_inside_replace(
        source: Path | str,
        destination: Path | str,
        **options: object,
    ) -> None:
        nonlocal injected
        source_dir = options.get("src_dir_fd")
        if not injected and destination == published_path.name and isinstance(source_dir, int):
            injected = True
            os.unlink(source, dir_fd=source_dir)
            os.symlink(attacker, source, dir_fd=source_dir)
        real_replace(source, destination, **options)  # type: ignore[arg-type]

    monkeypatch.setattr(builder_module.os, "replace", swap_source_inside_replace)

    with pytest.raises(ValueError, match=r"binding|symbolic"):
        builder.publish(candidate, _Lease(CatalogRevision(2)))

    assert injected is True
    assert published_path.is_symlink() is False
    assert published_path.read_bytes() == previous_bytes
    assert read_index_receipt(published_path, corpus_root=tmp_path).generation == 1
    builder.discard(candidate)


def test_late_parent_rename_restores_previous_index_at_canonical_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published_path = tmp_path / "search" / "search-v1.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path, corpus_root=tmp_path)
    initial = builder.build_candidate(_request(1, title="Stable published evidence"))
    builder.publish(initial, _Lease(CatalogRevision(1)))
    previous_bytes = published_path.read_bytes()
    candidate = builder.build_candidate(_request(2, title="Replacement evidence"))
    displaced_parent = tmp_path / "displaced-search"
    real_replace = builder_module.os.replace
    injected = False

    def rename_parent_inside_replace(
        source: Path | str,
        destination: Path | str,
        **options: object,
    ) -> None:
        nonlocal injected
        if not injected and destination == published_path.name:
            injected = True
            published_path.parent.rename(displaced_parent)
            published_path.parent.mkdir()
        real_replace(source, destination, **options)  # type: ignore[arg-type]

    monkeypatch.setattr(builder_module.os, "replace", rename_parent_inside_replace)

    with pytest.raises(ValueError, match="parent binding changed"):
        builder.publish(candidate, _Lease(CatalogRevision(2)))

    assert injected is True
    assert published_path.exists()
    assert published_path.is_symlink() is False
    assert published_path.read_bytes() == previous_bytes
    assert read_index_receipt(published_path, corpus_root=tmp_path).generation == 1
    displaced_publication = displaced_parent / published_path.name
    assert displaced_publication.exists()
    assert (
        read_index_receipt(
            displaced_publication,
            corpus_root=tmp_path,
        ).generation
        == 2
    )
    builder.discard(candidate)
    assert displaced_publication.exists()
    assert tuple(tmp_path.rglob(f".{published_path.name}.*-*.sqlite3")) == ()


def test_parent_rename_cleanup_never_unlinks_a_late_third_party_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published_path = tmp_path / "search" / "search-v1.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path, corpus_root=tmp_path)
    initial = builder.build_candidate(_request(1, title="Stable published evidence"))
    builder.publish(initial, _Lease(CatalogRevision(1)))
    previous_bytes = published_path.read_bytes()
    candidate = builder.build_candidate(_request(2, title="Replacement evidence"))
    displaced_parent = tmp_path / "displaced-search"
    third_party_bytes = b"third-party inode must remain untouched"
    real_replace = builder_module.os.replace

    def replace_displaced_publication_with_third_party(
        source: Path | str,
        destination: Path | str,
        **options: object,
    ) -> None:
        published_path.parent.rename(displaced_parent)
        published_path.parent.mkdir()
        real_replace(source, destination, **options)  # type: ignore[arg-type]
        displaced_publication = displaced_parent / published_path.name
        displaced_publication.unlink()
        displaced_publication.write_bytes(third_party_bytes)

    monkeypatch.setattr(
        builder_module.os,
        "replace",
        replace_displaced_publication_with_third_party,
    )

    with pytest.raises(ValueError, match="parent binding changed") as caught:
        builder.publish(candidate, _Lease(CatalogRevision(2)))

    assert any("cleanup unavailable" in note for note in caught.value.__notes__)
    assert (displaced_parent / published_path.name).read_bytes() == third_party_bytes
    assert published_path.read_bytes() == previous_bytes
    builder.discard(candidate)
    assert (displaced_parent / published_path.name).read_bytes() == third_party_bytes


def test_concurrent_candidates_with_same_next_generation_cannot_both_publish(
    tmp_path: Path,
) -> None:
    published_path = tmp_path / "search-v1.sqlite3"
    initial_builder = SqliteFtsIndexBuilder(published_path, corpus_root=tmp_path)
    initial = initial_builder.build_candidate(_request(1))
    initial_builder.publish(initial, _Lease(CatalogRevision(1)))
    first_builder = SqliteFtsIndexBuilder(published_path, corpus_root=tmp_path)
    second_builder = SqliteFtsIndexBuilder(published_path, corpus_root=tmp_path)
    first = first_builder.build_candidate(_request(2, title="First generation two"))
    second = second_builder.build_candidate(_request(2, title="Second generation two"))
    contenders = ((first_builder, first), (second_builder, second))
    start = Barrier(2)
    publication_lock = Lock()

    def publish_contender(
        builder: SqliteFtsIndexBuilder,
        candidate: IndexCandidate,
    ) -> BaseException | None:
        start.wait()
        try:
            with _SerialLease(CatalogRevision(2), publication_lock) as lease:
                builder.publish(candidate, lease)
        except BaseException as error:
            return error
        return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(
            executor.map(
                lambda contender: publish_contender(*contender),
                contenders,
            )
        )

    assert sum(outcome is None for outcome in outcomes) == 1
    failures = tuple(outcome for outcome in outcomes if outcome is not None)
    assert len(failures) == 1
    assert isinstance(failures[0], ValueError)
    assert "generation" in str(failures[0])
    assert read_index_receipt(published_path, corpus_root=tmp_path).generation == 2
    for (builder, candidate), outcome in zip(contenders, outcomes, strict=True):
        if outcome is not None:
            builder.discard(candidate)


def test_candidate_integrity_is_checked_inside_the_write_transaction_before_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed_transaction_states: list[bool] = []

    def observe(connection: sqlite3.Connection) -> object:
        observed_transaction_states.append(connection.in_transaction)
        return read_index_receipt_from_connection(connection)

    monkeypatch.setattr(builder_module, "read_index_receipt_from_connection", observe)
    builder = SqliteFtsIndexBuilder(
        tmp_path / "search-v1.sqlite3",
        corpus_root=tmp_path,
    )

    builder.build_candidate(_request(4))

    assert observed_transaction_states == [True]


def test_precommit_counter_mismatch_rolls_back_and_removes_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_read_receipt = read_index_receipt_from_connection

    def corrupt_fts_counter(connection: sqlite3.Connection) -> object:
        assert connection.in_transaction is True
        connection.execute("DELETE FROM paper_fts")
        return real_read_receipt(connection)

    monkeypatch.setattr(
        builder_module,
        "read_index_receipt_from_connection",
        corrupt_fts_counter,
    )
    published_path = tmp_path / "search-v1.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path, corpus_root=tmp_path)

    with pytest.raises(ValueError, match="document counters disagree"):
        builder.build_candidate(_request(4))

    assert not published_path.exists()
    assert tuple(tmp_path.glob("*.candidate-*.sqlite3")) == ()


def test_rebuild_uses_one_snapshot_then_publishes_under_its_revision_guard(
    tmp_path: Path,
) -> None:
    request = _request(9)
    snapshot = _Snapshot(request)
    builder = SqliteFtsIndexBuilder(
        tmp_path / "search-v1.sqlite3",
        corpus_root=tmp_path,
    )
    service = RebuildSearchIndex(
        catalog=_Reader(snapshot),
        builder=builder,
        revision_guard=_Guard(CatalogRevision(9)),
    )

    published = service.execute(chunk_schema_version="chunk-v1")

    assert snapshot.closed is True
    assert published.catalog_revision == CatalogRevision(9)
    assert read_index_receipt(
        published.path,
        corpus_root=tmp_path,
    ).catalog_revision == CatalogRevision(9)


def test_rebuild_discards_stale_candidate_without_touching_published_index(
    tmp_path: Path,
) -> None:
    published_path = tmp_path / "search-v1.sqlite3"
    builder = SqliteFtsIndexBuilder(published_path, corpus_root=tmp_path)
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
    builder = SqliteFtsIndexBuilder(
        tmp_path / "search-v1.sqlite3",
        corpus_root=tmp_path,
    )
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
