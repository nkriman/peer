"""Step definitions for features/autoresearch_diagnose.feature (peer-l6l)."""

from __future__ import annotations

from behave import given, then, when  # type: ignore[import-untyped]

from peer.autoresearch.diagnose import (
    CostOutlier,
    CostOutlierSummary,
    DriftSample,
    FailureSummary,
    PerSeverityCount,
    PrecisionMiss,
    TopicDriftSummary,
    extract_cost_outliers,
    extract_failure_modes,
    extract_precision_misses,
    extract_topic_drift,
    render_markdown,
)
from peer.eval.types import (
    AgentConfig,
    EvalReport,
    EvalSampleResult,
    EvalSummary,
    MetricResult,
)

# ---------------------------------------------------------------------------
# Synthetic EvalReport builders
# ---------------------------------------------------------------------------


def _sample_with_unmatched(pr_url: str, sev_counts: dict[str, int]) -> EvalSampleResult:
    """Build a per-sample with `mean_per_pr_recall.unmatched_gold` = sev_counts."""
    unmatched_gold: list[dict] = []
    for sev, n in sev_counts.items():
        for i in range(n):
            unmatched_gold.append(
                {
                    "path": f"src/{sev}_{i}.py",
                    "line": 10 + i,
                    "severity": sev,
                    "description": f"{sev} desc {i}",
                }
            )
    return EvalSampleResult(
        pr_url=pr_url,
        metrics={
            "mean_per_pr_recall": MetricResult(
                name="mean_per_pr_recall",
                value=0.0,
                per_sample_detail={"unmatched_gold": unmatched_gold},
            ),
        },
    )


def _report(samples: list[EvalSampleResult]) -> EvalReport:
    return EvalReport(
        agent_config=AgentConfig(model="test", reviewer_class="TestReviewer"),
        dataset_path="in-memory",
        dataset_size=len(samples),
        summary=EvalSummary(
            n_samples_total=len(samples),
            n_samples_succeeded=len(samples),
        ),
        per_sample=samples,
    )


# ---------------------------------------------------------------------------
# extract_failure_modes
# ---------------------------------------------------------------------------


@given(
    "a synthetic EvalReport with 3 samples and unmatched_gold severity counts "
    "[important=5; critical=1, minor=2; important=1, nit=3]"
)
def step_synthetic_failure_report(context) -> None:
    s1 = _sample_with_unmatched("https://example/a", {"important": 5})
    s2 = _sample_with_unmatched("https://example/b", {"critical": 1, "minor": 2})
    s3 = _sample_with_unmatched("https://example/c", {"important": 1, "nit": 3})
    context.fixtures["report"] = _report([s1, s2, s3])


@when("I call extract_failure_modes")
def step_extract_fm(context) -> None:
    context.fixtures["failure"] = extract_failure_modes(context.fixtures["report"])


@then(
    "the returned FailureSummary's per-severity totals equal "
    "{{critical: {c:d}, important: {i:d}, minor: {m:d}, nit: {n:d}}}"
)
def step_failure_severity(context, c: int, i: int, m: int, n: int) -> None:
    s = context.fixtures["failure"].per_severity
    assert (s.critical, s.important, s.minor, s.nit) == (c, i, m, n), (
        f"expected ({c},{i},{m},{n}), got ({s.critical},{s.important},{s.minor},{s.nit})"
    )


@then("the FailureSummary's n_samples_with_misses equals {n:d}")
def step_n_samples_with_misses(context, n: int) -> None:
    got = context.fixtures["failure"].n_samples_with_misses
    assert got == n, f"expected {n}, got {got}"


# ---------------------------------------------------------------------------
# extract_topic_drift
# ---------------------------------------------------------------------------


@given(
    "a synthetic EvalReport with 1 sample where peer emitted 3 comments and matched 0 gold defects"
)
def step_synthetic_drift_report(context) -> None:
    s = EvalSampleResult(
        pr_url="https://example/drift",
        review_summary={"n_comments": 3},
        metrics={
            "detection_rate": MetricResult(
                name="detection_rate",
                value=0.0,
                per_sample_detail={"matched_count": 0, "total_gold": 2},
            ),
            "mean_per_pr_recall": MetricResult(
                name="mean_per_pr_recall",
                value=0.0,
                per_sample_detail={
                    "unmatched_gold": [
                        {
                            "path": "src/foo.py",
                            "line": 50,
                            "severity": "important",
                            "description": "missed",
                        }
                    ]
                },
            ),
            "novelty_rate": MetricResult(
                name="novelty_rate",
                value=1.0,
                per_sample_detail={
                    "unmatched_peer": [
                        {"path": "src/bar.py", "line": i, "severity": "minor", "body": f"b{i}"}
                        for i in range(3)
                    ]
                },
            ),
        },
    )
    context.fixtures["report"] = _report([s])


@when("I call extract_topic_drift")
def step_extract_drift(context) -> None:
    context.fixtures["drift"] = extract_topic_drift(context.fixtures["report"])


@then("the TopicDriftSummary has {n:d} sample in drift_samples")
@then("the TopicDriftSummary has {n:d} samples in drift_samples")
def step_drift_n(context, n: int) -> None:
    got = len(context.fixtures["drift"].drift_samples)
    assert got == n, f"expected {n}, got {got}"


# ---------------------------------------------------------------------------
# extract_cost_outliers
# ---------------------------------------------------------------------------


@given("a synthetic EvalReport whose per-sample costs are [{c1:f}, {c2:f}, {c3:f}, {c4:f}]")
def step_synthetic_cost_report(context, c1: float, c2: float, c3: float, c4: float) -> None:
    samples = []
    for i, cost in enumerate([c1, c2, c3, c4]):
        samples.append(
            EvalSampleResult(
                pr_url=f"https://example/s{i}",
                cost_usd=cost,
                review_summary={"n_comments": 1},
                metrics={},
            )
        )
    context.fixtures["report"] = _report(samples)


@when("I call extract_cost_outliers with n_top {n:d}")
def step_extract_cost(context, n: int) -> None:
    context.fixtures["cost"] = extract_cost_outliers(context.fixtures["report"], n_top=n)


@then("the CostOutlierSummary's top has cost {c:f} first")
def step_cost_first(context, c: float) -> None:
    got = context.fixtures["cost"].top[0].cost_usd
    assert abs(got - c) < 1e-9, f"expected {c}, got {got}"


@then("the CostOutlierSummary's top has cost {c:f} second")
def step_cost_second(context, c: float) -> None:
    got = context.fixtures["cost"].top[1].cost_usd
    assert abs(got - c) < 1e-9, f"expected {c}, got {got}"


# ---------------------------------------------------------------------------
# extract_precision_misses
# ---------------------------------------------------------------------------


@given("a synthetic EvalReport with 1 sample where peer emitted 4 comments and matched 1 gold")
def step_synthetic_precision_report(context) -> None:
    s = EvalSampleResult(
        pr_url="https://example/p",
        review_summary={"n_comments": 4},
        metrics={
            "detection_rate": MetricResult(
                name="detection_rate",
                value=0.5,
                per_sample_detail={"matched_count": 1, "total_gold": 2},
            ),
            "novelty_rate": MetricResult(
                name="novelty_rate",
                value=0.75,
                per_sample_detail={
                    "unmatched_peer": [
                        {"path": "src/x.py", "line": i, "severity": "minor", "body": f"b{i}"}
                        for i in range(3)
                    ]
                },
            ),
        },
    )
    context.fixtures["report"] = _report([s])


@when("I call extract_precision_misses")
def step_extract_pm(context) -> None:
    pm = extract_precision_misses(context.fixtures["report"])
    context.fixtures["pm"] = pm
    # Mirror into "findings" so the existing step (linter_context_steps:85)
    # `the returned list has length N` can locate it.
    context.fixtures["findings"] = pm


# Note: `the returned list has length N` is provided by
# features/steps/linter_context_steps.py — reused here.


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------


def _populated_inputs() -> tuple[
    FailureSummary, TopicDriftSummary, CostOutlierSummary, list[PrecisionMiss]
]:
    failure = FailureSummary(
        per_severity=PerSeverityCount(critical=1, important=3),
        n_samples_with_misses=2,
        n_unmatched_total=4,
        samples=[
            {"pr_url": "https://example/a", "per_severity": {"important": 3}, "n_unmatched": 3}
        ],
    )
    drift = TopicDriftSummary(
        drift_samples=[
            DriftSample(
                pr_url="https://example/b",
                n_peer_comments=2,
                peer_locations=[{"path": "p", "line": 1, "body": "b"}],
                gold_locations=[{"path": "p", "line": 9, "severity": "minor", "description": "d"}],
            )
        ]
    )
    cost = CostOutlierSummary(
        top=[CostOutlier(pr_url="https://example/c", cost_usd=0.05, n_comments=2)],
        total_cost_usd=0.10,
    )
    pm = [
        PrecisionMiss(
            pr_url="https://example/d",
            path="src/y.py",
            line=5,
            severity="minor",
            body="some body",
        )
    ]
    return failure, drift, cost, pm


@given("populated diagnose inputs")
def step_populated(context) -> None:
    context.fixtures["inputs"] = _populated_inputs()


@when("I call render_markdown")
def step_render_once(context) -> None:
    inputs = context.fixtures["inputs"]
    context.fixtures["rendered"] = render_markdown(*inputs)


@when("I call render_markdown twice")
def step_render_twice(context) -> None:
    inputs = context.fixtures["inputs"]
    context.fixtures["rendered_a"] = render_markdown(*inputs)
    context.fixtures["rendered_b"] = render_markdown(*inputs)


# Note: `the rendered output contains "..."` is provided by
# features/steps/patch_suggestions_followups_steps.py — to reuse it we mirror
# into the "rendered" fixture (which it already reads).


@then("the two outputs are byte-equal")
def step_byte_equal(context) -> None:
    a = context.fixtures["rendered_a"]
    b = context.fixtures["rendered_b"]
    assert a == b, f"outputs differ:\n--- A ---\n{a[:500]}\n--- B ---\n{b[:500]}"
