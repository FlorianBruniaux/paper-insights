from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class PathBoundaryError(ValueError):
    """A requested corpus path crosses the configured data boundary."""


@dataclass(frozen=True, slots=True)
class CorpusPaths:
    data_root: Path
    catalog: Path
    blobs: Path
    search_directory: Path
    search_index: Path

    @classmethod
    def from_data_root(cls, data_root: Path) -> CorpusPaths:
        root = data_root.expanduser().resolve(strict=False)
        return cls(
            data_root=root,
            catalog=root / "catalog.sqlite3",
            blobs=root / "blobs",
            search_directory=root / ".search",
            search_index=root / ".search" / "search-v1.sqlite3",
        )

    def all_paths(self) -> tuple[Path, ...]:
        return (
            self.data_root,
            self.catalog,
            self.blobs,
            self.search_directory,
            self.search_index,
        )

    def confined(self, relative_path: Path) -> Path:
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise PathBoundaryError("path is outside data root")

        current = self.data_root
        for part in relative_path.parts:
            current = current / part
            if current.is_symlink():
                raise PathBoundaryError("symbolic link is not allowed in a corpus path")

        candidate = (self.data_root / relative_path).resolve(strict=False)
        if not candidate.is_relative_to(self.data_root):
            raise PathBoundaryError("path is outside data root")
        return candidate
