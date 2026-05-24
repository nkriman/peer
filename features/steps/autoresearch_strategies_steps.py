"""Step definitions for features/autoresearch_strategies.feature (peer-oaq)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

from behave import given, then, when  # type: ignore[import-untyped]

from peer import Agent, Comment, Recipe, TestReviewer
from peer.strategies import (
    DraftCritiqueReviewer,
    SelfFilterReviewer,
    TwoModelPipelineReviewer,
    UnknownStrategy,
    resolve_strategy,
)
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


def _comment(path: str = "src/foo.py", line: int = 10, body: str = "b") -> Comment:
    return Comment(
        path=path,
        line=line,
        severity="minor",
        body=body,
        rationale="r",
    )


@dataclass
class _ScriptedReviewer:
    """Returns scripted (comments, usage) tuples, recording invocations."""

    scripted: list[tuple[list[Comment], dict]] = field(default_factory=list)
    call_count: int = 0
    name: str = "scripted"
    model: str = "test:scripted"

    def review(
        self,
        context: Context,
        codebase_context: CodebaseContext | None = None,
        *,
        extra_user_message: str | None = None,
        run_context: object | None = None,
    ) -> tuple[list[Comment], dict]:
        idx = self.call_count
        self.call_count += 1
        if idx >= len(self.scripted):
            return self.scripted[-1] if self.scripted else ([], {})
        return self.scripted[idx]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@when('I call resolve_strategy with "{name}"')
def step_resolve(context, name: str) -> None:
    try:
        context.fixtures["resolved"] = resolve_strategy(name)
        context.fixtures["resolve_error"] = None
    except Exception as e:
        context.fixtures["resolved"] = None
        context.fixtures["resolve_error"] = e


@then("the returned class is {name}")
def step_returned_class(context, name: str) -> None:
    from peer.strategies import AgenticReviewer

    expected = {
        "AgenticReviewer": AgenticReviewer,
        "DraftCritiqueReviewer": DraftCritiqueReviewer,
        "TwoModelPipelineReviewer": TwoModelPipelineReviewer,
        "SelfFilterReviewer": SelfFilterReviewer,
    }[name]
    got = context.fixtures["resolved"]
    assert got is expected, f"expected {expected}, got {got}"


@then("UnknownStrategy is raised")
def step_unknown_raised(context) -> None:
    err = context.fixtures["resolve_error"]
    assert isinstance(err, UnknownStrategy), f"expected UnknownStrategy, got {type(err)!r}"


# ---------------------------------------------------------------------------
# DraftCritiqueReviewer
# ---------------------------------------------------------------------------


@given(
    "an inner TestReviewer returning {n:d} fixed Comments and a critique returning DROP for the first"
)
def step_inner_critique_drops_first(context, n: int) -> None:
    inner_comments = [_comment(line=10 + i, body=f"b{i}") for i in range(n)]
    inner = _ScriptedReviewer(
        scripted=[(inner_comments, {"input_tokens": 50, "output_tokens": 20, "model": "x"})]
    )
    # Critique returns all comments except the first
    critique = _ScriptedReviewer(
        scripted=[(inner_comments[1:], {"input_tokens": 30, "output_tokens": 10, "model": "y"})]
    )
    context.fixtures["dc"] = DraftCritiqueReviewer(inner=inner, critique=critique)


@given("an inner TestReviewer returning {n:d} fixed Comments and a critique returning KEEP for all")
def step_inner_critique_keeps_all(context, n: int) -> None:
    inner_comments = [_comment(line=10 + i, body=f"b{i}") for i in range(n)]
    inner = _ScriptedReviewer(
        scripted=[(inner_comments, {"input_tokens": 50, "output_tokens": 20, "model": "x"})]
    )
    critique = _ScriptedReviewer(
        scripted=[(inner_comments, {"input_tokens": 30, "output_tokens": 10, "model": "y"})]
    )
    context.fixtures["dc"] = DraftCritiqueReviewer(inner=inner, critique=critique)


@given(
    "an inner TestReviewer returning 1 Comment with usage {{input_tokens {it_in:d}, output_tokens {it_out:d}}} "
    "and a critique with usage {{input_tokens {cr_in:d}, output_tokens {cr_out:d}}}"
)
def step_inner_critique_usage(context, it_in, it_out, cr_in, cr_out) -> None:
    one = [_comment()]
    inner = _ScriptedReviewer(
        scripted=[(one, {"input_tokens": it_in, "output_tokens": it_out, "model": "x"})]
    )
    critique = _ScriptedReviewer(
        scripted=[(one, {"input_tokens": cr_in, "output_tokens": cr_out, "model": "y"})]
    )
    context.fixtures["dc"] = DraftCritiqueReviewer(inner=inner, critique=critique)


@when("I invoke DraftCritiqueReviewer.review")
def step_invoke_dc(context) -> None:
    dc: DraftCritiqueReviewer = context.fixtures["dc"]
    comments, usage = dc.review(_ctx())
    context.fixtures["comments"] = comments
    context.fixtures["usage"] = usage


# Note: `the returned comments list has length N` is provided by
# features/steps/peer_deps_steps.py — reused here.


@then("the returned usage's input_tokens equals {n:d}")
def step_usage_in(context, n: int) -> None:
    got = context.fixtures["usage"]["input_tokens"]
    assert got == n, f"expected {n}, got {got}"


@then("the returned usage's output_tokens equals {n:d}")
def step_usage_out(context, n: int) -> None:
    got = context.fixtures["usage"]["output_tokens"]
    assert got == n, f"expected {n}, got {got}"


# ---------------------------------------------------------------------------
# TwoModelPipelineReviewer
# ---------------------------------------------------------------------------


@given(
    "a screen TestReviewer returning {n:d} Comments and a detail TestReviewer that should not be called"
)
def step_screen_zero(context, n: int) -> None:
    screen_comments = [_comment(line=10 + i) for i in range(n)]
    screen = _ScriptedReviewer(
        scripted=[(screen_comments, {"input_tokens": 10, "output_tokens": 5, "model": "x"})]
    )
    detail = _ScriptedReviewer(
        scripted=[([], {"input_tokens": 0, "output_tokens": 0, "model": "y"})]
    )
    context.fixtures["screen"] = screen
    context.fixtures["detail"] = detail
    context.fixtures["pipe"] = TwoModelPipelineReviewer(screen=screen, detail=detail)


@given("a screen TestReviewer returning {n:d} Comments and a recording detail TestReviewer")
def step_screen_n(context, n: int) -> None:
    # Two screen comments, one per file (so detail runs twice).
    screen_comments = [_comment(path=f"src/file{i}.py") for i in range(n)]
    screen = _ScriptedReviewer(
        scripted=[(screen_comments, {"input_tokens": 10, "output_tokens": 5, "model": "x"})]
    )
    detail = _ScriptedReviewer(
        scripted=[
            (
                [_comment(path="src/anything.py")],
                {"input_tokens": 30, "output_tokens": 10, "model": "y"},
            )
        ]
    )
    # Make ctx hold the paths the screen will reference
    context.fixtures["screen"] = screen
    context.fixtures["detail"] = detail
    context.fixtures["pipe"] = TwoModelPipelineReviewer(screen=screen, detail=detail)
    # Override ctx so it has matching hunks
    ctx = Context(
        pr_url="x",
        owner="o",
        repo="r",
        number=1,
        title="t",
        body="",
        head_sha="s",
        hunks=[
            ContextHunk(
                path=f"src/file{i}.py",
                old_start=10,
                old_lines=1,
                new_start=10,
                new_lines=1,
                diff_text="@@ -10,1 +10,1 @@\n line",
            )
            for i in range(n)
        ],
        prior_comments=[],
        token_estimate=0,
    )
    context.fixtures["pipe_ctx"] = ctx


@when("I invoke TwoModelPipelineReviewer.review")
def step_invoke_pipe(context) -> None:
    pipe: TwoModelPipelineReviewer = context.fixtures["pipe"]
    ctx = context.fixtures.get("pipe_ctx") or _ctx()
    comments, usage = pipe.review(ctx)
    context.fixtures["comments"] = comments
    context.fixtures["usage"] = usage


@then("the detail reviewer was invoked {n:d} times")
def step_detail_calls(context, n: int) -> None:
    got = context.fixtures["detail"].call_count
    assert got == n, f"expected {n} detail calls, got {got}"


# ---------------------------------------------------------------------------
# SelfFilterReviewer
# ---------------------------------------------------------------------------


@given(
    "an inner TestReviewer returning {n:d} fixed Comments and a stub judge returning scores {s1:f} and {s2:f}"
)
def step_inner_with_judge(context, n: int, s1: float, s2: float) -> None:
    cmts = [_comment(line=10 + i, body=f"b{i}") for i in range(n)]
    inner = _ScriptedReviewer(
        scripted=[(cmts, {"input_tokens": 50, "output_tokens": 20, "model": "x"})]
    )
    scores = [s1, s2]
    score_idx = [0]

    def judge(_c, _ctx) -> float:
        out = scores[score_idx[0]]
        score_idx[0] += 1
        return out

    context.fixtures["inner"] = inner
    context.fixtures["judge"] = judge


@when("I invoke SelfFilterReviewer with min_confidence {thresh:f}")
def step_invoke_sf(context, thresh: float) -> None:
    sf = SelfFilterReviewer(
        inner=context.fixtures["inner"],
        inner_judge=context.fixtures["judge"],
        min_confidence=thresh,
    )
    comments, usage = sf.review(_ctx())
    context.fixtures["comments"] = comments
    context.fixtures["usage"] = usage


# ---------------------------------------------------------------------------
# Recipe wiring
# ---------------------------------------------------------------------------


@given(
    'a Recipe with reviewer_dotted_path "{name}" and reviewer_kwargs containing an inner TestReviewer'
)
def step_recipe_with_strategy(context, name: str) -> None:
    # Direct: use a real TestReviewer instance (recipe's resolver only
    # auto-instantiates string dotted-paths; raw objects pass through).
    inner = TestReviewer(comments=[_comment()])
    context.fixtures["recipe"] = Recipe(
        reviewer_dotted_path=name,
        reviewer_kwargs={"inner": inner},
    )


@when("I apply the recipe to a fresh Agent")
def step_apply(context) -> None:
    with patch("anthropic.Anthropic"):
        agent = Agent(model="anthropic:claude-sonnet-4-6")
        context.fixtures["recipe"].apply_to_agent(agent)
    context.fixtures["agent"] = agent


@then("the Agent's reviewer is a DraftCritiqueReviewer")
def step_agent_reviewer_is_dc(context) -> None:
    rv = context.fixtures["agent"].reviewer
    assert isinstance(rv, DraftCritiqueReviewer), (
        f"expected DraftCritiqueReviewer, got {type(rv)!r}"
    )


# Silence "Any unused" linter complaint
_ = Any
