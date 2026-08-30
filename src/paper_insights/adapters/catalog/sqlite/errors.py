from paper_insights.domain.errors import ErrorCode


class CatalogConflict(RuntimeError):
    code: ErrorCode = ErrorCode.CATALOG_CONFLICT

    def __init__(self) -> None:
        super().__init__(self.code.value)
