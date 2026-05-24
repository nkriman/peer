"""Step definitions for features/claude_code_everywhere.feature (peer-0jy)."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any
from unittest.mock import patch

from behave import given, then, when  # type: ignore[import-untyped]

from peer import Agent, ClaudeCodeCLIReviewer, ClaudeReviewer, Recipe
from peer.claude_code_client import (
    ClaudeCodeShimClient,
    ClaudeCodeShimResponse,
    make_client,
)
from peer.eval.runner import EvalRunner
from peer.reviewers import _COMMENT_TOOL


def _envelope(
    result_text: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read: int = 0,
    cache_creation: int = 0,
) -> dict:
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": result_text,
        "total_cost_usd": 0.0,
        "duration_ms": 100,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_creation,
        },
    }


def _stub_runner(envelope: dict, argv_sink: list | None = None):
    """Return a callable that subprocess.run can be swapped with."""

    def _run(argv, **_kwargs):
        if argv_sink is not None:
            argv_sink.extend(argv)
        completed = subprocess.CompletedProcess(
            args=argv, returncode=0, stdout=json.dumps(envelope), stderr=""
        )
        return completed

    return _run


# ---------------------------------------------------------------------------
# Shim: text + tool_use
# ---------------------------------------------------------------------------


@given(
    'a fake claude binary returning result text "{text}" with input_tokens {it:d} and output_tokens {ot:d}'
)
def step_fake_text(context, text: str, it: int, ot: int) -> None:
    context.fixtures["envelope"] = _envelope(text, input_tokens=it, output_tokens=ot)


@given(
    "a fake claude binary returning a fenced JSON with one comment for the post_review_comments tool"
)
def step_fake_fenced(context) -> None:
    payload = {
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
    text = "Here:\n```json\n" + json.dumps(payload) + "\n```\nDone."
    context.fixtures["envelope"] = _envelope(text, input_tokens=10, output_tokens=20)


@given("a fake claude binary that records its argv")
def step_fake_argv(context) -> None:
    context.fixtures["envelope"] = _envelope("ok", input_tokens=1, output_tokens=1)
    context.fixtures["argv"] = []


@given(
    "a fake claude binary returning input_tokens {it:d} cache_read {cr:d} cache_creation {cc:d} and output_tokens {ot:d}"
)
def step_fake_usage(context, it: int, cr: int, cc: int, ot: int) -> None:
    context.fixtures["envelope"] = _envelope(
        "x", input_tokens=it, output_tokens=ot, cache_read=cr, cache_creation=cc
    )


@when("I call ClaudeCodeShimClient.messages.create with no tools")
def step_call_no_tools(context) -> None:
    runner = _stub_runner(context.fixtures["envelope"], context.fixtures.get("argv"))
    client = ClaudeCodeShimClient(_runner=runner)
    context.fixtures["resp"] = client.messages.create(
        model="sonnet", messages=[{"role": "user", "content": "hi"}], max_tokens=50
    )


@when("I call ClaudeCodeShimClient.messages.create with the _COMMENT_TOOL and tool_choice")
def step_call_with_tools(context) -> None:
    runner = _stub_runner(context.fixtures["envelope"], context.fixtures.get("argv"))
    client = ClaudeCodeShimClient(_runner=runner)
    context.fixtures["resp"] = client.messages.create(
        model="sonnet",
        messages=[{"role": "user", "content": "review this"}],
        max_tokens=8192,
        tools=[_COMMENT_TOOL],
        tool_choice={"type": "tool", "name": "post_review_comments"},
    )


@when('I call ClaudeCodeShimClient.messages.create with system "{system}" and model "{model}"')
def step_call_with_system(context, system: str, model: str) -> None:
    runner = _stub_runner(context.fixtures["envelope"], context.fixtures.get("argv"))
    client = ClaudeCodeShimClient(_runner=runner)
    context.fixtures["resp"] = client.messages.create(
        model=model,
        system=system,
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=10,
    )


@then('the response\'s first content block type equals "{val}"')
def step_first_type(context, val: str) -> None:
    got = context.fixtures["resp"].content[0].type
    assert got == val, f"expected {val!r}, got {got!r}"


@then('the response\'s first content block text equals "{val}"')
def step_first_text(context, val: str) -> None:
    got = context.fixtures["resp"].content[0].text
    assert got == val, f"expected {val!r}, got {got!r}"


@then("the response's usage input_tokens equals {n:d}")
def step_usage_in(context, n: int) -> None:
    got = context.fixtures["resp"].usage.input_tokens
    assert got == n, f"expected {n}, got {got}"


@then("the response's usage output_tokens equals {n:d}")
def step_usage_out(context, n: int) -> None:
    got = context.fixtures["resp"].usage.output_tokens
    assert got == n, f"expected {n}, got {got}"


@then("the response has at least one tool_use content block")
def step_has_tool_use(context) -> None:
    resp: ClaudeCodeShimResponse = context.fixtures["resp"]
    assert any(b.type == "tool_use" for b in resp.content), f"no tool_use block in {resp.content}"


@then('the tool_use block\'s name equals "{name}"')
def step_tool_use_name(context, name: str) -> None:
    resp: ClaudeCodeShimResponse = context.fixtures["resp"]
    blk = next(b for b in resp.content if b.type == "tool_use")
    assert blk.name == name, f"expected name={name!r}, got {blk.name!r}"


@then("the tool_use block's input has comments list of length {n:d}")
def step_tool_use_len(context, n: int) -> None:
    resp: ClaudeCodeShimResponse = context.fixtures["resp"]
    blk = next(b for b in resp.content if b.type == "tool_use")
    assert blk.input is not None
    got = len(blk.input.get("comments", []))
    assert got == n, f"expected {n} comments, got {got}"


@then('the first comment\'s path equals "{path}"')
def step_first_comment_path(context, path: str) -> None:
    resp: ClaudeCodeShimResponse = context.fixtures["resp"]
    blk = next(b for b in resp.content if b.type == "tool_use")
    assert blk.input is not None
    got = blk.input["comments"][0]["path"]
    assert got == path, f"expected {path!r}, got {got!r}"


# Note: `the recorded argv contains "..."` is provided by
# features/steps/claude_code_cli_reviewer_steps.py (peer-nq7) — reused here
# via the same context.fixtures["argv"] key.


# ---------------------------------------------------------------------------
# make_client
# ---------------------------------------------------------------------------


@given('PEER_USE_CLAUDE_CODE is set to "{val}"')
def step_env_set(context, val: str) -> None:
    context.fixtures["_prev_env"] = os.environ.get("PEER_USE_CLAUDE_CODE")
    os.environ["PEER_USE_CLAUDE_CODE"] = val


@given("PEER_USE_CLAUDE_CODE is unset")
def step_env_unset(context) -> None:
    context.fixtures["_prev_env"] = os.environ.get("PEER_USE_CLAUDE_CODE")
    os.environ.pop("PEER_USE_CLAUDE_CODE", None)


@when("I call make_client with no override")
def step_make_no_override(context) -> None:
    try:
        context.fixtures["client"] = make_client()
    finally:
        # Restore env to avoid leaking across scenarios
        prev = context.fixtures.get("_prev_env")
        if prev is None:
            os.environ.pop("PEER_USE_CLAUDE_CODE", None)
        else:
            os.environ["PEER_USE_CLAUDE_CODE"] = prev


@when("I call make_client with use_claude_code False")
def step_make_explicit_false(context) -> None:
    try:
        context.fixtures["client"] = make_client(use_claude_code=False)
    finally:
        prev = context.fixtures.get("_prev_env")
        if prev is None:
            os.environ.pop("PEER_USE_CLAUDE_CODE", None)
        else:
            os.environ["PEER_USE_CLAUDE_CODE"] = prev


@then("the returned client is a ClaudeCodeShimClient")
def step_is_shim(context) -> None:
    got = context.fixtures["client"]
    assert isinstance(got, ClaudeCodeShimClient), f"got {type(got)!r}"


@then("the returned client is NOT a ClaudeCodeShimClient")
def step_is_not_shim(context) -> None:
    got = context.fixtures["client"]
    assert not isinstance(got, ClaudeCodeShimClient), f"got {type(got)!r}"


# ---------------------------------------------------------------------------
# ClaudeReviewer + EvalRunner integration
# ---------------------------------------------------------------------------


@when("I construct a ClaudeReviewer")
def step_construct_reviewer(context) -> None:
    try:
        with patch("anthropic.Anthropic"):
            context.fixtures["reviewer"] = ClaudeReviewer(model="anthropic:claude-sonnet-4-6")
    finally:
        prev = context.fixtures.get("_prev_env")
        if prev is None:
            os.environ.pop("PEER_USE_CLAUDE_CODE", None)
        else:
            os.environ["PEER_USE_CLAUDE_CODE"] = prev


@then("the reviewer's client is a ClaudeCodeShimClient")
def step_reviewer_client_is_shim(context) -> None:
    rv = context.fixtures["reviewer"]
    assert isinstance(rv.client, ClaudeCodeShimClient), f"got {type(rv.client)!r}"


@when("I call EvalRunner._get_client")
def step_call_get_client(context) -> None:
    try:
        from peer import TestReviewer

        runner = EvalRunner(reviewer=TestReviewer(), dataset=[])
        context.fixtures["client"] = runner._get_client()
    finally:
        prev = context.fixtures.get("_prev_env")
        if prev is None:
            os.environ.pop("PEER_USE_CLAUDE_CODE", None)
        else:
            os.environ["PEER_USE_CLAUDE_CODE"] = prev


# ---------------------------------------------------------------------------
# Recipe.use_claude_code
# ---------------------------------------------------------------------------


@given("a Recipe with use_claude_code True")
def step_recipe_use_cc(context) -> None:
    # Snapshot env so the after_scenario hook can restore (mirrors the
    # ALLOW_LLM_CALLS pattern). We use the existing "I apply the recipe
    # to a fresh Agent" step defined in autoresearch_strategies_steps.
    context.fixtures["_prev_env_apply"] = os.environ.get("PEER_USE_CLAUDE_CODE")
    context.fixtures["recipe"] = Recipe(use_claude_code=True)


# Note: `I apply the recipe to a fresh Agent` is provided by
# features/steps/autoresearch_strategies_steps.py — reused here.


# Note: `the Agent's reviewer is a ClaudeCodeCLIReviewer` is provided by
# features/steps/claude_code_cli_reviewer_steps.py — reused here.


@then('PEER_USE_CLAUDE_CODE equals "{val}"')
def step_env_equals(context, val: str) -> None:
    try:
        got = os.environ.get("PEER_USE_CLAUDE_CODE")
        assert got == val, f"expected {val!r}, got {got!r}"
    finally:
        # Restore after assert so cleanup runs regardless of pass/fail.
        prev = context.fixtures.get("_prev_env_apply")
        if prev is None:
            os.environ.pop("PEER_USE_CLAUDE_CODE", None)
        else:
            os.environ["PEER_USE_CLAUDE_CODE"] = prev


_ = Any
