from paper_insights.domain.errors import ErrorCode


class CatalogConflict(RuntimeError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.CATALOG_CONFLICT.value)
