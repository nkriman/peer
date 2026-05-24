"""Step definitions for features/eval_v02.feature."""

from __future__ import annotations

from behave import given, then, when  # type: ignore[import-untyped]

from peer.eval import (
    AggregateKind,
    EvalRunner,
    LLMJudge,
    MetricResult,
    RationaleGrounding,
    judge_match,
)

# ---------------------------------------------------------------------------
# MetricResult.value flexible types
# ---------------------------------------------------------------------------


@when("I construct a MetricResult with value True")
def step_metricresult_bool(context) -> None:
    context.fixtures["mr"] = MetricResult(name="x", value=True)


@when('I construct a MetricResult with value {"a": 0.5, "b": "good"}')
def step_metricresult_dict(context) -> None:
    context.fixtures["mr"] = MetricResult(name="x", value={"a": 0.5, "b": "good"})


@then("the MetricResult's value is the bool True")
def step_mr_value_bool_true(context) -> None:
    v = context.fixtures["mr"].value
    assert v is True, f"expected True (bool), got {v!r}"


@then('the MetricResult\'s value is the dict {"a": 0.5, "b": "good"}')
def step_mr_value_dict(context) -> None:
    assert context.fixtures["mr"].value == {"a": 0.5, "b": "good"}


# ---------------------------------------------------------------------------
# AggregateKind enum
# ---------------------------------------------------------------------------


@when("I import AggregateKind")
def step_import_aggregate_kind(context) -> None:
    context.fixtures["AggKind"] = AggregateKind


@then("AggregateKind has members MEAN SUM_OF_SUMS PASS_RATE PER_TIER LATENCY_PERCENTILE")
def step_aggregate_kind_members(context) -> None:
    AK = context.fixtures["AggKind"]
    for member in ("MEAN", "SUM_OF_SUMS", "PASS_RATE", "PER_TIER", "LATENCY_PERCENTILE"):
        assert hasattr(AK, member), f"AggregateKind missing member {member}"


# ---------------------------------------------------------------------------
# Custom metric with aggregate_kind
# ---------------------------------------------------------------------------


@given('a custom metric class with name "{name}" and aggregate_kind PASS_RATE')
def step_custom_metric_with_kind(context, name: str) -> None:
    class CustomMetric:
        pass

    CustomMetric.name = name
    CustomMetric.aggregate_kind = AggregateKind.PASS_RATE
    context.fixtures["metric"] = CustomMetric()


@then("the metric's aggregate_kind equals AggregateKind.PASS_RATE")
def step_metric_aggregate_kind(context) -> None:
    got = context.fixtures["metric"].aggregate_kind
    assert got is AggregateKind.PASS_RATE, f"expected PASS_RATE, got {got!r}"


# ---------------------------------------------------------------------------
# LLMJudge
# ---------------------------------------------------------------------------


@when('I construct an LLMJudge with rubric "{r}"')
def step_construct_llm_judge(context, r: str) -> None:
    context.fixtures["judge"] = LLMJudge(rubric=r)


@then('the LLMJudge\'s rubric equals "{r}"')
def step_judge_rubric(context, r: str) -> None:
    assert context.fixtures["judge"].rubric == r


@then("the LLMJudge's include_input is False")
def step_judge_include_input_false(context) -> None:
    assert context.fixtures["judge"].include_input is False


@then("the LLMJudge's include_expected_output is True")
def step_judge_include_expected_true(context) -> None:
    assert context.fixtures["judge"].include_expected_output is True


@then("the LLMJudge's include_reason is True")
def step_judge_include_reason_true(context) -> None:
    assert context.fixtures["judge"].include_reason is True


# ---------------------------------------------------------------------------
# judge_match back-compat
# ---------------------------------------------------------------------------


@when("I import judge_match from peer.eval")
def step_import_judge_match(context) -> None:
    context.fixtures["judge_match"] = judge_match


@then("judge_match is callable")
def step_judge_match_callable(context) -> None:
    assert callable(context.fixtures["judge_match"])


# ---------------------------------------------------------------------------
# RationaleGrounding not in defaults
# ---------------------------------------------------------------------------


class _StubReviewer:
    model = "stub:test"

    def review(self, pr_url):
        from peer.types import Review

        return Review(
            comments=[], usage={"input_tokens": 0, "output_tokens": 0, "model": self.model}
        )


@when("I construct an EvalRunner with default metrics")
def step_construct_runner_default(context) -> None:
    runner = EvalRunner(reviewer=_StubReviewer(), dataset=[])
    context.fixtures["runner"] = runner


@then("the default metrics list does NOT contain RationaleGrounding")
def step_default_no_rationale_grounding(context) -> None:
    metrics = context.fixtures["runner"].metrics
    types_present = {type(m).__name__ for m in metrics}
    assert "RationaleGrounding" not in types_present, (
        f"RationaleGrounding leaked into defaults; metrics={types_present}"
    )
    # And verify the class exists as an opt-in
    assert RationaleGrounding is not None
