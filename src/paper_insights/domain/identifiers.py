from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID


_SOURCE_ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ARXIV_ID = re.compile(r"^(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})$")
_ARXIV_VERSION = re.compile(r"^(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})v[1-9]\d*$")
_DOI = re.compile(r"^10\.\d{4,9}/[^\s/]+(?:/[^\s/]+)*$")


@dataclass(frozen=True, slots=True)
class SourceId:
    value: str

    def __post_init__(self) -> None:
        if not _SOURCE_ID.fullmatch(self.value):
            raise ValueError("source ID must be a canonical lowercase slug")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Sha256:
    value: str

    def __post_init__(self) -> None:
        if not _SHA256.fullmatch(self.value):
            raise ValueError("SHA-256 must contain 64 lowercase hexadecimal characters")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class UUIDv7Id:
    value: UUID

    def __post_init__(self) -> None:
        if self.value.version != 7:
            raise ValueError("identifier must be UUIDv7")

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class PaperId(UUIDv7Id):
    pass


@dataclass(frozen=True, slots=True)
class PaperVersionId(UUIDv7Id):
    pass


@dataclass(frozen=True, slots=True)
class VersionObservationId(UUIDv7Id):
    pass


@dataclass(frozen=True, slots=True)
class AuthorId(UUIDv7Id):
    pass


@dataclass(frozen=True, slots=True)
class BlobId(UUIDv7Id):
    pass


@dataclass(frozen=True, slots=True)
class SnapshotId(UUIDv7Id):
    pass


@dataclass(frozen=True, slots=True)
class ArtifactId(UUIDv7Id):
    pass


@dataclass(frozen=True, slots=True)
class RunId(UUIDv7Id):
    pass


@dataclass(frozen=True, slots=True)
class CollectionId(UUIDv7Id):
    pass


@dataclass(frozen=True, slots=True)
class WatchlistId(UUIDv7Id):
    pass


@dataclass(frozen=True, slots=True)
class AnalysisId(UUIDv7Id):
    pass


@dataclass(frozen=True, slots=True)
class IdentityEventId(UUIDv7Id):
    pass


@dataclass(frozen=True, slots=True)
class PassageId(Sha256):
    pass


@dataclass(frozen=True, slots=True)
class PaperSelector:
    paper_id: PaperId | None = None
    arxiv_id: str | None = None
    doi: str | None = None

    def __post_init__(self) -> None:
        if sum(value is not None for value in (self.paper_id, self.arxiv_id, self.doi)) != 1:
            raise ValueError("paper selector requires exactly one identifier")
        if self.arxiv_id is not None and not _ARXIV_ID.fullmatch(self.arxiv_id):
            raise ValueError("invalid canonical arXiv identifier")
        if self.doi is not None:
            canonical_doi = self.doi == self.doi.lower() and _DOI.fullmatch(self.doi)
            if not canonical_doi:
                raise ValueError("invalid canonical DOI")

    @classmethod
    def by_arxiv(cls, value: str) -> PaperSelector:
        return cls(arxiv_id=value)

    @classmethod
    def by_doi(cls, value: str) -> PaperSelector:
        return cls(doi=value)


@dataclass(frozen=True, slots=True)
class VersionSelector:
    paper_version_id: PaperVersionId | None = None
    source_id: SourceId | None = None
    source_version_key: str | None = None
    current: bool = False

    def __post_init__(self) -> None:
        by_id = (
            self.paper_version_id is not None
            and self.source_id is None
            and self.source_version_key is None
            and not self.current
        )
        by_source = (
            self.paper_version_id is None
            and self.source_id is not None
            and self.source_version_key is not None
            and not self.current
        )
        by_current = (
            self.paper_version_id is None
            and self.source_id is not None
            and self.source_version_key is None
            and self.current
        )
        if sum((by_id, by_source, by_current)) != 1:
            raise ValueError("version selector requires exactly one selector form")
        if (
            by_source
            and self.source_id == SourceId("arxiv")
            and not _ARXIV_VERSION.fullmatch(self.source_version_key or "")
        ):
            raise ValueError("arXiv version selector requires a complete version key")

    @classmethod
    def by_source_version(cls, source_id: SourceId, value: str) -> VersionSelector:
        return cls(source_id=source_id, source_version_key=value)

    @classmethod
    def current_for(cls, source_id: SourceId) -> VersionSelector:
        return cls(source_id=source_id, current=True)
