from __future__ import annotations

from typing import BinaryIO, Protocol

from paper_insights.domain.corpus import BlobInspection, BlobWrite, StoredBlobRef


class BlobStore(Protocol):
    def put(self, blob: BlobWrite) -> StoredBlobRef: ...

    def open_verified(self, ref: StoredBlobRef) -> BinaryIO: ...

    def inspect(self, ref: StoredBlobRef) -> BlobInspection: ...
