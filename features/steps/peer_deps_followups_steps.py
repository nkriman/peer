"""Step definitions for features/peer_deps_followups.feature (peer-0um).

Covers validation retries, capture_run_messages (incl. async safety),
and ReviewerRateLimited + 429 backoff.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import anthropic
from behave import given, then, when  # type: ignore[import-untyped]

from peer import (
    Agent,
    CapturedMessage,
    ClaudeReviewer,
    Comment,
    PeerDeps,
    ReviewerRateLimited,
    TestReviewer,
    capture_run_messages,
)
from peer.types import CodebaseContext, Context, ContextHunk

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(paths: list[str]) -> Context:
    hunks = [
        ContextHunk(
            path=p,
            old_start=10,
            old_lines=2,
            new_start=10,
            new_lines=2,
            diff_text="@@ -10,2 +10,2 @@\n line\n line",
        )
        for p in paths
    ]
    return Context(
        pr_url="https://example/test/pull/1",
        owner="test",
        repo="test",
        number=1,
        title="t",
        body="",
        head_sha="sha",
        hunks=hunks,
        prior_comments=[],
        token_estimate=0,
    )


@dataclass
class ScriptedReviewer:
    """Reviewer that returns a programmed list-of-comments per invocation.

    `scripted_returns` is a list of (comments_to_return, usage_dict) tuples;
    each call pops the next one. Records the `ctx.attempt` it was passed in
    `seen_attempts` for verification.
    """

    name: str = "scripted"
    model: str = "test:scripted"
    scripted_returns: list[tuple[list[Comment], dict]] = field(default_factory=list)
    invocation_count: int = 0
    seen_attempts: list[int] = field(default_factory=list)

    def review(
        self,
        context: Context,
        codebase_context: CodebaseContext | None = None,
        *,
        extra_user_message: str | None = None,
        run_context: object | None = None,
    ) -> tuple[list[Comment], dict]:
        idx = self.invocation_count
        self.invocation_count += 1
        if run_context is not None:
            self.seen_attempts.append(getattr(run_context, "attempt", -1))
        if idx >= len(self.scripted_returns):
            # Past-end → reuse last entry (lets "always returns" scenarios work).
            return self.scripted_returns[-1]
        return self.scripted_returns[idx]


# ---------------------------------------------------------------------------
# Validation retries
# ---------------------------------------------------------------------------


@given("an Agent with retries set to one")
def step_agent_retries_one(context) -> None:
    context.fixtures["agent"] = Agent(model="anthropic:claude-sonnet-4-6", retries={"output": 1})


@given("an Agent with retries set to zero")
def step_agent_retries_zero(context) -> None:
    context.fixtures["agent"] = Agent(model="anthropic:claude-sonnet-4-6", retries={"output": 0})


def _bad_comment() -> Comment:
    return Comment(
        path="src/does-not-exist.py",
        line=999,
        severity="minor",
        body="bad",
        rationale="bad",
    )


def _good_comment() -> Comment:
    return Comment(
        path="src/foo.py",
        line=10,
        severity="minor",
        body="ok",
        rationale="ok",
    )


@given(
    "a scripted Reviewer that returns a bad-path Comment on attempt 0 and a valid Comment on attempt 1"
)
def step_scripted_retry_success(context) -> None:
    usage = {"input_tokens": 0, "output_tokens": 0, "model": "test:scripted"}
    sr = ScriptedReviewer(
        scripted_returns=[
            ([_bad_comment()], dict(usage)),
            ([_good_comment()], dict(usage)),
        ]
    )
    context.fixtures["scripted_reviewer"] = sr


@given("a scripted Reviewer that always returns a bad-path Comment")
def step_scripted_always_bad(context) -> None:
    usage = {"input_tokens": 0, "output_tokens": 0, "model": "test:scripted"}
    sr = ScriptedReviewer(scripted_returns=[([_bad_comment()], dict(usage))])
    context.fixtures["scripted_reviewer"] = sr


@given("a scripted Reviewer that records each ctx.attempt it was passed")
def step_scripted_records_attempts(context) -> None:
    # Set up so the first attempt's comments all drop (forces a retry) and
    # the second attempt's comment is valid (terminates the loop).
    usage = {"input_tokens": 0, "output_tokens": 0, "model": "test:scripted"}
    sr = ScriptedReviewer(
        scripted_returns=[
            ([_bad_comment()], dict(usage)),
            ([_good_comment()], dict(usage)),
        ]
    )
    context.fixtures["scripted_reviewer"] = sr


@when('I call Agent.run on a synthetic PR with one hunk on "{path}"')
def step_run_synthetic_one_hunk(context, path: str) -> None:
    agent = context.fixtures["agent"]
    sr = context.fixtures["scripted_reviewer"]
    synth_ctx = _make_context([path])

    def _fake_gather(_url: str) -> Context:
        synth_ctx.pr_url = _url
        return synth_ctx

    with (
        patch("peer.agent.gather", _fake_gather),
        patch("peer.agent.gather_codebase_context", side_effect=RuntimeError("skip")),
        agent.override(reviewer=sr),
    ):
        context.fixtures["review"] = agent.run(
            "https://github.com/test/test/pull/1", deps=PeerDeps()
        )


# Note: `the returned Review has N comments` is provided by
# features/steps/agent_integration_steps.py — reused here.


@then("the Review's usage records n_retries_used equal to {n:d}")
def step_review_n_retries(context, n: int) -> None:
    usage = context.fixtures["review"].usage or {}
    got = usage.get("n_retries_used")
    assert got == n, f"expected n_retries_used={n}, got {got!r} in usage={usage!r}"


@then("the scripted Reviewer was invoked exactly {n:d} times")
@then("the scripted Reviewer was invoked exactly {n:d} time")
def step_scripted_invoked_n(context, n: int) -> None:
    got = context.fixtures["scripted_reviewer"].invocation_count
    assert got == n, f"expected {n} invocations, got {got}"


@then('the scripted Reviewer recorded attempts "{csv}"')
def step_scripted_attempts(context, csv: str) -> None:
    expected = [int(s) for s in csv.split(",")]
    got = context.fixtures["scripted_reviewer"].seen_attempts
    assert got == expected, f"expected attempts {expected}, got {got}"


# ---------------------------------------------------------------------------
# capture_run_messages
# ---------------------------------------------------------------------------


@given('an Agent with a TestReviewer that returns one fixed Comment on "{path}"')
def step_agent_with_testreviewer(context, path: str) -> None:
    agent = Agent(model="anthropic:claude-sonnet-4-6")
    fixed = [
        Comment(
            path=path,
            line=10,
            severity="minor",
            body="t",
            rationale="t",
        )
    ]
    context.fixtures["agent"] = agent
    context.fixtures["pending_override"] = TestReviewer(comments=fixed)
    context.fixtures["fixed_test_reviewer"] = TestReviewer(comments=fixed)


@when(
    'I call Agent.run inside a capture_run_messages block on a synthetic PR with one hunk on "{path}"'
)
def step_run_inside_capture(context, path: str) -> None:
    agent = context.fixtures["agent"]
    rv = context.fixtures["pending_override"]
    synth_ctx = _make_context([path])

    def _fake_gather(_url: str) -> Context:
        synth_ctx.pr_url = _url
        return synth_ctx

    with (
        capture_run_messages() as buf,
        patch("peer.agent.gather", _fake_gather),
        patch("peer.agent.gather_codebase_context", side_effect=RuntimeError("skip")),
        agent.override(reviewer=rv),
    ):
        agent.run("https://github.com/test/test/pull/1", deps=PeerDeps())
    context.fixtures["captured"] = buf


@then("the captured messages list has length {n:d}")
def step_captured_len(context, n: int) -> None:
    got = len(context.fixtures["captured"])
    assert got == n, f"expected {n}, got {got}"


@then("the first captured message's system_prompt is non-empty")
def step_captured_system_nonempty(context) -> None:
    cm: CapturedMessage = context.fixtures["captured"][0]
    assert cm.system_prompt and isinstance(cm.system_prompt, str)


@then('the first captured message\'s user_prompt contains "{needle}"')
def step_captured_user_contains(context, needle: str) -> None:
    cm: CapturedMessage = context.fixtures["captured"][0]
    assert needle in cm.user_prompt, f"{needle!r} not in user_prompt={cm.user_prompt[:200]!r}"


@then("the first captured message's raw_response is a dict")
def step_captured_raw_is_dict(context) -> None:
    cm: CapturedMessage = context.fixtures["captured"][0]
    assert isinstance(cm.raw_response, dict)


@then('the first captured message\'s usage has model "{model}"')
def step_captured_usage_model(context, model: str) -> None:
    cm: CapturedMessage = context.fixtures["captured"][0]
    got = cm.usage.get("model")
    assert got == model, f"expected model={model!r}, got {got!r}"


@given("two independent capture_run_messages buffers in two separate asyncio tasks")
def step_two_tasks(context) -> None:
    # The actual concurrency is realized inside the When-step; this step just
    # signals intent + creates the per-PR fixtures.
    context.fixtures["pr_urls"] = [
        "https://github.com/test/a/pull/1",
        "https://github.com/test/b/pull/2",
    ]


@when("each task calls Agent.run once with a distinct PR url")
def step_each_task_runs(context) -> None:
    pr_urls = context.fixtures["pr_urls"]

    fixed = [
        Comment(
            path="src/foo.py",
            line=10,
            severity="minor",
            body="t",
            rationale="t",
        )
    ]

    def _fake_gather(url: str) -> Context:
        c = _make_context(["src/foo.py"])
        c.pr_url = url
        return c

    async def _one_run(pr_url: str) -> tuple[str, list[CapturedMessage]]:
        agent = Agent(model="anthropic:claude-sonnet-4-6")
        with capture_run_messages() as buf:
            with (
                patch("peer.agent.gather", _fake_gather),
                patch("peer.agent.gather_codebase_context", side_effect=RuntimeError("skip")),
                agent.override(reviewer=TestReviewer(comments=fixed)),
            ):
                # Yield so both tasks interleave inside their respective
                # capture blocks — the real test of contextvar isolation.
                await asyncio.sleep(0)
                agent.run(pr_url, deps=PeerDeps())
                await asyncio.sleep(0)
            return pr_url, list(buf)

    async def _gather_all() -> list[tuple[str, list[CapturedMessage]]]:
        return await asyncio.gather(*(_one_run(u) for u in pr_urls))

    results = asyncio.run(_gather_all())
    context.fixtures["per_task_results"] = results


@then("each buffer contains exactly 1 captured message")
def step_each_buffer_one(context) -> None:
    for url, buf in context.fixtures["per_task_results"]:
        assert len(buf) == 1, f"buffer for {url} has length {len(buf)}, expected 1"


@then("each buffer's captured PR url matches the task that opened it")
def step_each_buffer_matches(context) -> None:
    for url, buf in context.fixtures["per_task_results"]:
        cm = buf[0]
        assert cm.pr_url == url, f"buffer pr_url={cm.pr_url!r} != task url={url!r}"


@when('I call Agent.run on a synthetic PR with one hunk on "{path}" with no active capture block')
def step_run_no_capture(context, path: str) -> None:
    # Clear any prior-scenario "captured" leakage (fixtures persist within a
    # feature; see features/environment.py).
    context.fixtures.pop("captured", None)
    agent = context.fixtures["agent"]
    rv = context.fixtures["pending_override"]
    synth_ctx = _make_context([path])

    def _fake_gather(_url: str) -> Context:
        synth_ctx.pr_url = _url
        return synth_ctx

    # Directly assert the contextvar exposes None at the run-time call.
    from peer.runtime import _capture_buffer

    sentinel: list[bool] = []

    def _observe_no_buffer(*_a, **_kw) -> tuple[list, dict]:
        sentinel.append(_capture_buffer.get() is None)
        return [], {"input_tokens": 0, "output_tokens": 0, "model": "test"}

    rv.review = _observe_no_buffer  # type: ignore[method-assign]

    with (
        patch("peer.agent.gather", _fake_gather),
        patch("peer.agent.gather_codebase_context", side_effect=RuntimeError("skip")),
        agent.override(reviewer=rv),
    ):
        agent.run("https://github.com/test/test/pull/1", deps=PeerDeps())
    context.fixtures["no_capture_sentinel"] = sentinel


@then("no captured-messages list is populated")
def step_no_captured(context) -> None:
    sentinel = context.fixtures["no_capture_sentinel"]
    assert sentinel and all(sentinel), (
        f"capture buffer was unexpectedly active outside capture_run_messages() — sentinel={sentinel}"
    )


# ---------------------------------------------------------------------------
# ReviewerRateLimited / 429 backoff
# ---------------------------------------------------------------------------


class _FakeAnthropic429(Exception):
    """Looks like a 429 to _is_rate_limit_error (carries status_code=429)."""

    status_code = 429


def _make_reviewer(max_retries: int) -> tuple[ClaudeReviewer, list[float]]:
    sleeps: list[float] = []

    def _record(s: float) -> None:
        sleeps.append(s)

    # Construct without touching anthropic.Anthropic() — patch its client
    # attribute after the fact.
    with patch("anthropic.Anthropic"):
        rv = ClaudeReviewer(
            model="anthropic:claude-sonnet-4-6",
            rate_limit_max_retries=max_retries,
            rate_limit_base_backoff=1.0,
            _sleep=_record,
        )
    return rv, sleeps


@given("a ClaudeReviewer whose underlying client always raises a 429")
def step_reviewer_always_429(context) -> None:
    rv, sleeps = _make_reviewer(max_retries=2)
    rv.client.messages.create.side_effect = _FakeAnthropic429("rate limited")  # type: ignore[attr-defined]
    context.fixtures["reviewer"] = rv
    context.fixtures["sleeps"] = sleeps


@given("a ClaudeReviewer whose underlying client raises a 429 on call 0 and succeeds on call 1")
def step_reviewer_429_then_ok(context) -> None:
    rv, sleeps = _make_reviewer(max_retries=3)

    class _OkResp:
        content: list = []  # noqa: RUF012  # test stub, mutation not a concern

        class usage:
            input_tokens = 0
            output_tokens = 0

    rv.client.messages.create.side_effect = [_FakeAnthropic429("once"), _OkResp()]  # type: ignore[attr-defined]
    context.fixtures["reviewer"] = rv
    context.fixtures["sleeps"] = sleeps


@given("the Reviewer's rate_limit_max_retries is set to {n:d}")
def step_set_max_retries(context, n: int) -> None:
    # Already configured in the make_reviewer step — this exists so the
    # scenario reads naturally. We assert what was actually set.
    rv: ClaudeReviewer = context.fixtures["reviewer"]
    assert rv.rate_limit_max_retries == n, (
        f"expected rate_limit_max_retries={n}, got {rv.rate_limit_max_retries}"
    )


@when("the Reviewer is invoked")
def step_invoke_reviewer(context) -> None:
    rv: ClaudeReviewer = context.fixtures["reviewer"]
    ctx = _make_context(["src/foo.py"])
    try:
        rv.review(ctx, None)
        context.fixtures["error"] = None
    except Exception as e:
        context.fixtures["error"] = e


@then("ReviewerRateLimited is raised")
def step_rrl_raised(context) -> None:
    err = context.fixtures["error"]
    assert isinstance(err, ReviewerRateLimited), f"expected ReviewerRateLimited, got {type(err)!r}"


# Note: `no exception is raised` is provided by features/steps/peer_deps_steps.py.


@then("the underlying client was called exactly {n:d} times")
@then("the underlying client was called exactly {n:d} time")
def step_client_calls(context, n: int) -> None:
    rv: ClaudeReviewer = context.fixtures["reviewer"]
    got = rv.client.messages.create.call_count  # type: ignore[attr-defined]
    assert got == n, f"expected {n} client calls, got {got}"


@then("the cumulative sleep time was approximately {n:d} ticks of base backoff")
def step_cumulative_sleeps(context, n: int) -> None:
    sleeps = context.fixtures["sleeps"]
    total = sum(sleeps)
    # Backoff schedule: 1.0 * 2^0 + 1.0 * 2^1 = 3.0 for max_retries=2.
    assert abs(total - float(n)) < 1e-6, (
        f"expected ~{n} base ticks of sleep, got {total} (sleeps={sleeps})"
    )


# Sanity: keep anthropic import live so the linter doesn't drop it (used by
# the FakeAnthropic429 + mocked Anthropic client constructor).
_ = anthropic
_ = Any
