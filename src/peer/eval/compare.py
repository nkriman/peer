"""Recipe-vs-baseline comparison (cross-run-v01).

`compare_to_baseline` takes two MultiRunReports and classifies each
metric's delta as `above_noise` / `in_noise` / `below_noise` given a
noise_floor threshold.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .cross_run import MultiRunReport

Verdict = Literal["above_noise", "in_noise", "below_noise"]


class ComparisonEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    recipe_median: float | None
    baseline_median: float | None
    delta: float | None
    verdict: Verdict | None


class ComparisonReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    noise_floor: float
    n_runs_recipe: int
    n_runs_baseline: int
    per_metric: list[ComparisonEntry] = Field(default_factory=list)


def compare_to_baseline(
    recipe_report: MultiRunReport,
    baseline_report: MultiRunReport,
    noise_floor: float = 0.06,
) -> ComparisonReport:
    """Classify recipe vs baseline per-metric.

    `noise_floor` default of 0.06 matches the reviewer-side run-to-run
    variance we measured on the hard subset (see
    `data/autoresearch/may24/noise_floor_finding.md`). Real corpora
    should calibrate their own.
    """
    metric_names: set[str] = set()
    metric_names.update(recipe_report.metric_bands.keys())
    metric_names.update(baseline_report.metric_bands.keys())

    entries: list[ComparisonEntry] = []
    for name in sorted(metric_names):
        r_band = recipe_report.metric_bands.get(name)
        b_band = baseline_report.metric_bands.get(name)
        r_med = r_band.median if r_band else None
        b_med = b_band.median if b_band else None
        if r_med is None or b_med is None:
            entries.append(
                ComparisonEntry(
                    metric=name,
                    recipe_median=r_med,
                    baseline_median=b_med,
                    delta=None,
                    verdict=None,
                )
            )
            continue
        delta = r_med - b_med
        if delta > noise_floor:
            verdict: Verdict = "above_noise"
        elif delta < -noise_floor:
            verdict = "below_noise"
        else:
            verdict = "in_noise"
        entries.append(
            ComparisonEntry(
                metric=name,
                recipe_median=r_med,
                baseline_median=b_med,
                delta=delta,
                verdict=verdict,
            )
        )

    return ComparisonReport(
        noise_floor=noise_floor,
        n_runs_recipe=recipe_report.n_runs,
        n_runs_baseline=baseline_report.n_runs,
        per_metric=entries,
    )


def render_comparison_summary(report: ComparisonReport) -> str:
    """Markdown summary of recipe-vs-baseline verdicts."""
    lines: list[str] = []
    lines.append("# Recipe vs Baseline comparison")
    lines.append("")
    lines.append(
        f"recipe: N={report.n_runs_recipe} runs; baseline: N={report.n_runs_baseline} runs; "
        f"noise_floor: {report.noise_floor}"
    )
    lines.append("")
    lines.append("| metric | recipe_median | baseline_median | delta | verdict |")
    lines.append("|---|---:|---:|---:|:---|")
    for e in report.per_metric:
        verdict_str: str = str(e.verdict) if e.verdict else "n/a"
        if e.verdict == "above_noise":
            verdict_str = f"✓ {e.verdict}"
        elif e.verdict == "below_noise":
            verdict_str = f"✗ {e.verdict}"
        elif e.verdict == "in_noise":
            verdict_str = f"— {e.verdict}"
        lines.append(
            f"| {e.metric} | "
            f"{_fmt(e.recipe_median)} | {_fmt(e.baseline_median)} | "
            f"{_fmt(e.delta)} | {verdict_str} |"
        )
    lines.append("")
    return "\n".join(lines)


def _fmt(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:+.4f}" if v < 0 or v > 0 else f"{v:.4f}"
