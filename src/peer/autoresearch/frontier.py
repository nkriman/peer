"""Pareto-frontier reader/renderer over comparison reports (multi-objective-v01).

`peer autoresearch frontier` reads all `comparison_*.json` under a reports
directory, computes the non-dominated set across every measured metric, and
prints both the front and the dominated entries. The leaderboard.tsv is left
alone — these JSON files are the source of per-metric truth.

A "comparison" is a recipe-vs-baseline ComparisonReport written by
`peer autoresearch run --baseline-cmp --n-runs N`. The Pareto comparison
uses each report's recipe-side medians (per metric). A report dominates
another iff it is >= on every measured metric and > on at least one.
"""

from __future__ import annotations

from pathlib import Path

from ..eval.compare import LOWER_IS_BETTER, ComparisonReport, classify_comparison

# Re-export with underscore name to preserve any prior internal imports.
_LOWER_IS_BETTER: frozenset[str] = LOWER_IS_BETTER


def read_comparison_reports(reports_dir: Path) -> list[tuple[Path, ComparisonReport]]:
    """Discover and load every `comparison_*.json` under `reports_dir`.

    Returns list of (path, report) sorted by path so output is stable.
    Returns [] if the directory does not exist.
    """
    if not reports_dir.exists():
        return []
    paths = sorted(reports_dir.glob("comparison_*.json"))
    out: list[tuple[Path, ComparisonReport]] = []
    for p in paths:
        try:
            out.append((p, ComparisonReport.model_validate_json(p.read_text())))
        except Exception:
            continue
    return out


def _metric_value(report: ComparisonReport, metric: str) -> float | None:
    for e in report.per_metric:
        if e.metric == metric:
            return e.recipe_median
    return None


def _all_measured_metrics(reports: list[ComparisonReport]) -> list[str]:
    seen: set[str] = set()
    for r in reports:
        for e in r.per_metric:
            if e.verdict is not None:
                seen.add(e.metric)
    return sorted(seen)


def _dominates(a: ComparisonReport, b: ComparisonReport, metrics: list[str]) -> bool:
    """Return True iff `a` weakly dominates `b` and strictly dominates on ≥1.

    Skips metrics where either side is unmeasured (None).
    """
    strictly_better = False
    for m in metrics:
        va = _metric_value(a, m)
        vb = _metric_value(b, m)
        if va is None or vb is None:
            continue
        if m in _LOWER_IS_BETTER:
            if va > vb:
                return False
            if va < vb:
                strictly_better = True
        else:
            if va < vb:
                return False
            if va > vb:
                strictly_better = True
    return strictly_better


def compute_pareto_front(
    reports: list[ComparisonReport],
) -> tuple[list[ComparisonReport], list[ComparisonReport]]:
    """Partition reports into (front, dominated).

    `front` = non-dominated set. `dominated` = the rest.
    """
    metrics = _all_measured_metrics(reports)
    front: list[ComparisonReport] = []
    dominated: list[ComparisonReport] = []
    for i, r in enumerate(reports):
        is_dominated = False
        for j, other in enumerate(reports):
            if i == j:
                continue
            if _dominates(other, r, metrics):
                is_dominated = True
                break
        if is_dominated:
            dominated.append(r)
        else:
            front.append(r)
    return front, dominated


def render_frontier(
    paired_front: list[tuple[Path, ComparisonReport]],
    paired_dominated: list[tuple[Path, ComparisonReport]],
) -> str:
    """Markdown rendering of front + dominated tables."""
    all_reports = [r for _, r in paired_front + paired_dominated]
    metrics = _all_measured_metrics(all_reports)

    def _row(path: Path, report: ComparisonReport) -> str:
        verdict = classify_comparison(report)
        cells = [path.stem, verdict.overall]
        for m in metrics:
            v = _metric_value(report, m)
            cells.append("n/a" if v is None else f"{v:.4f}")
        return "| " + " | ".join(cells) + " |"

    header_cols = ["report", "verdict", *metrics]
    header = "| " + " | ".join(header_cols) + " |"
    sep = "|" + "|".join(["---"] * len(header_cols)) + "|"

    lines: list[str] = []
    lines.append("# Pareto frontier")
    lines.append("")
    lines.append(
        f"front: {len(paired_front)} non-dominated; dominated: {len(paired_dominated)}. "
        f"Metrics: {', '.join(metrics) if metrics else '(none measured)'}."
    )
    lines.append("")
    lines.append("## Front (non-dominated)")
    lines.append("")
    if paired_front:
        lines.append(header)
        lines.append(sep)
        for path, report in paired_front:
            lines.append(_row(path, report))
    else:
        lines.append("(empty)")
    lines.append("")
    lines.append("## Dominated")
    lines.append("")
    if paired_dominated:
        lines.append(header)
        lines.append(sep)
        for path, report in paired_dominated:
            lines.append(_row(path, report))
    else:
        lines.append("(none)")
    lines.append("")
    return "\n".join(lines)
