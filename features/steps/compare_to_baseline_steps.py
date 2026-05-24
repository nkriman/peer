"""Step definitions for features/compare_to_baseline.feature (peer-x5w)."""

from __future__ import annotations

from behave import then, when  # type: ignore[import-untyped]

from peer.eval import MetricBand, MultiRunReport, compare_to_baseline


def _multi_run(median: float) -> MultiRunReport:
    return MultiRunReport(
        n_runs=3,
        per_run=[],
        metric_bands={
            "detection_rate": MetricBand(
                min=median, max=median, median=median, range=0.0, n_judges_included=3
            )
        },
    )


@when(
    "I call compare_to_baseline with recipe detection_rate median {rmed:f} "
    "and baseline median {bmed:f} and noise_floor {nf:f}"
)
def step_call_compare(context, rmed: float, bmed: float, nf: float) -> None:
    recipe_report = _multi_run(rmed)
    baseline_report = _multi_run(bmed)
    context.fixtures["comparison"] = compare_to_baseline(
        recipe_report, baseline_report, noise_floor=nf
    )


@then('the comparison\'s detection_rate verdict equals "{verdict}"')
def step_verdict(context, verdict: str) -> None:
    comp = context.fixtures["comparison"]
    entry = next(e for e in comp.per_metric if e.metric == "detection_rate")
    assert entry.verdict == verdict, f"expected {verdict!r}, got {entry.verdict!r}"


@then("the comparison's detection_rate delta equals approximately {expected:f}")
def step_delta(context, expected: float) -> None:
    comp = context.fixtures["comparison"]
    entry = next(e for e in comp.per_metric if e.metric == "detection_rate")
    assert entry.delta is not None and abs(entry.delta - expected) < 1e-6, (
        f"expected delta≈{expected}, got {entry.delta!r}"
    )
