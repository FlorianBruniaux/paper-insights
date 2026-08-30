from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from paper_insights.application.ports.catalog import CatalogReader, CatalogUnitOfWorkFactory
from paper_insights.application.ports.clock import Clock
from paper_insights.domain.corpus import (
    InterruptedRunCandidate,
    InterruptedRunRepairResult,
    RepairInterruptedRun,
)
from paper_insights.domain.validation import require_tuples


class RepairConfirmationRequired(ValueError):
    def __init__(self) -> None:
        super().__init__("interrupted run repair requires explicit confirmation")


@dataclass(frozen=True, slots=True)
class InterruptedRunsPreview:
    cutoff: datetime
    candidates: tuple[InterruptedRunCandidate, ...]

    def __post_init__(self) -> None:
        require_tuples(self, "candidates")
        if self.cutoff.tzinfo is None or self.cutoff.utcoffset() != timedelta(0):
            raise ValueError("interrupted run cutoff must use UTC")


class RepairInterruptedRuns:
    def __init__(
        self,
        *,
        reader: CatalogReader,
        catalog: CatalogUnitOfWorkFactory,
        clock: Clock,
        stale_after: timedelta,
    ) -> None:
        if stale_after <= timedelta(0):
            raise ValueError("interrupted run age must be positive")
        self._reader = reader
        self._catalog = catalog
        self._clock = clock
        self._stale_after = stale_after

    def preview(self) -> InterruptedRunsPreview:
        cutoff = self._clock.now() - self._stale_after
        with self._reader.snapshot() as snapshot:
            candidates = snapshot.list_interrupted_runs(cutoff)
        return InterruptedRunsPreview(cutoff=cutoff, candidates=candidates)

    def execute(
        self,
        preview: InterruptedRunsPreview,
        *,
        confirmed: bool,
    ) -> tuple[InterruptedRunRepairResult, ...]:
        if not confirmed:
            raise RepairConfirmationRequired()
        occurred_at = self._clock.now()
        results: list[InterruptedRunRepairResult] = []
        for candidate in preview.candidates:
            command = RepairInterruptedRun(
                run_id=candidate.run_id,
                cutoff=preview.cutoff,
                occurred_at=occurred_at,
            )
            with self._catalog.begin() as unit:
                result = unit.ingestion.repair_interrupted_run(command)
                unit.commit()
            results.append(result)
        return tuple(results)
