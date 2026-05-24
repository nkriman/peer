"""Multi-run dispatcher for `peer autoresearch run --n-runs N`.

Single-run path lives in runner.py (one EvalReport, one leaderboard
row). Multi-run path lives here: invokes CrossRunRunner, writes a
MultiRunReport JSON, appends a leaderboard row with median values, and
optionally runs the bare baseline N times for comparison.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..agent import Agent
from ..baselines import BareClaudeCodeReviewer
from ..dataset import JSONLStorage
from ..eval import (
    CrossRunRunner,
    compare_to_baseline,
    render_comparison_summary,
    render_multirun_summary,
)
from ..recipe import Recipe
from .leaderboard import append_row
from .runner import _current_commit_sha, _read_program_md
from .utility import parse_utility_formula

logger = logging.getLogger(__name__)


def _extract_per_metric_median(report: Any, metric: str) -> float | None:
    band = report.metric_bands.get(metric)
    return band.median if band else None


def _sum_n_comments_median(report: Any) -> int | None:
    """Sum n_comments per run, take the median across runs."""
    per_run_totals: list[int] = []
    for r in report.per_run:
        total = 0
        for s in r.per_sample:
            rs = s.review_summary or {}
            n = rs.get("n_comments")
            if isinstance(n, int):
                total += n
        per_run_totals.append(total)
    if not per_run_totals:
        return None
    per_run_totals.sort()
    return per_run_totals[len(per_run_totals) // 2]


def run_multirun_iteration(
    recipe_path: Path | str,
    dataset_path: Path | str,
    leaderboard_path: Path | str,
    description: str,
    program_md_path: Path | str,
    n_runs: int,
    baseline_cmp: bool,
) -> int:
    """Run a recipe N times, optionally also the bare baseline N times,
    write reports + leaderboard row + comparison verdict."""
    leaderboard_path = Path(leaderboard_path)
    commit_sha = _current_commit_sha()
    utility_fn = parse_utility_formula(_read_program_md(program_md_path))

    try:
        recipe = Recipe.from_file(recipe_path)
        recipe_hash = recipe.canonical_hash()
    except Exception as e:
        logger.error("recipe load failed: %s", e)
        return 2

    samples = JSONLStorage(Path(dataset_path)).load_all()

    # ---- Recipe phase: N reruns ----
    logger.info("[multirun] running recipe N=%d", n_runs)
    agent = Agent(recipe=recipe)
    runner = CrossRunRunner(reviewer=agent, dataset=samples, n_runs=n_runs)
    recipe_report = runner.run()

    # Persist the MultiRunReport.
    recipe_out = Path("data/eval_runs") / f"multirun_{recipe_hash}_{commit_sha}.json"
    recipe_out.parent.mkdir(parents=True, exist_ok=True)
    recipe_out.write_text(recipe_report.model_dump_json(indent=2))
    logger.info("[multirun] recipe MultiRunReport -> %s", recipe_out)

    # Leaderboard row with median values.
    detection_med = _extract_per_metric_median(recipe_report, "detection_rate")
    cost_med = _extract_per_metric_median(recipe_report, "cost_usd")  # often n/a; harmless
    n_comments_med = _sum_n_comments_median(recipe_report)
    metrics_dict: dict[str, float | int | None] = {
        "detection_rate": detection_med,
        "n_comments_total": n_comments_med,
        "dataset_size": len(samples),
    }
    utility = utility_fn(metrics_dict)

    append_row(
        leaderboard_path,
        commit_sha=commit_sha,
        recipe_hash=recipe_hash,
        utility=utility,
        detection_rate=detection_med,
        precision_minor=None,
        precision_important=None,
        precision_critical=None,
        cost_usd=cost_med,
        n_comments_total=n_comments_med,
        status="ok",
        description=f"{description} ({n_runs} runs: median)",
    )

    # ---- Print recipe summary ----
    print()
    print(render_multirun_summary(recipe_report))

    # ---- Baseline-cmp phase ----
    if baseline_cmp:
        logger.info("[multirun] running bare baseline N=%d", n_runs)
        baseline_reviewer = BareClaudeCodeReviewer(model_id="sonnet")
        baseline_runner = CrossRunRunner(reviewer=baseline_reviewer, dataset=samples, n_runs=n_runs)
        baseline_report = baseline_runner.run()

        baseline_out = Path("data/eval_runs") / f"multirun_baseline_{commit_sha}.json"
        baseline_out.write_text(baseline_report.model_dump_json(indent=2))
        logger.info("[multirun] baseline MultiRunReport -> %s", baseline_out)

        # Also append a baseline row for the leaderboard's audit trail.
        b_detection = _extract_per_metric_median(baseline_report, "detection_rate")
        b_n_comments = _sum_n_comments_median(baseline_report)
        append_row(
            leaderboard_path,
            commit_sha=commit_sha,
            recipe_hash="bare----",
            utility=b_detection,
            detection_rate=b_detection,
            precision_minor=None,
            precision_important=None,
            precision_critical=None,
            cost_usd=None,
            n_comments_total=b_n_comments,
            status="ok",
            description=f"baseline[bare claude code] ({n_runs} runs: median)",
        )

        comparison = compare_to_baseline(recipe_report, baseline_report)
        cmp_out = Path("data/eval_runs") / f"comparison_{recipe_hash}_{commit_sha}.json"
        cmp_out.write_text(comparison.model_dump_json(indent=2))

        print()
        print(render_comparison_summary(comparison))

    return 0
