"""Step definitions for features/cross_run.feature (peer-x5w)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from behave import then, when  # type: ignore[import-untyped]

from peer.eval import (
    CrossRunRunner,
    MultiRunReport,
    compute_run_bands,
)
from peer.eval.types import (
    AgentConfig,
    EvalReport,
    EvalSampleResult,
    EvalSummary,
)


def _report_with_value(metric: str, value: float | None) -> EvalReport:
    return EvalReport(
        agent_config=AgentConfig(model="test", reviewer_class="TestReviewer"),
        dataset_path="in-memory",
        dataset_size=1,
        summary=EvalSummary(
            metric_values={metric: value},
            n_samples_total=1,
            n_samples_succeeded=1,
        ),
        per_sample=[EvalSampleResult(pr_url="x")],
    )


# Mock EvalRunner so CrossRunRunner doesn't actually try to hit Anthropic.
@when("I call CrossRunRunner.run with n_runs {n:d}")
def step_call_cross_run(context, n: int) -> None:
    reviewer = context.fixtures["reviewer"]
    dataset = context.fixtures["dataset"]
    n_invocations: list[int] = []

    class _StubEvalRunner:
        def __init__(self, reviewer: Any, dataset: list, **_: Any) -> None:
            self._reviewer = reviewer
            self._dataset = dataset

        async def run_async(self) -> EvalReport:
            # Simulate the reviewer being called once per sample
            for sample in self._dataset:
                reviewer.review(sample.pr_url)
            n_invocations.append(1)
            return _report_with_value("detection_rate", 0.05)

    with patch("peer.eval.cross_run.EvalRunner", _StubEvalRunner):
        runner = CrossRunRunner(reviewer=reviewer, dataset=dataset, n_runs=n)
        context.fixtures["report"] = runner.run()


@when("I attempt to construct a CrossRunRunner with n_runs {n:d}")
def step_attempt_construct(context, n: int) -> None:
    try:
        CrossRunRunner(
            reviewer=context.fixtures["reviewer"],
            dataset=context.fixtures["dataset"],
            n_runs=n,
        )
        context.fixtures["error"] = None
    except Exception as e:
        context.fixtures["error"] = e


@then("the MultiRunReport's per_run has length {n:d}")
def step_per_run_len(context, n: int) -> None:
    report: MultiRunReport = context.fixtures["report"]
    got = len(report.per_run)
    assert got == n, f"expected {n}, got {got}"


# Note: `ValueError is raised` is provided by features/steps/dataset_split_steps.py.
# That impl reads context.fixtures.get("error"); we mirror the construction error
# into the same key in the When-step above.


# Reuse `the counting reviewer was invoked exactly N times` from
# features/steps/peer_deps_followups_steps.py.


@when("I call compute_run_bands on per-run detection_rate values [{v1:f}, {v2:f}, {v3:f}]")
def step_compute_run_bands_three(context, v1: float, v2: float, v3: float) -> None:
    reports = [_report_with_value("detection_rate", v) for v in [v1, v2, v3]]
    bands = compute_run_bands(reports)
    context.fixtures["band"] = bands["detection_rate"]


# Reuse `the band's min/max/median/range/n_judges_included` steps from
# features/steps/eval_cross_judge_steps.py — they read context.fixtures["band"].


@then("dispatching raises SystemExit with code {code:d}")
def step_dispatch_systemexit(context, code: int) -> None:
    """Verify the autoresearch handler enforces the --baseline-cmp + --n-runs 1 conflict."""
    from peer.cli import _cmd_autoresearch_run

    args = context.fixtures["args"]
    rc = _cmd_autoresearch_run(args)
    assert rc == code, f"expected rc={code}, got {rc}"
