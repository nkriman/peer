"""Multi-run averaging primitive (cross-run-v01).

Same shape as `cross_judge` but loops the *reviewer* instead of the
judge. After the noise-floor finding (same recipe + temperature=0
producing 2.5× different DR across runs), this is the primitive every
"recipe A beats recipe B" claim should be expressed through.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..dataset.types import GoldSample
from .cross_judge import MetricBand, compute_variance_bands
from .runner import EvalRunner
from .types import EvalReport

logger = logging.getLogger(__name__)


class MultiRunReport(BaseModel):
    """Output of CrossRunRunner: per-run EvalReports + per-metric bands."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    n_runs: int
    per_run: list[EvalReport] = Field(default_factory=list)
    metric_bands: dict[str, MetricBand] = Field(default_factory=dict)


def compute_run_bands(reports: list[EvalReport]) -> dict[str, MetricBand]:
    """Aggregate per-metric values across reruns of the same recipe.

    Semantically distinct from `compute_variance_bands` (which aggregates
    across judges of the same review) but mathematically identical — delegated
    to the same helper.
    """
    return compute_variance_bands(reports)


class CrossRunRunner:
    """Run the same reviewer N times against the same dataset.

    Sequential by default — each run independent. Cost is N× single-run
    cost; on CLI subscription that's $0 either way.
    """

    def __init__(
        self,
        reviewer: Any,
        dataset: list[GoldSample],
        n_runs: int = 3,
        concurrency: int = 5,
    ) -> None:
        if n_runs <= 0:
            raise ValueError(f"n_runs must be >= 1; got {n_runs}")
        self.reviewer = reviewer
        self.dataset = list(dataset)
        self.n_runs = int(n_runs)
        self.concurrency = max(1, int(concurrency))

    def run(self) -> MultiRunReport:
        return asyncio.run(self.run_async())

    async def run_async(self) -> MultiRunReport:
        per_run: list[EvalReport] = []
        for i in range(self.n_runs):
            logger.info("[cross_run] run %d/%d", i + 1, self.n_runs)
            runner = EvalRunner(
                reviewer=self.reviewer,
                dataset=self.dataset,
                concurrency=self.concurrency,
            )
            report = await runner.run_async()
            per_run.append(report)
        bands = compute_run_bands(per_run)
        return MultiRunReport(n_runs=self.n_runs, per_run=per_run, metric_bands=bands)


def render_multirun_summary(report: MultiRunReport) -> str:
    """Markdown summary: per-metric bands + per-run breakdown."""
    lines: list[str] = []
    lines.append("# Multi-run report")
    lines.append("")
    lines.append(f"N runs: {report.n_runs}")
    lines.append("")
    lines.append("## Per-metric bands (across reruns)")
    lines.append("")
    lines.append("| metric | min | median | max | range | n |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for name in sorted(report.metric_bands):
        band = report.metric_bands[name]
        lines.append(
            f"| {name} | "
            f"{_fmt(band.min)} | {_fmt(band.median)} | {_fmt(band.max)} | "
            f"{_fmt(band.range)} | {band.n_judges_included} |"
        )
    lines.append("")
    lines.append("## Per-run detection_rate")
    lines.append("")
    for i, r in enumerate(report.per_run, start=1):
        dr = (r.summary.metric_values or {}).get("detection_rate")
        lines.append(f"- run {i}: detection_rate={_fmt(dr)}")
    lines.append("")
    return "\n".join(lines)


def _fmt(v: float | int | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:.4f}"
