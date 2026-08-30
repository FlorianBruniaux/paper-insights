from __future__ import annotations

import io
import json
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from paper_insights.domain.corpus import CollectionView
from paper_insights.domain.identifiers import CollectionId, PaperSelector
from paper_insights.interfaces.cli.app import run

COLLECTION_ID = CollectionId(UUID("01890f3e-3b12-7cc0-98d6-4f6f94748f51"))
NOW = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)


class _Collections:
    def __init__(self) -> None:
        self.current: CollectionView | None = None
        self.last_selector: PaperSelector | None = None

    def create(self, *, slug: str, title: str) -> CollectionView:
        self.current = CollectionView(
            collection_id=COLLECTION_ID,
            slug=slug,
            title=title,
            paper_count=0,
            created_at=NOW,
            updated_at=NOW,
        )
        return self.current

    def rename(self, collection_id: CollectionId, *, title: str) -> CollectionView:
        assert self.current is not None
        assert collection_id == self.current.collection_id
        self.current = CollectionView(
            collection_id=collection_id,
            slug=self.current.slug,
            title=title,
            paper_count=self.current.paper_count,
            created_at=NOW,
            updated_at=NOW,
        )
        return self.current

    def add(
        self,
        collection_id: CollectionId,
        paper: PaperSelector,
        *,
        note: str | None = None,
    ) -> CollectionView:
        del note
        assert self.current is not None
        assert collection_id == self.current.collection_id
        self.last_selector = paper
        self.current = CollectionView(
            collection_id=collection_id,
            slug=self.current.slug,
            title=self.current.title,
            paper_count=1,
            created_at=NOW,
            updated_at=NOW,
        )
        return self.current

    def remove(self, collection_id: CollectionId, paper: PaperSelector) -> CollectionView:
        assert self.current is not None
        assert collection_id == self.current.collection_id
        self.last_selector = paper
        self.current = CollectionView(
            collection_id=collection_id,
            slug=self.current.slug,
            title=self.current.title,
            paper_count=0,
            created_at=NOW,
            updated_at=NOW,
        )
        return self.current

    def list(self) -> tuple[CollectionView, ...]:
        return () if self.current is None else (self.current,)


def _invoke(arguments: list[str], service: _Collections, data_root: Path) -> dict[str, object]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(
        arguments,
        doctor_service_factory=lambda _settings: (_ for _ in ()).throw(AssertionError),
        collections_service_factory=lambda _settings: nullcontext(service),
        environ={"PAPER_INSIGHTS_DATA_ROOT": str(data_root)},
        stdout=stdout,
        stderr=stderr,
    )
    assert code == 0
    assert stderr.getvalue() == ""
    return json.loads(stdout.getvalue())


def test_collection_cli_covers_create_rename_list_add_and_remove(tmp_path: Path) -> None:
    service = _Collections()
    root = tmp_path / "corpus"

    created = _invoke(
        ["collections", "create", "article-agents", "--title", "Article agents", "--json"],
        service,
        root,
    )
    renamed = _invoke(
        ["collections", "rename", "article-agents", "--title", "Agent papers", "--json"],
        service,
        root,
    )
    added = _invoke(
        ["collections", "add", "article-agents", "arxiv:2608.01234", "--json"],
        service,
        root,
    )
    listed = _invoke(["collections", "list", "--json"], service, root)
    removed = _invoke(
        ["collections", "remove", "article-agents", "arxiv:2608.01234", "--json"],
        service,
        root,
    )

    assert created["data"]["collection"]["slug"] == "article-agents"  # type: ignore[index]
    assert renamed["data"]["collection"]["title"] == "Agent papers"  # type: ignore[index]
    assert added["data"]["collection"]["paper_count"] == 1  # type: ignore[index]
    assert listed["data"]["collections"][0]["paper_count"] == 1  # type: ignore[index]
    assert removed["data"]["collection"]["paper_count"] == 0  # type: ignore[index]
    assert service.last_selector == PaperSelector.by_arxiv("2608.01234")
    assert all(
        payload["schema_version"] == "paper-insights.cli.v1"
        for payload in (created, renamed, added, listed, removed)
    )
