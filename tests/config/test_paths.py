from __future__ import annotations

from pathlib import Path

import pytest

from paper_insights.paths import CorpusPaths, PathBoundaryError


def test_all_corpus_paths_are_absolute_and_derived_from_data_root(tmp_path: Path) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")

    assert paths.data_root == (tmp_path / "corpus").resolve()
    assert paths.catalog == paths.data_root / "catalog.sqlite3"
    assert paths.blobs == paths.data_root / "blobs"
    assert paths.search_index == paths.data_root / ".search" / "search-v1.sqlite3"
    assert all(path.is_absolute() for path in paths.all_paths())
    assert not paths.data_root.exists()


def test_confined_rejects_parent_escape(tmp_path: Path) -> None:
    paths = CorpusPaths.from_data_root(tmp_path / "corpus")

    with pytest.raises(PathBoundaryError, match="outside data root"):
        paths.confined(Path("../outside.txt"))


def test_confined_rejects_existing_symlink_escape(tmp_path: Path) -> None:
    data_root = tmp_path / "corpus"
    outside = tmp_path / "outside"
    data_root.mkdir()
    outside.mkdir()
    (data_root / "escape").symlink_to(outside, target_is_directory=True)
    paths = CorpusPaths.from_data_root(data_root)

    with pytest.raises(PathBoundaryError, match="symbolic link"):
        paths.confined(Path("escape/payload.bin"))
