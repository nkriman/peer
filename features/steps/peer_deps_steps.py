"""Step definitions for features/peer_deps.feature.

Covers peer-deps-v01 user-facing behaviors. All scenarios run offline
(zero LLM calls) — we never actually invoke Anthropic; the ClaudeReviewer
is constructed but never exercised, and TestReviewer covers the
synthetic-output path.
"""

from __future__ import annotations

import warnings
from unittest.mock import patch

from behave import given, then, when  # type: ignore[import-untyped]

import peer.deps as _deps_module
from peer import Agent, PeerDeps, TestReviewer
from peer.exceptions import LLMCallsDisabled, UnknownModelError
from peer.reviewers import ClaudeReviewer
from peer.types import Comment, Context, ContextHunk


def _make_context(n_hunks: int = 1) -> Context:
    """Build a minimal Context with N hunks for TestReviewer to work on."""
    hunks = [
        ContextHunk(
            path=f"src/file{i}.py",
            old_start=10 * (i + 1),
            old_lines=2,
            new_start=10 * (i + 1),
            new_lines=2,
            diff_text=f"@@ -{10 * (i + 1)},2 +{10 * (i + 1)},2 @@\n line a\n line b",
        )
        for i in range(n_hunks)
    ]
    return Context(
        pr_url="https://example/test/pull/1",
        owner="test",
        repo="test",
        number=1,
        title="Test PR",
        body="",
        head_sha="abc123",
        hunks=hunks,
        prior_comments=[],
        token_estimate=0,
    )


# ---------------------------------------------------------------------------
# PeerDeps construction
# ---------------------------------------------------------------------------


@when("I construct a PeerDeps with no arguments")
def step_peerdeps_default(context) -> None:
    context.fixtures["peer_deps"] = PeerDeps()


@when('I construct a PeerDeps with extra_instructions "{instr}"')
def step_peerdeps_with_extra(context, instr: str) -> None:
    context.fixtures["peer_deps"] = PeerDeps(extra_instructions=instr)


@then("the PeerDeps has config equal to None")
def step_peerdeps_config_none(context) -> None:
    assert context.fixtures["peer_deps"].config is None


@then("the PeerDeps has classifier equal to None")
def step_peerdeps_classifier_none(context) -> None:
    assert context.fixtures["peer_deps"].classifier is None


@then("the PeerDeps has linters equal to the empty list")
def step_peerdeps_linters_empty(context) -> None:
    assert context.fixtures["peer_deps"].linters == []


@then("the PeerDeps has extra_instructions equal to None")
def step_peerdeps_extra_none(context) -> None:
    assert context.fixtures["peer_deps"].extra_instructions is None


@then('the PeerDeps\'s extra_instructions equals "{val}"')
def step_peerdeps_extra_equals(context, val: str) -> None:
    assert context.fixtures["peer_deps"].extra_instructions == val


# ---------------------------------------------------------------------------
# RunContext
# ---------------------------------------------------------------------------


@given('a PeerDeps instance with extra_instructions "{val}"')
def step_given_peerdeps(context, val: str) -> None:
    context.fixtures["peer_deps"] = PeerDeps(extra_instructions=val)


@when('I construct a RunContext with that PeerDeps and pr_url "{url}"')
def step_construct_runcontext(context, url: str) -> None:
    from peer.runtime import RunContext

    context.fixtures["run_ctx"] = RunContext[PeerDeps](
        deps=context.fixtures["peer_deps"], pr_url=url
    )


@then('the RunContext\'s deps.extra_instructions equals "{val}"')
def step_runcontext_deps_extra(context, val: str) -> None:
    assert context.fixtures["run_ctx"].deps.extra_instructions == val


@then("the RunContext's attempt equals 0")
def step_runcontext_attempt_zero(context) -> None:
    assert context.fixtures["run_ctx"].attempt == 0


@then('the RunContext does NOT have a "metadata" field')
def step_runcontext_no_metadata(context) -> None:
    ctx = context.fixtures["run_ctx"]
    # Pydantic v2: model_fields excludes private/forbidden fields
    assert "metadata" not in ctx.model_fields, (
        f"RunContext should not have a 'metadata' field; found {list(ctx.model_fields)}"
    )


# ---------------------------------------------------------------------------
# ALLOW_LLM_CALLS gate
# ---------------------------------------------------------------------------


@given("peer.deps.ALLOW_LLM_CALLS is set to False")
def step_allow_false(context) -> None:
    context.fixtures["_prev_allow"] = _deps_module.ALLOW_LLM_CALLS
    _deps_module.ALLOW_LLM_CALLS = False


@when("the real ClaudeReviewer attempts to call its LLM")
def step_real_claude_call(context) -> None:
    rv = ClaudeReviewer(model="anthropic:claude-sonnet-4-6")
    try:
        rv.review(_make_context())
        context.error = None
    except Exception as e:
        context.error = e
    finally:
        _deps_module.ALLOW_LLM_CALLS = context.fixtures.get("_prev_allow", True)


@when("the TestReviewer is invoked")
def step_test_reviewer_invoked(context) -> None:
    rv = TestReviewer(n_comments=1, severity="minor")
    try:
        rv.review(_make_context())
        context.error = None
    except Exception as e:
        context.error = e
    finally:
        _deps_module.ALLOW_LLM_CALLS = context.fixtures.get("_prev_allow", True)


@then("LLMCallsDisabled is raised")
def step_llm_disabled_raised(context) -> None:
    assert isinstance(context.error, LLMCallsDisabled), (
        f"expected LLMCallsDisabled, got {type(context.error).__name__}: {context.error!r}"
    )


@then('the error message references "Agent.override(reviewer=TestReviewer())"')
def step_error_message_references(context) -> None:
    msg = str(context.error)
    assert "Agent.override(reviewer=TestReviewer())" in msg, (
        f"missing override-fix hint in: {msg!r}"
    )


@then("no exception is raised")
def step_no_exception(context) -> None:
    assert context.error is None, f"expected no exception, got: {context.error!r}"


# ---------------------------------------------------------------------------
# TestReviewer modes
# ---------------------------------------------------------------------------


@given("a TestReviewer constructed with one fixed Comment")
def step_test_reviewer_fixed(context) -> None:
    fixed = [
        Comment(
            path="src/foo.py",
            line=42,
            severity="critical",
            body="fixed test comment",
            rationale="fixed test rationale",
        )
    ]
    context.fixtures["reviewer"] = TestReviewer(comments=fixed)
    context.fixtures["fixed_comments"] = fixed


@given('a TestReviewer constructed with n_comments {n:d} and severity "{sev}"')
def step_test_reviewer_synth(context, n: int, sev: str) -> None:
    context.fixtures["reviewer"] = TestReviewer(n_comments=n, severity=sev)


@when("I call review on a Context with a single hunk")
def step_call_review_single_hunk(context) -> None:
    ctx = _make_context(n_hunks=1)
    comments, usage = context.fixtures["reviewer"].review(ctx)
    context.fixtures["comments"] = comments
    context.fixtures["usage"] = usage


@when("I call review on a Context with three hunks")
def step_call_review_three_hunks(context) -> None:
    ctx = _make_context(n_hunks=3)
    comments, usage = context.fixtures["reviewer"].review(ctx)
    context.fixtures["comments"] = comments
    context.fixtures["usage"] = usage


@then("the returned comments list equals the fixed list")
def step_comments_equal_fixed(context) -> None:
    got = context.fixtures["comments"]
    expected = context.fixtures["fixed_comments"]
    assert len(got) == len(expected), f"length mismatch: {len(got)} vs {len(expected)}"
    for g, e in zip(got, expected, strict=False):
        assert g.model_dump() == e.model_dump(), f"mismatch: {g} vs {e}"


@then('the returned usage has model "{model}"')
def step_usage_model_equals(context, model: str) -> None:
    assert context.fixtures["usage"].get("model") == model


@then("the returned comments list has length {n:d}")
def step_comments_length(context, n: int) -> None:
    got = context.fixtures["comments"]
    assert len(got) == n, f"expected {n} comments, got {len(got)}: {got}"


@then('each returned comment has severity "{sev}"')
def step_each_comment_severity(context, sev: str) -> None:
    for c in context.fixtures["comments"]:
        assert c.severity == sev, f"expected {sev}, got {c.severity} on {c}"


# ---------------------------------------------------------------------------
# Provider:model parsing
# ---------------------------------------------------------------------------


@when('I construct an Agent with model "{model}"')
def step_construct_agent_with_model(context, model: str) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        context.fixtures["agent"] = Agent(model=model)
        context.fixtures["warnings"] = list(caught)
        context.error = None


@when('I attempt to construct an Agent with model "{model}"')
def step_attempt_construct_agent(context, model: str) -> None:
    try:
        context.fixtures["agent"] = Agent(model=model)
        context.error = None
    except Exception as e:
        context.error = e


@then('the Agent\'s model attribute equals "{val}"')
def step_agent_model_equals(context, val: str) -> None:
    assert context.fixtures["agent"].model == val, (
        f"expected {val!r}, got {context.fixtures['agent'].model!r}"
    )


@then("no DeprecationWarning is emitted")
def step_no_deprecation(context) -> None:
    dep = [
        w
        for w in context.fixtures.get("warnings", [])
        if issubclass(w.category, DeprecationWarning)
    ]
    assert not dep, f"unexpected deprecation warnings: {[str(w.message) for w in dep]}"


@then('a DeprecationWarning is emitted referencing "{ref}"')
def step_deprecation_emitted_referencing(context, ref: str) -> None:
    dep = [
        w
        for w in context.fixtures.get("warnings", [])
        if issubclass(w.category, DeprecationWarning) and ref in str(w.message)
    ]
    assert dep, (
        f"expected DeprecationWarning referencing {ref!r}; "
        f"got {[str(w.message) for w in context.fixtures.get('warnings', [])]}"
    )


@then("UnknownModelError is raised")
def step_unknown_model_raised(context) -> None:
    assert isinstance(context.error, UnknownModelError), (
        f"expected UnknownModelError, got {type(context.error).__name__}: {context.error!r}"
    )


# ---------------------------------------------------------------------------
# Agent.override
# ---------------------------------------------------------------------------


@given('an Agent constructed with model "{model}"')
def step_given_agent_with_model(context, model: str) -> None:
    context.fixtures["agent"] = Agent(model=model)
    context.fixtures["original_reviewer"] = context.fixtures["agent"].reviewer


@when("I enter Agent.override with a TestReviewer and exit cleanly")
def step_override_simple(context) -> None:
    agent = context.fixtures["agent"]
    test_rv = TestReviewer()
    with agent.override(reviewer=test_rv):
        context.fixtures["during_block_reviewer"] = agent.reviewer
    context.fixtures["after_block_reviewer"] = agent.reviewer


@when("I enter Agent.override with a TestReviewer and raise RuntimeError inside")
def step_override_with_exception(context) -> None:
    agent = context.fixtures["agent"]
    test_rv = TestReviewer()
    try:
        with agent.override(reviewer=test_rv):
            raise RuntimeError("expected")
    except RuntimeError as e:
        context.error = e
    context.fixtures["after_block_reviewer"] = agent.reviewer


@when("I nest two Agent.override blocks with two distinct TestReviewers")
def step_nested_override(context) -> None:
    agent = context.fixtures["agent"]
    outer = TestReviewer(n_comments=1, severity="minor")
    inner = TestReviewer(n_comments=2, severity="nit")
    with agent.override(reviewer=outer):
        context.fixtures["during_outer_reviewer"] = agent.reviewer
        with agent.override(reviewer=inner):
            context.fixtures["during_inner_reviewer"] = agent.reviewer
        context.fixtures["after_inner_reviewer"] = agent.reviewer
    context.fixtures["after_outer_reviewer"] = agent.reviewer
    context.fixtures["outer_test_reviewer"] = outer
    context.fixtures["inner_test_reviewer"] = inner


@then("during the block the Agent's reviewer is a TestReviewer")
def step_during_block_is_test(context) -> None:
    rv = context.fixtures["during_block_reviewer"]
    assert isinstance(rv, TestReviewer), f"expected TestReviewer, got {type(rv).__name__}"


@then("after the block the Agent's reviewer is the original ClaudeReviewer")
def step_after_block_original_claude(context) -> None:
    rv = context.fixtures["after_block_reviewer"]
    original = context.fixtures["original_reviewer"]
    assert rv is original, f"expected restored {type(original).__name__}, got {type(rv).__name__}"


@then("the RuntimeError propagates out of the block")
def step_runtime_propagates(context) -> None:
    assert isinstance(context.error, RuntimeError), (
        f"expected RuntimeError to propagate; got {type(context.error).__name__}: {context.error!r}"
    )


@then("the Agent's reviewer after the block is the original ClaudeReviewer")
def step_after_block_original_claude_after_exc(context) -> None:
    rv = context.fixtures["after_block_reviewer"]
    original = context.fixtures["original_reviewer"]
    assert rv is original, f"expected restored {type(original).__name__}, got {type(rv).__name__}"


@then("during the inner block the Agent's reviewer is the inner TestReviewer")
def step_during_inner_is_inner(context) -> None:
    rv = context.fixtures["during_inner_reviewer"]
    inner = context.fixtures["inner_test_reviewer"]
    assert rv is inner, "inner reviewer not active"


@then("after the inner block exits the Agent's reviewer is the outer TestReviewer")
def step_after_inner_is_outer(context) -> None:
    rv = context.fixtures["after_inner_reviewer"]
    outer = context.fixtures["outer_test_reviewer"]
    assert rv is outer, f"expected outer TestReviewer; got {type(rv).__name__}"


@then("after the outer block exits the Agent's reviewer is the original ClaudeReviewer")
def step_after_outer_is_original(context) -> None:
    rv = context.fixtures["after_outer_reviewer"]
    original = context.fixtures["original_reviewer"]
    assert rv is original


# ---------------------------------------------------------------------------
# Agent.run canonical entry
# ---------------------------------------------------------------------------


@given("a TestReviewer that returns one fixed Comment")
def step_given_test_reviewer_fixed_one(context) -> None:
    # Path/line must match the synthetic hunk fixture's first hunk so
    # peer's diff-validation pass doesn't drop the comment.
    fixed = [
        Comment(
            path="src/file0.py",
            line=10,
            severity="important",
            body="fixed comment",
            rationale="fixed rationale",
        )
    ]
    context.fixtures["fixed_test_reviewer"] = TestReviewer(comments=fixed)


@when("I override the Agent's reviewer with the TestReviewer")
def step_override_with_test_reviewer(context) -> None:
    # Combined override + run executed in the next step; just stash the reviewer.
    context.fixtures["pending_override"] = context.fixtures["fixed_test_reviewer"]


@when('I call Agent.run with pr_url "{url}" and a PeerDeps')
def step_call_agent_run(context, url: str) -> None:
    agent = context.fixtures["agent"]
    override_rv = context.fixtures.get("pending_override")

    # We need to feed Agent.run a Context without making real `gh` calls.
    # Patch peer.context.gather AND gather_codebase_context to return synthetic.
    synth_ctx = _make_context(n_hunks=1)

    def _fake_gather(_url: str) -> Context:
        synth_ctx.pr_url = _url
        return synth_ctx

    with (
        patch("peer.agent.gather", _fake_gather),
        patch("peer.agent.gather_codebase_context", side_effect=RuntimeError("skip")),
    ):
        if override_rv is not None:
            with agent.override(reviewer=override_rv):
                review = agent.run(url, deps=PeerDeps())
        else:
            review = agent.run(url, deps=PeerDeps())
    context.fixtures["review"] = review


@then("the returned Review's comments list has length {n:d}")
def step_review_comments_length(context, n: int) -> None:
    review = context.fixtures["review"]
    assert len(review.comments) == n, (
        f"expected {n} comments, got {len(review.comments)}: {review.comments}"
    )
