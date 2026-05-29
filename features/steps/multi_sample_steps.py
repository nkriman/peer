"""Step definitions for features/multi_sample.feature (multi-sample-v01)."""

from __future__ import annotations

from dataclasses import dataclass, field

from behave import given, then, when  # type: ignore[import-untyped]

from peer import Comment
from peer.strategies import MultiSampleReviewer, resolve_strategy
from peer.types import CodebaseContext, Context, ContextHunk


def _ctx() -> Context:
    return Context(
        pr_url="x",
        owner="o",
        repo="r",
        number=1,
        title="t",
        body="",
        head_sha="s",
        hunks=[
            ContextHunk(
                path="src/foo.py",
                old_start=10,
                old_lines=2,
                new_start=10,
                new_lines=3,
                diff_text="@@ -10,2 +10,3 @@\n line\n line\n line",
            )
        ],
        prior_comments=[],
        token_estimate=0,
    )


def _comment(path: str = "a.py", line: int = 10, body: str = "bug") -> Comment:
    return Comment(path=path, line=line, severity="minor", body=body, rationale="r")


@dataclass
class _CountingReviewer:
    """Returns scripted comments + usage; increments count each invocation.

    Attribute name `count` (not `call_count`) matches the existing
    cross-judge BDD step `the counting reviewer was invoked exactly N times`
    so we can reuse it.
    """

    scripted: list[tuple[list[Comment], dict]] = field(default_factory=list)
    count: int = 0
    name: str = "counting"
    model: str = "test:counting"

    def review(
        self,
        context: Context,
        codebase_context: CodebaseContext | None = None,
        *,
        extra_user_message: str | None = None,
        run_context: object | None = None,
    ) -> tuple[list[Comment], dict]:
        idx = self.count
        self.count += 1
        if not self.scripted:
            return ([], {})
        if idx >= len(self.scripted):
            return self.scripted[-1]
        return self.scripted[idx]


# ---------------------------------------------------------------------------
# Givens
# ---------------------------------------------------------------------------


@given("a MultiSampleReviewer with a counting inner reviewer and k={k:d}")
def step_with_counting_inner(context, k: int) -> None:
    inner = _CountingReviewer(
        scripted=[([_comment()], {"input_tokens": 1, "output_tokens": 1, "model": "x"})]
    )
    context.fixtures["reviewer"] = inner
    context.fixtures["ms"] = MultiSampleReviewer(inner=inner, k=k)


@given("a MultiSampleReviewer with an inner returning the same comment every time and k={k:d}")
def step_with_same_comment_inner(context, k: int) -> None:
    same = _comment(path="a.py", line=10, body="bug")
    inner = _CountingReviewer(
        scripted=[([same], {"input_tokens": 1, "output_tokens": 1, "model": "x"})]
    )
    context.fixtures["reviewer"] = inner
    context.fixtures["ms"] = MultiSampleReviewer(inner=inner, k=k)


@given(
    "a MultiSampleReviewer with an inner returning 3 distinct comments across 3 calls and k={k:d}"
)
def step_with_distinct_comments_inner(context, k: int) -> None:
    inner = _CountingReviewer(
        scripted=[
            (
                [_comment(path="a.py", line=10, body="X")],
                {"input_tokens": 1, "output_tokens": 1, "model": "x"},
            ),
            (
                [_comment(path="a.py", line=11, body="X")],
                {"input_tokens": 1, "output_tokens": 1, "model": "x"},
            ),
            (
                [_comment(path="a.py", line=10, body="Y")],
                {"input_tokens": 1, "output_tokens": 1, "model": "x"},
            ),
        ]
    )
    context.fixtures["reviewer"] = inner
    context.fixtures["ms"] = MultiSampleReviewer(inner=inner, k=k)


@given("a MultiSampleReviewer with an inner returning usage {it:d}/{ot:d}/{cost:f} and k={k:d}")
def step_with_usage_inner(context, it: int, ot: int, cost: float, k: int) -> None:
    inner = _CountingReviewer(
        scripted=[
            (
                [_comment()],
                {"input_tokens": it, "output_tokens": ot, "total_cost_usd": cost, "model": "x"},
            )
        ]
    )
    context.fixtures["reviewer"] = inner
    context.fixtures["ms"] = MultiSampleReviewer(inner=inner, k=k)


# ---------------------------------------------------------------------------
# Whens
# ---------------------------------------------------------------------------


@when("I invoke MultiSampleReviewer.review")
def step_invoke_ms(context) -> None:
    ms: MultiSampleReviewer = context.fixtures["ms"]
    comments, usage = ms.review(_ctx())
    context.fixtures["ms_comments"] = comments
    context.fixtures["ms_usage"] = usage


@when("I attempt to construct a MultiSampleReviewer with k={k:d}")
def step_attempt_construct_ms(context, k: int) -> None:
    try:
        MultiSampleReviewer(inner=_CountingReviewer(), k=k)
        context.fixtures["error"] = None
    except Exception as e:
        context.fixtures["error"] = e


# ---------------------------------------------------------------------------
# Thens
# ---------------------------------------------------------------------------


# Note: `the counting reviewer was invoked exactly N times` is provided by
# features/steps/eval_cross_judge_steps.py — we reuse it by storing our inner
# under context.fixtures["reviewer"] with a `count` attribute.


@then("the returned multi-sample comments list has length {n:d}")
def step_ms_comments_len(context, n: int) -> None:
    got = len(context.fixtures["ms_comments"])
    assert got == n, f"expected {n} comments, got {got}"


@then("the returned multi-sample usage input_tokens is {n:d}")
def step_ms_usage_in(context, n: int) -> None:
    got = context.fixtures["ms_usage"]["input_tokens"]
    assert got == n, f"expected {n}, got {got}"


@then("the returned multi-sample usage output_tokens is {n:d}")
def step_ms_usage_out(context, n: int) -> None:
    got = context.fixtures["ms_usage"]["output_tokens"]
    assert got == n, f"expected {n}, got {got}"


@then("the returned multi-sample usage total_cost_usd is {c:f}")
def step_ms_usage_cost(context, c: float) -> None:
    got = context.fixtures["ms_usage"]["total_cost_usd"]
    assert abs(got - c) < 1e-6, f"expected {c}, got {got}"
