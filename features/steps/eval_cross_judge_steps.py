"""Step definitions for features/eval_cross_judge.feature (peer-iaj)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from behave import given, then, when  # type: ignore[import-untyped]

from peer.eval import (
    CrossJudgeReport,
    CrossJudgeRunner,
    MetricBand,
    compute_variance_bands,
    render_cross_judge_summary,
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


# ---------------------------------------------------------------------------
# Reviewer-runs-once scenarios
# ---------------------------------------------------------------------------


class _CountingReviewer:
    model = "test:counting"

    def __init__(self) -> None:
        self.count = 0

    def review(self, pr_url: str) -> Any:
        from peer.types import Review

        self.count += 1
        return Review(
            comments=[],
            reason="test",
            usage={"input_tokens": 0, "output_tokens": 0, "model": "test"},
        )


@given("a counting PR-Reviewer and a {n:d}-sample dataset")
def step_counting_dataset(context, n: int) -> None:
    from peer.dataset.types import GoldSample

    context.fixtures["reviewer"] = _CountingReviewer()
    context.fixtures["dataset"] = [
        GoldSample(pr_url=f"https://example/p{i}", pr_title="t") for i in range(n)
    ]


@given("a recording per-judge stub that scores differently for sonnet vs haiku")
def step_recording_per_judge(context) -> None:
    # Patch _judge_client_for so the returned object exposes the requested
    # model name as `_pinned_model` — the subsequent When-step reads that to
    # derive a judge-specific deterministic DR.
    def _fake_judge_for(model: str):
        class _C:
            _pinned_model = model

        return _C()

    context.fixtures["_patcher"] = patch("peer.eval.cross_judge._judge_client_for", _fake_judge_for)
    context.fixtures["_patcher"].start()


@when('I call CrossJudgeRunner.run with judge_models ["sonnet","haiku","opus"]')
def step_run_three_judges(context) -> None:
    # Use empty metrics list so we don't actually invoke the judge
    runner = CrossJudgeRunner(
        reviewer=context.fixtures["reviewer"],
        dataset=context.fixtures["dataset"],
        judge_models=["sonnet", "haiku", "opus"],
    )
    # Patch EvalRunner's metric default so we don't try to make LLM calls.
    with patch("peer.eval.cross_judge.EvalRunner") as MR:
        from peer.eval.types import AgentConfig as _AC
        from peer.eval.types import EvalReport as _ER
        from peer.eval.types import EvalSummary as _ES

        async def _fake_run_async():
            return _ER(
                agent_config=_AC(model="test", reviewer_class="TestReviewer"),
                dataset_path="in-memory",
                dataset_size=len(context.fixtures["dataset"]),
                summary=_ES(metric_values={"detection_rate": 0.05}),
                per_sample=[],
            )

        instance = MR.return_value
        instance.run_async = _fake_run_async
        context.fixtures["report"] = runner.run()


@then("the counting reviewer was invoked exactly {n:d} times")
def step_reviewer_count(context, n: int) -> None:
    got = context.fixtures["reviewer"].count
    assert got == n, f"expected {n}, got {got}"


@when('I call CrossJudgeRunner.run with judge_models ["sonnet","haiku"]')
def step_run_two_judges(context) -> None:
    runner = CrossJudgeRunner(
        reviewer=context.fixtures["reviewer"],
        dataset=context.fixtures["dataset"],
        judge_models=["sonnet", "haiku"],
    )
    call_order: list[str] = []

    with patch("peer.eval.cross_judge.EvalRunner") as MR:
        from peer.eval.types import AgentConfig as _AC
        from peer.eval.types import EvalReport as _ER
        from peer.eval.types import EvalSummary as _ES

        def _ctor(**kwargs):
            judge_client = kwargs.get("judge_client_override")
            judge_name = getattr(judge_client, "_pinned_model", "unknown")
            call_order.append(judge_name)

            class _Inst:
                async def run_async(self_inner):
                    # Use a deterministic DR based on the judge that was used.
                    dr = 0.10 if "sonnet" in judge_name else 0.04
                    return _ER(
                        agent_config=_AC(model="test", reviewer_class="TestReviewer"),
                        dataset_path="in-memory",
                        dataset_size=len(context.fixtures["dataset"]),
                        summary=_ES(metric_values={"detection_rate": dr}),
                        per_sample=[],
                    )

            return _Inst()

        MR.side_effect = _ctor
        context.fixtures["report"] = runner.run()
    context.fixtures["call_order"] = call_order
    if "_patcher" in context.fixtures:
        context.fixtures["_patcher"].stop()


@then("the report's per_judge has length {n:d}")
def step_per_judge_len(context, n: int) -> None:
    got = len(context.fixtures["report"].per_judge)
    assert got == n, f"expected {n}, got {got}"


@then('the per_judge["sonnet"] detection_rate differs from per_judge["haiku"] detection_rate')
def step_per_judge_differ(context) -> None:
    rep: CrossJudgeReport = context.fixtures["report"]
    s = rep.per_judge["sonnet"].summary.metric_values["detection_rate"]
    h = rep.per_judge["haiku"].summary.metric_values["detection_rate"]
    assert s != h, f"expected different DRs, both got {s}"


# ---------------------------------------------------------------------------
# compute_variance_bands scenarios
# ---------------------------------------------------------------------------


@when("I call compute_variance_bands on per-judge detection_rate values [{v1:f}, {v2:f}, {v3:f}]")
def step_compute_three(context, v1: float, v2: float, v3: float) -> None:
    reports = [_report_with_value("detection_rate", v) for v in [v1, v2, v3]]
    bands = compute_variance_bands(reports)
    context.fixtures["band"] = bands["detection_rate"]


@when("I call compute_variance_bands on per-judge detection_rate values [{v1:f}, None, {v3:f}]")
def step_compute_with_none(context, v1: float, v3: float) -> None:
    reports = [
        _report_with_value("detection_rate", v1),
        _report_with_value("detection_rate", None),
        _report_with_value("detection_rate", v3),
    ]
    bands = compute_variance_bands(reports)
    context.fixtures["band"] = bands["detection_rate"]


@then("the band's min equals {v:f}")
def step_band_min(context, v: float) -> None:
    got = context.fixtures["band"].min
    assert abs(got - v) < 1e-9, f"expected {v}, got {got}"


@then("the band's max equals {v:f}")
def step_band_max(context, v: float) -> None:
    got = context.fixtures["band"].max
    assert abs(got - v) < 1e-9, f"expected {v}, got {got}"


@then("the band's median equals {v:f}")
def step_band_median(context, v: float) -> None:
    got = context.fixtures["band"].median
    assert abs(got - v) < 1e-9, f"expected {v}, got {got}"


@then("the band's range equals approximately {v:f}")
def step_band_range(context, v: float) -> None:
    got = context.fixtures["band"].range
    assert abs(got - v) < 1e-6, f"expected {v}, got {got}"


@then("the band's n_judges_included equals {n:d}")
def step_band_n(context, n: int) -> None:
    got = context.fixtures["band"].n_judges_included
    assert got == n, f"expected {n}, got {got}"


# ---------------------------------------------------------------------------
# render_cross_judge_summary
# ---------------------------------------------------------------------------


def _report_with_band(dr_min: float, dr_max: float) -> CrossJudgeReport:
    median = (dr_min + dr_max) / 2
    return CrossJudgeReport(
        judge_models=["a", "b"],
        per_judge={},
        metric_bands={
            "detection_rate": MetricBand(
                min=dr_min, max=dr_max, median=median, range=dr_max - dr_min, n_judges_included=2
            )
        },
    )


@given("a CrossJudgeReport with detection_rate band min {lo:f} and max {hi:f}")
def step_cj_with_band(context, lo: float, hi: float) -> None:
    context.fixtures["cj_report"] = _report_with_band(lo, hi)


@when("I call render_cross_judge_summary")
def step_render_cj(context) -> None:
    context.fixtures["rendered"] = render_cross_judge_summary(context.fixtures["cj_report"])


# Note: `the rendered output contains/does NOT contain "..."` are provided by
# features/steps/patch_suggestions_followups_steps.py — reused via context.fixtures["rendered"].


# ---------------------------------------------------------------------------
# CLI conflict
# ---------------------------------------------------------------------------


@then("parsing raises SystemExit")
def step_parsing_raises(context) -> None:
    # The previous `When I parse "..."` step (provided by eval_v02_followups)
    # uses parser.parse_args which would raise SystemExit on argparse failure.
    # In this case the conflict is enforced inside the handler, not by argparse.
    # Verify by calling the handler directly with the parsed args.
    from peer.cli import _cmd_eval

    args = context.fixtures["args"]
    rc = _cmd_eval(args)
    assert rc == 2, f"expected rc=2 from conflict, got {rc}"
