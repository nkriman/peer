"""Step definitions for features/agent_integration.feature.

Covers Agent.run consuming PeerDeps.config + PeerDeps.linters end-to-end.
All scenarios run offline — no LLM calls and no `gh` calls.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from behave import given, then, when  # type: ignore[import-untyped]

from peer import Agent, CodebaseContext, LinterFinding, PeerDeps, TestReviewer
from peer.codebase_context import gather_codebase_context
from peer.config import PeerConfig, Rule
from peer.prompts import format_prompt
from peer.types import Comment, Context, ContextHunk


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


# ---------------------------------------------------------------------------
# Agent.run + PeerConfig severity cap
# ---------------------------------------------------------------------------


@given('an Agent with model "{model}"')
def step_given_agent_simple(context, model: str) -> None:
    context.fixtures["agent"] = Agent(model=model)


@given('a PeerDeps with a PeerConfig that caps "{path}" severity at "{cap}"')
def step_peerdeps_with_cap(context, path: str, cap: str) -> None:
    cfg = PeerConfig(rules=[Rule(paths=[path], severity_cap=cap)])  # type: ignore[arg-type]
    context.fixtures["peer_deps"] = PeerDeps(config=cfg)


@given('a TestReviewer that returns one Comment on "{path}" with severity "{sev}"')
def step_test_reviewer_one_comment(context, path: str, sev: str) -> None:
    fixed = [
        Comment(
            path=path,
            line=10,
            severity=sev,  # type: ignore[arg-type]
            body="test body",
            rationale="test rationale",
        )
    ]
    rv = TestReviewer(comments=fixed)
    # Satisfy both pending-override pathways (this module's + the one in
    # peer_deps_steps.py which expects "fixed_test_reviewer").
    context.fixtures["pending_override"] = rv
    context.fixtures["fixed_test_reviewer"] = rv


@when("I call Agent.run with a synthetic PR")
def step_call_agent_run_synthetic(context) -> None:
    agent = context.fixtures["agent"]
    deps = context.fixtures["peer_deps"]
    test_rv = context.fixtures["pending_override"]
    synth_ctx = _make_context(["src/foo.py"])

    def _fake_gather(_url: str) -> Context:
        synth_ctx.pr_url = _url
        return synth_ctx

    with (
        patch("peer.agent.gather", _fake_gather),
        patch("peer.agent.gather_codebase_context", side_effect=RuntimeError("skip")),
        agent.override(reviewer=test_rv),
    ):
        context.fixtures["review"] = agent.run("https://github.com/test/test/pull/1", deps=deps)


@then("the returned Review has {n:d} comment")
@then("the returned Review has {n:d} comments")
def step_review_has_n(context, n: int) -> None:
    got = len(context.fixtures["review"].comments)
    assert got == n, f"expected {n}, got {got}: {context.fixtures['review'].comments}"


@then('the returned Review\'s first comment has severity "{sev}"')
def step_review_first_severity(context, sev: str) -> None:
    got = context.fixtures["review"].comments[0].severity
    assert got == sev, f"expected {sev}, got {got}"


@then("the returned Review's first comment's path equals \"{path}\"")
def step_review_first_path(context, path: str) -> None:
    got = context.fixtures["review"].comments[0].path
    assert got == path, f"expected {path}, got {got}"


# ---------------------------------------------------------------------------
# Agent.run + ignore filter
# ---------------------------------------------------------------------------


@given('a PeerDeps with a PeerConfig that ignores "{glob}"')
def step_peerdeps_with_ignore(context, glob: str) -> None:
    cfg = PeerConfig(ignore={"glob": [glob]})  # type: ignore[arg-type]
    context.fixtures["peer_deps"] = PeerDeps(config=cfg)


@given("a TestReviewer that synthesizes one Comment per hunk")
def step_test_reviewer_synth_per_hunk(context) -> None:
    # n_comments=10 is way more than we'll have; TestReviewer caps at len(hunks)
    rv = TestReviewer(n_comments=10, severity="minor")
    context.fixtures["pending_override"] = rv
    context.fixtures["fixed_test_reviewer"] = rv


@when('I call Agent.run with a synthetic PR containing hunks for "{a}" and "{b}"')
def step_call_run_two_hunks(context, a: str, b: str) -> None:
    agent = context.fixtures["agent"]
    deps = context.fixtures["peer_deps"]
    test_rv = context.fixtures["pending_override"]
    synth_ctx = _make_context([a, b])

    def _fake_gather(_url: str) -> Context:
        synth_ctx.pr_url = _url
        return synth_ctx

    with (
        patch("peer.agent.gather", _fake_gather),
        patch("peer.agent.gather_codebase_context", side_effect=RuntimeError("skip")),
        agent.override(reviewer=test_rv),
    ):
        context.fixtures["review"] = agent.run("https://github.com/test/test/pull/1", deps=deps)


# ---------------------------------------------------------------------------
# gather_codebase_context + linters
# ---------------------------------------------------------------------------


@given("a fake repo with one Python file")
def step_fake_repo(context) -> None:
    context.fixtures["fake_repo_path"] = Path("/tmp/fake_repo_does_not_matter")
    context.fixtures["fake_ctx"] = _make_context(["src/foo.py"])


@given("a stub Linter returning one fixed LinterFinding")
def step_stub_linter(context) -> None:
    fixed_finding = LinterFinding(
        linter="stub",
        path="src/foo.py",
        line=42,
        rule_id="X001",
        severity="minor",
        message="stub finding",
    )

    class StubLinter:
        name = "stub"

        def lint(self, repo_path: Path, target_files: list[str]) -> list[LinterFinding]:
            return [fixed_finding]

    context.fixtures["stub_linter"] = StubLinter()


@when("I call gather_codebase_context with linters set to the stub Linter")
def step_call_gather_with_linter(context) -> None:
    ctx = context.fixtures["fake_ctx"]
    linter = context.fixtures["stub_linter"]
    # Stub out the expensive parts (tree-sitter parse, repo checkout) so
    # the only path that runs is the linter loop.
    with (
        patch("peer.codebase_context._have_tree_sitter", return_value=True),
        patch(
            "peer.codebase_context._ensure_repo_checkout",
            return_value=Path("/tmp/fake_repo"),
        ),
        patch("peer.codebase_context._extract_modified_symbols"),
        patch("peer.codebase_context._find_related_tests", return_value=([], [])),
    ):
        context.fixtures["cc"] = gather_codebase_context(ctx, linters=[linter])


@then("the returned CodebaseContext's linter_findings has length {n:d}")
def step_cc_linter_findings_len(context, n: int) -> None:
    findings = context.fixtures["cc"].linter_findings
    # Mirror into "findings" so the existing step
    # `the first finding has rule_id "..."` (defined in linter_context_steps)
    # can locate the list.
    context.fixtures["findings"] = findings
    got = len(findings)
    assert got == n, f"expected {n}, got {got}: {findings}"


# Note: `the first finding has rule_id "..."` is provided by
# features/steps/linter_context_steps.py; we reuse it (no duplicate here).


# ---------------------------------------------------------------------------
# format_prompt linter section rendering
# ---------------------------------------------------------------------------


@given("a Context with one hunk")
def step_given_one_hunk_context(context) -> None:
    context.fixtures["ctx"] = _make_context(["src/foo.py"])


@given("a CodebaseContext with one LinterFinding for that hunk")
def step_cc_with_one_finding(context) -> None:
    cc = CodebaseContext(
        linter_findings=[
            LinterFinding(
                linter="ruff",
                path="src/foo.py",
                line=10,
                rule_id="E501",
                severity="nit",
                message="line too long",
            )
        ]
    )
    context.fixtures["cc"] = cc


@given("a CodebaseContext with no LinterFindings")
def step_cc_no_findings(context) -> None:
    context.fixtures["cc"] = CodebaseContext()


@when("I call format_prompt with both")
def step_call_format_prompt(context) -> None:
    context.fixtures["rendered"] = format_prompt(context.fixtures["ctx"], context.fixtures["cc"])


@then('the rendered prompt contains the literal "{s}"')
def step_rendered_contains(context, s: str) -> None:
    text = context.fixtures["rendered"]
    assert s in text, f"expected to find {s!r} in rendered prompt"


@then('the rendered prompt does NOT contain the literal "{s}"')
def step_rendered_not_contains(context, s: str) -> None:
    text = context.fixtures["rendered"]
    assert s not in text, f"unexpectedly found {s!r} in rendered prompt"


@then("the rendered prompt contains the finding's rule_id and message")
def step_rendered_has_rule_and_message(context) -> None:
    text = context.fixtures["rendered"]
    assert "E501" in text, "rule_id E501 missing from rendered prompt"
    assert "line too long" in text, "message missing from rendered prompt"
