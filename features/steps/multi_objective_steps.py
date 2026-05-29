"""Step definitions for features/multi_objective.feature (multi-objective-v01)."""

from __future__ import annotations

import argparse
from pathlib import Path

from behave import given, then, when  # type: ignore[import-untyped]

from peer.eval.compare import (
    ComparisonEntry,
    ComparisonReport,
    classify_comparison,
)


def _build_report(verdicts: list[str]) -> ComparisonReport:
    """Build a ComparisonReport with one entry per verdict label.

    Numbers are synthetic but consistent with the verdict: delta is
    placed outside / inside the noise band as appropriate. Metric
    names are unique to keep the classifier happy.
    """
    nf = 0.06
    entries: list[ComparisonEntry] = []
    for i, v in enumerate(verdicts):
        if v == "above_noise":
            r_med, b_med = 0.30, 0.10
        elif v == "below_noise":
            r_med, b_med = 0.10, 0.30
        else:  # in_noise
            r_med, b_med = 0.10, 0.10
        entries.append(
            ComparisonEntry(
                metric=f"metric_{i}",
                recipe_median=r_med,
                baseline_median=b_med,
                delta=r_med - b_med,
                verdict=v,  # type: ignore[arg-type]
            )
        )
    return ComparisonReport(
        noise_floor=nf,
        n_runs_recipe=5,
        n_runs_baseline=5,
        per_metric=entries,
    )


def _parse_verdict_list(arg: str) -> list[str]:
    inner = arg.strip().lstrip("[").rstrip("]")
    return [tok.strip() for tok in inner.split(",")]


# ---------------------------------------------------------------------------
# classify_comparison
# ---------------------------------------------------------------------------


@given("a ComparisonReport with verdicts {verdicts}")
def step_given_report(context, verdicts: str) -> None:
    parsed = _parse_verdict_list(verdicts)
    context.fixtures["comparison_report"] = _build_report(parsed)


@when("I call classify_comparison")
def step_call_classify(context) -> None:
    report = context.fixtures["comparison_report"]
    context.fixtures["verdict"] = classify_comparison(report)


@then('the RecipeVerdict overall is "{value}"')
def step_overall_is(context, value: str) -> None:
    got = context.fixtures["verdict"].overall
    assert got == value, f"expected {value!r}, got {got!r}"


@then("the RecipeVerdict n_above_noise is {n:d}")
def step_n_above(context, n: int) -> None:
    got = context.fixtures["verdict"].n_above_noise
    assert got == n, f"expected {n}, got {got}"


@then("the RecipeVerdict n_below_noise is {n:d}")
def step_n_below(context, n: int) -> None:
    got = context.fixtures["verdict"].n_below_noise
    assert got == n, f"expected {n}, got {got}"


# ---------------------------------------------------------------------------
# compute_pareto_front
# ---------------------------------------------------------------------------


def _pareto_report(detection_rate: float, comments_per_pr: float) -> ComparisonReport:
    return ComparisonReport(
        noise_floor=0.06,
        n_runs_recipe=5,
        n_runs_baseline=5,
        per_metric=[
            ComparisonEntry(
                metric="detection_rate",
                recipe_median=detection_rate,
                baseline_median=0.05,
                delta=detection_rate - 0.05,
                verdict="above_noise" if detection_rate > 0.11 else "in_noise",
            ),
            ComparisonEntry(
                metric="comments_per_pr",
                recipe_median=comments_per_pr,
                baseline_median=4.0,
                delta=comments_per_pr - 4.0,
                verdict="below_noise" if comments_per_pr < 3.94 else "in_noise",
            ),
        ],
    )


@given(
    "two ComparisonReports where report-A has detection_rate {dr_a:f} and comments_per_pr {cpr_a:f}"
)
def step_two_reports_a(context, dr_a: float, cpr_a: float) -> None:
    context.fixtures["report_a"] = _pareto_report(dr_a, cpr_a)


@given("report-B has detection_rate {dr_b:f} and comments_per_pr {cpr_b:f}")
def step_two_reports_b(context, dr_b: float, cpr_b: float) -> None:
    context.fixtures["report_b"] = _pareto_report(dr_b, cpr_b)


@when("I call compute_pareto_front")
def step_call_pareto(context) -> None:
    from peer.autoresearch.frontier import compute_pareto_front

    reports = [context.fixtures["report_a"], context.fixtures["report_b"]]
    front, dominated = compute_pareto_front(reports)
    context.fixtures["front"] = front
    context.fixtures["dominated"] = dominated


@then("the front has length {n:d}")
def step_front_len(context, n: int) -> None:
    got = len(context.fixtures["front"])
    assert got == n, f"expected {n}, got {got}"


@then("the dominated has length {n:d}")
def step_dominated_len(context, n: int) -> None:
    got = len(context.fixtures["dominated"])
    assert got == n, f"expected {n}, got {got}"


# ---------------------------------------------------------------------------
# `peer autoresearch frontier` CLI dispatch
# ---------------------------------------------------------------------------


@given("an empty reports directory")
def step_empty_reports_dir(context) -> None:
    import tempfile

    d = tempfile.mkdtemp(prefix="peer_frontier_empty_")
    context.fixtures["reports_dir"] = Path(d)


@when("I dispatch peer autoresearch frontier")
def step_dispatch_frontier(context) -> None:
    from peer.cli import _cmd_autoresearch_frontier

    args = argparse.Namespace(reports_dir=context.fixtures["reports_dir"])
    context.fixtures["frontier_rc"] = _cmd_autoresearch_frontier(args)


@then("the autoresearch frontier rc is {code:d}")
def step_frontier_rc(context, code: int) -> None:
    got = context.fixtures["frontier_rc"]
    assert got == code, f"expected rc={code}, got {got}"
