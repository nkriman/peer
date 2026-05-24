"""Step definitions for features/agentic_reviewer.feature (peer-4vn)."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

from behave import given, then, when  # type: ignore[import-untyped]

from peer import Agent, Recipe
from peer.strategies import AgenticReviewer
from peer.types import Comment, Context, ContextHunk


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
                new_lines=5,
                diff_text="@@ -10,2 +10,5 @@\n line\n line\n line\n line\n line",
            )
        ],
        prior_comments=[],
        token_estimate=0,
    )


def _envelope(structured_output: dict | None = None, result_text: str = "") -> dict:
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": result_text,
        "structured_output": structured_output,
        "total_cost_usd": 0.0,
        "duration_ms": 100,
        "usage": {"input_tokens": 100, "output_tokens": 50},
        "num_turns": 3,
    }


def _patch_subprocess(envelope: dict, argv_sink: list | None = None):
    def _fake_run(argv, **_kwargs):
        if argv_sink is not None:
            argv_sink.extend(argv)
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout=json.dumps(envelope), stderr=""
        )

    return patch("peer.strategies.agentic.subprocess.run", side_effect=_fake_run)


# Reuse from claude_code_cli_reviewer_steps.py:
#   `a fake claude binary that records its argv and returns empty comments`
#   `a fake claude binary returning the comments JSON wrapped in a fenced json block`
# Both set context.fixtures["claude_envelope"] + context.fixtures.get("argv").
# We re-use them via:

_DEFAULT_ENVELOPE_COMMENT = {
    "comments": [
        {
            "path": "src/foo.py",
            "line": 10,
            "severity": "minor",
            "body": "b",
            "rationale": "r",
        }
    ]
}


@given('a fake claude binary returning structured_output with one comment on "{path}"')
def step_fake_structured(context, path: str) -> None:
    payload = {
        "comments": [
            {
                "path": path,
                "line": 10,
                "severity": "minor",
                "body": "b",
                "rationale": "r",
            }
        ]
    }
    context.fixtures["agentic_envelope"] = _envelope(structured_output=payload)


@when('I invoke AgenticReviewer with allowed_tools "{tools}" and max_turns {n:d}')
def step_invoke_agentic_argv(context, tools: str, n: int) -> None:
    tool_list = [t.strip() for t in tools.split(",") if t.strip()]
    envelope = context.fixtures.get("claude_envelope") or _envelope(
        structured_output={"comments": []}
    )
    argv_sink = context.fixtures.get("argv") or []
    context.fixtures["argv"] = argv_sink
    rv = AgenticReviewer(allowed_tools=tool_list, max_turns=n)
    with _patch_subprocess(envelope, argv_sink=argv_sink):
        comments, usage = rv.review(_ctx())
    context.fixtures["agentic_comments"] = comments
    context.fixtures["agentic_usage"] = usage


@when("I invoke AgenticReviewer with default tools")
def step_invoke_agentic_default(context) -> None:
    # Prefer agentic_envelope (set by structured_output step) over the
    # generic claude_envelope (set by the fenced-JSON step).
    envelope = (
        context.fixtures.get("agentic_envelope")
        or context.fixtures.get("claude_envelope")
        or _envelope(structured_output={"comments": []})
    )
    rv = AgenticReviewer()
    with _patch_subprocess(envelope):
        comments, usage = rv.review(_ctx())
    context.fixtures["agentic_comments"] = comments
    context.fixtures["agentic_usage"] = usage


@when("the AgenticReviewer attempts to call its CLI")
def step_agentic_call_blocked(context) -> None:
    rv = AgenticReviewer()
    try:
        rv.review(_ctx())
        context.error = None
    except Exception as e:
        context.error = e


@then("the returned agentic comments list has length {n:d}")
def step_agentic_len(context, n: int) -> None:
    got = len(context.fixtures["agentic_comments"])
    assert got == n, f"expected {n}, got {got}: {context.fixtures['agentic_comments']}"


@then('the first agentic comment\'s path equals "{path}"')
def step_agentic_first_path(context, path: str) -> None:
    got: list[Comment] = context.fixtures["agentic_comments"]
    assert got[0].path == path, f"expected {path!r}, got {got[0].path!r}"


@then('the recorded argv does NOT contain "{needle}"')
def step_argv_not_contains(context, needle: str) -> None:
    argv = context.fixtures["argv"]
    # Substring check across the whole argv list (any element containing the needle).
    contains = any(needle in (a or "") for a in argv)
    assert not contains, f"{needle!r} unexpectedly found in argv: {argv}"


# Registry + Recipe wiring
# `When I call resolve_strategy with "..."` provided by autoresearch_strategies_steps.py.
# `Then the returned class is ...` provided by same.


@given('a Recipe with reviewer_dotted_path "agentic" and reviewer_kwargs max_turns {n:d}')
def step_recipe_with_agentic(context, n: int) -> None:
    context.fixtures["recipe"] = Recipe(
        reviewer_dotted_path="agentic",
        reviewer_kwargs={"max_turns": n},
    )


# `When I apply the recipe to a fresh Agent` provided by
# autoresearch_strategies_steps.py.


@then("the Agent's reviewer is an AgenticReviewer")
def step_agent_reviewer_is_agentic(context) -> None:
    agent: Agent = context.fixtures["agent"]
    assert isinstance(agent.reviewer, AgenticReviewer), (
        f"expected AgenticReviewer, got {type(agent.reviewer)!r}"
    )


@then("the Agent's reviewer's max_turns equals {n:d}")
def step_agent_reviewer_max_turns(context, n: int) -> None:
    agent: Agent = context.fixtures["agent"]
    got = getattr(agent.reviewer, "max_turns", None)
    assert got == n, f"expected {n}, got {got!r}"
