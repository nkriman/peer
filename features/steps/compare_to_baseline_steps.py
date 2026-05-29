"""Step definitions for features/compare_to_baseline.feature (peer-x5w)."""

from __future__ import annotations

import statistics

from behave import given, then, when  # type: ignore[import-untyped]

from peer.eval import (
    AgentConfig,
    EvalReport,
    EvalSampleResult,
    EvalSummary,
    MetricBand,
    MetricResult,
    MultiRunReport,
    compare_to_baseline,
    compare_to_baseline_ci,
    compare_to_baseline_paired_bootstrap,
)


def _multi_run(metric: str, median: float) -> MultiRunReport:
    return MultiRunReport(
        n_runs=3,
        per_run=[],
        metric_bands={
            metric: MetricBand(
                min=median, max=median, median=median, range=0.0, n_judges_included=3
            )
        },
    )


def _multi_run_from_values(metric: str, values: list[float]) -> MultiRunReport:
    cfg = AgentConfig(model="test", system_prompt_hash="x", reviewer_class="test")
    per_run = [
        EvalReport(
            run_id=f"r{i}",
            timestamp="2026-05-27T00:00:00Z",
            agent_config=cfg,
            dataset_path="in-memory",
            dataset_size=0,
            summary=EvalSummary(
                metric_values={metric: v},
                metric_details={metric: {}},
                n_samples_total=0,
                n_samples_succeeded=0,
                n_samples_failed=0,
            ),
            per_sample=[],
        )
        for i, v in enumerate(values)
    ]
    median = statistics.median(values)
    return MultiRunReport(
        n_runs=len(values),
        per_run=per_run,
        metric_bands={
            metric: MetricBand(
                min=min(values),
                max=max(values),
                median=median,
                range=max(values) - min(values),
                n_judges_included=len(values),
            )
        },
    )


@when(
    "I call compare_to_baseline with recipe detection_rate median {rmed:f} "
    "and baseline median {bmed:f} and noise_floor {nf:f}"
)
def step_call_compare(context, rmed: float, bmed: float, nf: float) -> None:
    recipe_report = _multi_run("detection_rate", rmed)
    baseline_report = _multi_run("detection_rate", bmed)
    context.fixtures["comparison"] = compare_to_baseline(
        recipe_report, baseline_report, noise_floor=nf
    )


@when(
    "I call compare_to_baseline with recipe comments_per_pr median {rmed:f} "
    "and baseline median {bmed:f} and noise_floor {nf:f}"
)
def step_call_compare_cpp(context, rmed: float, bmed: float, nf: float) -> None:
    recipe_report = _multi_run("comments_per_pr", rmed)
    baseline_report = _multi_run("comments_per_pr", bmed)
    context.fixtures["comparison"] = compare_to_baseline(
        recipe_report, baseline_report, noise_floor=nf
    )


def _parse_values(s: str) -> list[float]:
    return [float(x.strip()) for x in s.strip("[]").split(",")]


@given("recipe detection_rate per-run values {rvals} and baseline per-run values {bvals}")
def step_per_run_values(context, rvals: str, bvals: str) -> None:
    context.fixtures["recipe_report"] = _multi_run_from_values(
        "detection_rate", _parse_values(rvals)
    )
    context.fixtures["baseline_report"] = _multi_run_from_values(
        "detection_rate", _parse_values(bvals)
    )


@when("I call compare_to_baseline_ci")
def step_call_compare_ci(context) -> None:
    context.fixtures["comparison"] = compare_to_baseline_ci(
        context.fixtures["recipe_report"],
        context.fixtures["baseline_report"],
        n_resamples=2000,
        confidence=0.95,
        seed=0,
    )


@then('the comparison\'s {metric} verdict equals "{verdict}"')
def step_verdict(context, metric: str, verdict: str) -> None:
    comp = context.fixtures["comparison"]
    entry = next(e for e in comp.per_metric if e.metric == metric)
    assert entry.verdict == verdict, f"expected {verdict!r}, got {entry.verdict!r}"


@then("the comparison's {metric} delta equals approximately {expected:f}")
def step_delta(context, metric: str, expected: float) -> None:
    comp = context.fixtures["comparison"]
    entry = next(e for e in comp.per_metric if e.metric == metric)
    assert entry.delta is not None and abs(entry.delta - expected) < 1e-6, (
        f"expected delta≈{expected}, got {entry.delta!r}"
    )


def _multi_run_with_per_sample(metric: str, per_pr: dict[str, float]) -> MultiRunReport:
    cfg = AgentConfig(model="test", system_prompt_hash="x", reviewer_class="test")
    per_sample = [
        EvalSampleResult(
            pr_url=pr,
            metrics={metric: MetricResult(name=metric, value=v)},
        )
        for pr, v in per_pr.items()
    ]
    values = list(per_pr.values())
    median = statistics.median(values)
    report = EvalReport(
        run_id="r0",
        timestamp="2026-05-27T00:00:00Z",
        agent_config=cfg,
        dataset_path="in-memory",
        dataset_size=len(per_sample),
        summary=EvalSummary(
            metric_values={metric: median},
            metric_details={metric: {}},
            n_samples_total=len(per_sample),
            n_samples_succeeded=len(per_sample),
            n_samples_failed=0,
        ),
        per_sample=per_sample,
    )
    return MultiRunReport(
        n_runs=1,
        per_run=[report],
        metric_bands={
            metric: MetricBand(
                min=min(values),
                max=max(values),
                median=median,
                range=max(values) - min(values),
                n_judges_included=1,
            )
        },
    )


@given("recipe and baseline each have one run with per-PR detection_rate pairs")
@given("recipe and baseline each have one run with per-PR detection_rate pairs:")
def step_paired_per_pr(context) -> None:
    recipe_map: dict[str, float] = {}
    baseline_map: dict[str, float] = {}
    for row in context.table:
        recipe_map[row["pr_url"]] = float(row["recipe"])
        baseline_map[row["pr_url"]] = float(row["baseline"])
    context.fixtures["recipe_report"] = _multi_run_with_per_sample("detection_rate", recipe_map)
    context.fixtures["baseline_report"] = _multi_run_with_per_sample("detection_rate", baseline_map)


@when("I call compare_to_baseline_paired_bootstrap")
def step_call_paired_bootstrap(context) -> None:
    # Legacy percentile path (back-compat).
    context.fixtures["comparison"] = compare_to_baseline_paired_bootstrap(
        context.fixtures["recipe_report"],
        context.fixtures["baseline_report"],
        n_resamples=2000,
        confidence=0.95,
        seed=0,
        use_bca=False,
    )


@when("I call compare_to_baseline_paired_bootstrap with BCa and permutation")
def step_call_paired_bca(context) -> None:
    context.fixtures["comparison"] = compare_to_baseline_paired_bootstrap(
        context.fixtures["recipe_report"],
        context.fixtures["baseline_report"],
        n_resamples=2000,
        confidence=0.95,
        seed=0,
        use_bca=True,
        permutation_alpha=0.05,
        n_perms=2000,
    )


@then("the comparison's {metric} has a permutation pvalue below {alpha:f}")
def step_perm_pvalue_below(context, metric: str, alpha: float) -> None:
    comp = context.fixtures["comparison"]
    entry = next(e for e in comp.per_metric if e.metric == metric)
    assert entry.permutation_pvalue is not None, "expected permutation pvalue, got None"
    assert entry.permutation_pvalue < alpha, (
        f"expected pvalue<{alpha}, got {entry.permutation_pvalue}"
    )


@then("the comparison's {metric} has a CI populated")
def step_ci_populated(context, metric: str) -> None:
    comp = context.fixtures["comparison"]
    entry = next(e for e in comp.per_metric if e.metric == metric)
    assert entry.ci_lower is not None and entry.ci_upper is not None, (
        f"expected CI populated, got lower={entry.ci_lower!r} upper={entry.ci_upper!r}"
    )
    assert entry.ci_method and ("bootstrap" in entry.ci_method or "bca" in entry.ci_method), (
        f"expected bootstrap or BCa method, got {entry.ci_method!r}"
    )
