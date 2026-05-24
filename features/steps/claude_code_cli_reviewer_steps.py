"""Step definitions for features/claude_code_cli_reviewer.feature (peer-nq7)."""

from __future__ import annotations

import json
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

from behave import given, then, when  # type: ignore[import-untyped]

from peer import Agent, ClaudeCodeCLIReviewer
from peer.types import Context, ContextHunk


def _ctx(path: str) -> Context:
    return Context(
        pr_url="https://example/test/pull/1",
        owner="o",
        repo="r",
        number=1,
        title="t",
        body="",
        head_sha="s",
        hunks=[
            ContextHunk(
                path=path,
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


def _envelope(result_text: str, total_cost_usd: float) -> dict:
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": result_text,
        "total_cost_usd": total_cost_usd,
        "duration_ms": 100,
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _patch_subprocess_with_envelope(envelope: dict, record_argv: list | None = None):
    """Returns a patch context manager that makes subprocess.run return the
    given envelope (as JSON in stdout)."""
    completed = MagicMock(spec=subprocess.CompletedProcess)
    completed.returncode = 0
    completed.stdout = json.dumps(envelope)
    completed.stderr = ""

    def _fake_run(argv, **_kwargs):
        if record_argv is not None:
            record_argv.extend(argv)
        return completed

    return patch("peer.reviewers.subprocess.run", side_effect=_fake_run)


# ---------------------------------------------------------------------------
# Given steps
# ---------------------------------------------------------------------------


def _one_comment_payload(path: str = "src/foo.py", line: int = 10) -> dict:
    return {
        "comments": [
            {
                "path": path,
                "line": line,
                "severity": "minor",
                "body": "b",
                "rationale": "r",
            }
        ]
    }


@given(
    "a fake claude binary returning a clean JSON envelope with one comment "
    'on "{path}" line {line:d} and cost {cost:f}'
)
def step_fake_clean(context, path: str, line: int, cost: float) -> None:
    text = json.dumps(_one_comment_payload(path, line))
    context.fixtures["claude_envelope"] = _envelope(text, cost)


@given("a fake claude binary returning the comments JSON wrapped in a fenced json block")
def step_fake_fenced(context) -> None:
    text = "Here you go:\n```json\n" + json.dumps(_one_comment_payload()) + "\n```\nDone."
    context.fixtures["claude_envelope"] = _envelope(text, 0.0)


@given("a fake claude binary returning the comments JSON preceded by some prose")
def step_fake_prose(context) -> None:
    text = "Here is the JSON: " + json.dumps(_one_comment_payload()) + " and that's all."
    context.fixtures["claude_envelope"] = _envelope(text, 0.0)


@given("a fake claude binary returning a result with no JSON at all")
def step_fake_no_json(context) -> None:
    context.fixtures["claude_envelope"] = _envelope("I could not find any issues.", 0.0)


@given("a fake claude binary that records its argv and returns empty comments")
def step_fake_records_argv(context) -> None:
    context.fixtures["claude_envelope"] = _envelope(json.dumps({"comments": []}), 0.0)
    context.fixtures["argv"] = []


# ---------------------------------------------------------------------------
# When steps
# ---------------------------------------------------------------------------


@when('I invoke the ClaudeCodeCLIReviewer on a synthetic Context with one hunk on "{path}"')
def step_invoke_cli_reviewer(context, path: str) -> None:
    rv = ClaudeCodeCLIReviewer(model="claude-code:sonnet", model_id="sonnet")
    argv_recorder = context.fixtures.get("argv")
    with _patch_subprocess_with_envelope(
        context.fixtures["claude_envelope"], record_argv=argv_recorder
    ):
        comments, usage = rv.review(_ctx(path))
    # Mirror into "comments" so the existing step (peer_deps_steps:238)
    # `the returned comments list has length N` can locate the list.
    context.fixtures["comments"] = comments
    context.fixtures["cli_comments"] = comments
    context.fixtures["cli_usage"] = usage


@when("the ClaudeCodeCLIReviewer attempts to call its CLI")
def step_attempt_cli_with_flag_off(context) -> None:
    rv = ClaudeCodeCLIReviewer(model="claude-code:sonnet", model_id="sonnet")
    try:
        rv.review(_ctx("src/foo.py"))
        context.error = None
    except Exception as e:
        context.error = e


# ---------------------------------------------------------------------------
# Then steps
# ---------------------------------------------------------------------------


# Note: `the returned comments list has length N` is provided by
# features/steps/peer_deps_steps.py — reused here.


@then('the first parsed comment\'s path equals "{path}"')
def step_first_path(context, path: str) -> None:
    got = context.fixtures["cli_comments"][0].path
    assert got == path, f"expected {path!r}, got {got!r}"


@then("the returned usage's total_cost_usd equals {val:f}")
def step_usage_cost_equals(context, val: float) -> None:
    got = context.fixtures["cli_usage"].get("total_cost_usd")
    assert got == val, f"usage[total_cost_usd] expected {val}, got {got!r}"


@then('the recorded argv contains "{needle}"')
def step_argv_contains(context, needle: str) -> None:
    argv = context.fixtures["argv"]
    assert needle in argv, f"{needle!r} not in argv={argv}"


@then("the Agent's reviewer is a ClaudeCodeCLIReviewer")
def step_agent_reviewer_is_cli(context) -> None:
    agent: Agent = context.fixtures["agent"]
    assert isinstance(agent.reviewer, ClaudeCodeCLIReviewer), (
        f"expected ClaudeCodeCLIReviewer, got {type(agent.reviewer)!r}"
    )


@then("the Agent's reviewer's model_id equals \"{val}\"")
def step_agent_reviewer_model_id(context, val: str) -> None:
    agent: Agent = context.fixtures["agent"]
    got = getattr(agent.reviewer, "model_id", None)
    assert got == val, f"expected {val!r}, got {got!r}"


# Sanity — silence unused import in some scenarios.
_ = Any
