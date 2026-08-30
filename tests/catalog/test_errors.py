from paper_insights.adapters.catalog.sqlite.errors import CatalogConflict
from paper_insights.domain.errors import ErrorCode


def test_catalog_conflict_exposes_the_closed_error_code() -> None:
    error = CatalogConflict()

    assert error.code is ErrorCode.CATALOG_CONFLICT
    assert str(error) == ErrorCode.CATALOG_CONFLICT.value
