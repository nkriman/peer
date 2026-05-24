"""Step definitions for features/eval_v02_followups.feature (peer-40y).

Covers case-specific evaluators on GoldSample, EvalRunner.run_async with
bounded concurrency, and the --with-rationale-grounding CLI flag.
"""

from __future__ import annotations

import asyncio
import shlex
import time
from dataclasses import dataclass, field
from unittest.mock import patch

from behave import given, then, when  # type: ignore[import-untyped]

from peer import Comment, GoldSample, Review, TestReviewer
from peer.cli import _make_parser
from peer.eval.runner import EvalRunner
from peer.eval.types import AggregateKind, MetricResult

# ---------------------------------------------------------------------------
# Helpers — a recording evaluator that counts invocations
# ---------------------------------------------------------------------------


@dataclass
class RecordingEvaluator:
    """Minimal Evaluator that records each .score() call."""

    name: str = "test_recorder"
    aggregate_kind: AggregateKind = AggregateKind.MEAN
    invocation_count: int = 0
    seen_pr_urls: list[str] = field(default_factory=list)

    def score(self, sample: GoldSample, review: Review, *, client=None) -> MetricResult:
        self.invocation_count += 1
        self.seen_pr_urls.append(sample.pr_url)
        return MetricResult(name=self.name, value=1.0)


# ---------------------------------------------------------------------------
# GoldSample.evaluators
# ---------------------------------------------------------------------------


@when("I construct a GoldSample with two case-specific evaluators")
def step_gs_two_evaluators(context) -> None:
    e1 = RecordingEvaluator(name="test_a")
    e2 = RecordingEvaluator(name="test_b")
    context.fixtures["gs"] = GoldSample(
        pr_url="https://github.com/test/test/pull/1",
        pr_title="t",
        evaluators=[e1, e2],
    )


@when("I construct a minimal GoldSample")
def step_gs_minimal(context) -> None:
    context.fixtures["gs"] = GoldSample(
        pr_url="https://github.com/test/test/pull/1",
        pr_title="t",
    )


@then("the GoldSample's evaluators list has length {n:d}")
def step_gs_eval_len(context, n: int) -> None:
    got = len(context.fixtures["gs"].evaluators)
    assert got == n, f"expected {n}, got {got}"


@then('the first case-specific evaluator\'s name equals "{name}"')
def step_first_eval_name(context, name: str) -> None:
    got = context.fixtures["gs"].evaluators[0].name
    assert got == name, f"expected {name!r}, got {got!r}"


@then('the second case-specific evaluator\'s name equals "{name}"')
def step_second_eval_name(context, name: str) -> None:
    got = context.fixtures["gs"].evaluators[1].name
    assert got == name, f"expected {name!r}, got {got!r}"


@then("the GoldSample's evaluators list is the empty list")
def step_gs_eval_empty(context) -> None:
    got = context.fixtures["gs"].evaluators
    assert got == [], f"expected [], got {got!r}"


# ---------------------------------------------------------------------------
# Case-specific evaluators run via EvalRunner
# ---------------------------------------------------------------------------


@given('a TestReviewer that returns one Comment on "{path}"')
def step_testreviewer_one(context, path: str) -> None:
    rv = TestReviewer(
        comments=[
            Comment(
                path=path,
                line=10,
                severity="minor",
                body="b",
                rationale="r",
            )
        ]
    )
    # The reviewer needs a .review(pr_url) method (sync), which TestReviewer
    # doesn't have natively — it has .review(context, codebase_context). Wrap
    # in an adapter that EvalRunner can call.

    class _PRReviewer:
        model = "test:stub"

        def review(self, _pr_url: str) -> Review:
            return Review(
                comments=list(rv.comments or []),
                usage={"input_tokens": 0, "output_tokens": 0, "model": "test:stub"},
            )

    context.fixtures["reviewer"] = _PRReviewer()


@given("a GoldSample with one case-specific recording evaluator")
def step_gs_with_case_eval(context) -> None:
    e = RecordingEvaluator(name="case_specific")
    context.fixtures["case_eval"] = e
    context.fixtures["gs_one"] = GoldSample(
        pr_url="https://github.com/test/test/pull/1",
        pr_title="t",
        evaluators=[e],
    )


@given(
    "an EvalRunner constructed with the TestReviewer + that GoldSample "
    "+ one dataset-wide recording evaluator"
)
def step_runner_with_recorders(context) -> None:
    ds_eval = RecordingEvaluator(name="dataset_wide")
    context.fixtures["ds_eval"] = ds_eval
    runner = EvalRunner(
        reviewer=context.fixtures["reviewer"],
        dataset=[context.fixtures["gs_one"]],
        metrics=[ds_eval],
    )
    context.fixtures["runner"] = runner


@when("I call EvalRunner.run")
def step_call_run(context) -> None:
    context.fixtures["report"] = context.fixtures["runner"].run()


@then("the dataset-wide recording evaluator was invoked exactly {n:d} times")
@then("the dataset-wide recording evaluator was invoked exactly {n:d} time")
def step_ds_invoked(context, n: int) -> None:
    got = context.fixtures["ds_eval"].invocation_count
    assert got == n, f"expected {n}, got {got}"


@then("the case-specific recording evaluator was invoked exactly {n:d} times")
@then("the case-specific recording evaluator was invoked exactly {n:d} time")
def step_case_invoked(context, n: int) -> None:
    got = context.fixtures["case_eval"].invocation_count
    assert got == n, f"expected {n}, got {got}"


# ---------------------------------------------------------------------------
# run_async
# ---------------------------------------------------------------------------


@given("an EvalRunner constructed with the TestReviewer + one GoldSample")
def step_runner_one_sample(context) -> None:
    gs = GoldSample(
        pr_url="https://github.com/test/test/pull/1",
        pr_title="t",
    )
    runner = EvalRunner(
        reviewer=context.fixtures["reviewer"],
        dataset=[gs],
        metrics=[],
    )
    context.fixtures["runner"] = runner


@when("I call EvalRunner.run_async with concurrency {n:d}")
def step_call_run_async(context, n: int) -> None:
    runner: EvalRunner = context.fixtures["runner"]
    t0 = time.perf_counter()
    context.fixtures["report"] = asyncio.run(runner.run_async(concurrency=n))
    context.fixtures["elapsed_s"] = time.perf_counter() - t0


@then("the returned EvalReport has {n:d} per_sample result")
@then("the returned EvalReport has {n:d} per_sample results")
def step_report_per_sample_len(context, n: int) -> None:
    got = len(context.fixtures["report"].per_sample)
    assert got == n, f"expected {n}, got {got}"


@then("the EvalReport's run_id is non-empty")
def step_report_run_id(context) -> None:
    rid = context.fixtures["report"].run_id
    assert rid and isinstance(rid, str), f"empty run_id: {rid!r}"


@given('a SlowTestReviewer that sleeps 50ms before returning one Comment on "{path}"')
def step_slow_reviewer(context, path: str) -> None:
    class _SlowReviewer:
        model = "test:slow"

        def review(self, _pr_url: str) -> Review:
            time.sleep(0.05)
            return Review(
                comments=[
                    Comment(
                        path=path,
                        line=10,
                        severity="minor",
                        body="b",
                        rationale="r",
                    )
                ],
                usage={"input_tokens": 0, "output_tokens": 0, "model": "test:slow"},
            )

    context.fixtures["reviewer"] = _SlowReviewer()


@given("an EvalRunner constructed with that SlowTestReviewer + {n:d} GoldSamples")
def step_runner_n_samples(context, n: int) -> None:
    samples = [
        GoldSample(pr_url=f"https://github.com/test/test/pull/{i}", pr_title="t")
        for i in range(1, n + 1)
    ]
    runner = EvalRunner(
        reviewer=context.fixtures["reviewer"],
        dataset=samples,
        metrics=[],
    )
    context.fixtures["runner"] = runner


@then("the wall-clock duration was below {threshold:f} seconds")
def step_wall_clock_under(context, threshold: float) -> None:
    elapsed = context.fixtures["elapsed_s"]
    assert elapsed < threshold, (
        f"expected wall-clock < {threshold}s, got {elapsed:.3f}s (parallelism didn't kick in?)"
    )


# ---------------------------------------------------------------------------
# CLI flag parsing
# ---------------------------------------------------------------------------


@when('I parse "{cmd}"')
def step_parse_cmd(context, cmd: str) -> None:
    parser = _make_parser()
    # Strip the leading "peer" program name to match argparse expectations.
    argv = shlex.split(cmd)
    assert argv and argv[0] == "peer", f"expected leading 'peer', got {argv!r}"
    # argparse will try to resolve the dataset Path; for tests we don't need
    # the file to exist — parsing should succeed regardless.
    with patch("pathlib.Path.exists", return_value=True):
        args = parser.parse_args(argv[1:])
    context.fixtures["args"] = args


@then("the parsed args has with_rationale_grounding equal to True")
def step_args_rg_true(context) -> None:
    args = context.fixtures["args"]
    assert args.with_rationale_grounding is True, (
        f"expected True, got {args.with_rationale_grounding!r}"
    )


@then("the parsed args has with_rationale_grounding equal to False")
def step_args_rg_false(context) -> None:
    args = context.fixtures["args"]
    assert args.with_rationale_grounding is False, (
        f"expected False, got {args.with_rationale_grounding!r}"
    )


@then("the parsed args has concurrency equal to {n:d}")
def step_args_concurrency(context, n: int) -> None:
    args = context.fixtures["args"]
    assert args.concurrency == n, f"expected {n}, got {args.concurrency!r}"
