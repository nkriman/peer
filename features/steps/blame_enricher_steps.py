"""Step definitions for features/blame_enricher.feature (peer-vh8)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from behave import given, then, when  # type: ignore[import-untyped]

from peer import Recipe
from peer.context_git import gather_git_history
from peer.prompts import format_prompt
from peer.types import CodebaseContext, Context, ContextHunk


def _make_hunk(path: str = "src/foo.py", start: int = 10, lines: int = 2) -> ContextHunk:
    return ContextHunk(
        path=path,
        old_start=start,
        old_lines=lines,
        new_start=start,
        new_lines=lines,
        diff_text=f"@@ -{start},{lines} +{start},{lines} @@\n line\n line",
    )


def _make_context(paths: list[str]) -> Context:
    return Context(
        pr_url="x",
        owner="o",
        repo="r",
        number=1,
        title="t",
        body="",
        head_sha="s",
        hunks=[_make_hunk(p) for p in paths],
        prior_comments=[],
        token_estimate=0,
    )


_FAKE_LOG = (
    "abc1234 Alice: refactor foo for clarity (3 days ago)\n"
    "def5678 Bob: initial implementation of foo (1 week ago)\n"
    "9876543 Carol: add foo skeleton (2 weeks ago)\n"
)

_FAKE_BLAME = (
    "abcdef1234567890abcdef1234567890abcdef12 1 10 1\n"
    "author Alice Author\n"
    "author-mail <alice@example.com>\n"
    "summary refactor\n"
    "\tline content 1\n"
    "fedcba0987654321fedcba0987654321fedcba09 2 11 1\n"
    "author Bob Author\n"
    "author-mail <bob@example.com>\n"
    "summary fix\n"
    "\tline content 2\n"
)


@given('a fake git that returns 3 commit lines and 2 blame lines for "{path}"')
def step_fake_git_ok(context, path: str) -> None:
    def _fake_run(argv, **_kwargs):
        # argv is ["git", "-C", repo, subcmd, ...]
        subcmd = argv[3] if len(argv) > 3 else ""
        if subcmd == "log":
            return subprocess.CompletedProcess(args=argv, returncode=0, stdout=_FAKE_LOG, stderr="")
        if subcmd == "blame":
            return subprocess.CompletedProcess(
                args=argv, returncode=0, stdout=_FAKE_BLAME, stderr=""
            )
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    context.fixtures["_patcher"] = patch("peer.context_git.subprocess.run", side_effect=_fake_run)
    context.fixtures["_patcher"].start()


@given("a fake git that returns exit code 128 for every call")
def step_fake_git_fail(context) -> None:
    def _fake_run(argv, **_kwargs):
        return subprocess.CompletedProcess(
            args=argv, returncode=128, stdout="", stderr="not a git repo"
        )

    context.fixtures["_patcher"] = patch("peer.context_git.subprocess.run", side_effect=_fake_run)
    context.fixtures["_patcher"].start()


@when('I call gather_git_history with one hunk on "{path}" line {line:d} length {n_lines:d}')
def step_call_blame_one_hunk(context, path: str, line: int, n_lines: int) -> None:
    try:
        context.fixtures["blame_text"] = gather_git_history(
            Path("/tmp/fake_repo"), [_make_hunk(path, line, n_lines)]
        )
        context.error = None
    except Exception as e:
        context.fixtures["blame_text"] = None
        context.error = e
    if "_patcher" in context.fixtures:
        context.fixtures["_patcher"].stop()


@when("I call gather_git_history with an empty hunks list")
def step_call_blame_empty(context) -> None:
    context.fixtures["blame_text"] = gather_git_history(Path("/tmp/fake_repo"), [])


@then('the returned string contains "{needle}"')
def step_blame_contains(context, needle: str) -> None:
    text = context.fixtures["blame_text"]
    assert text is not None and needle in text, (
        f"{needle!r} not in:\n{text[:500] if text else '(None)'}"
    )


@then("the returned string contains the literal blame author names")
def step_blame_contains_authors(context) -> None:
    text = context.fixtures["blame_text"]
    assert text is not None
    assert "Alice Author" in text or "Alice" in text, f"missing Alice in:\n{text[:500]}"
    assert "Bob Author" in text or "Bob" in text, f"missing Bob in:\n{text[:500]}"


@then("the returned string is the empty string")
def step_blame_empty(context) -> None:
    text = context.fixtures["blame_text"]
    assert text == "", f"expected '', got {text!r}"


# Note: `no exception is raised` is provided by features/steps/peer_deps_steps.py.
# That implementation reads context.error, not context.fixtures["blame_error"], so we
# mirror our value into context.error in the When-step instead.


# ---------------------------------------------------------------------------
# CodebaseContext + gather_codebase_context
# ---------------------------------------------------------------------------


@when("I construct a default CodebaseContext")
def step_default_cc(context) -> None:
    context.fixtures["cc"] = CodebaseContext()


@then("the CodebaseContext's git_history equals the empty string")
def step_cc_empty_history(context) -> None:
    cc: CodebaseContext = context.fixtures["cc"]
    assert cc.git_history == "", f"expected '', got {cc.git_history!r}"


@given('a fake gather_git_history returning "{text}"')
def step_fake_gather(context, text: str) -> None:
    def _fake(*_args, **_kwargs):
        return text

    context.fixtures["_gather_patcher"] = patch("peer.context_git.gather_git_history", _fake)
    context.fixtures["_gather_patcher"].start()


@when("I call gather_codebase_context with include_git_history True")
def step_call_gather_with_blame(context) -> None:
    from peer.codebase_context import gather_codebase_context

    ctx = _make_context(["src/foo.py"])
    with (
        patch("peer.codebase_context._have_tree_sitter", return_value=True),
        patch("peer.codebase_context._ensure_repo_checkout", return_value=Path("/tmp/fake_repo")),
        patch("peer.codebase_context._extract_modified_symbols"),
        patch("peer.codebase_context._find_related_tests", return_value=([], [])),
    ):
        context.fixtures["cc"] = gather_codebase_context(ctx, include_git_history=True)
    if "_gather_patcher" in context.fixtures:
        context.fixtures["_gather_patcher"].stop()


@when("I call gather_codebase_context with include_git_history False")
def step_call_gather_without_blame(context) -> None:
    from peer.codebase_context import gather_codebase_context

    ctx = _make_context(["src/foo.py"])
    with (
        patch("peer.codebase_context._have_tree_sitter", return_value=True),
        patch("peer.codebase_context._ensure_repo_checkout", return_value=Path("/tmp/fake_repo")),
        patch("peer.codebase_context._extract_modified_symbols"),
        patch("peer.codebase_context._find_related_tests", return_value=([], [])),
    ):
        context.fixtures["cc"] = gather_codebase_context(ctx, include_git_history=False)


@then('the returned CodebaseContext\'s git_history equals "{val}"')
def step_returned_cc_history(context, val: str) -> None:
    cc: CodebaseContext = context.fixtures["cc"]
    assert cc.git_history == val, f"expected {val!r}, got {cc.git_history!r}"


@then("the returned CodebaseContext's git_history equals the empty string")
def step_returned_cc_empty(context) -> None:
    cc: CodebaseContext = context.fixtures["cc"]
    assert cc.git_history == "", f"expected '', got {cc.git_history!r}"


# ---------------------------------------------------------------------------
# format_prompt rendering
# ---------------------------------------------------------------------------


@given('a Context with one hunk and a CodebaseContext with git_history "{val}"')
def step_ctx_with_history(context, val: str) -> None:
    context.fixtures["ctx"] = _make_context(["src/foo.py"])
    context.fixtures["cc"] = CodebaseContext(git_history=val)


@given("a Context with one hunk and a CodebaseContext with empty git_history")
def step_ctx_with_empty_history(context) -> None:
    context.fixtures["ctx"] = _make_context(["src/foo.py"])
    context.fixtures["cc"] = CodebaseContext()


# Note: `I call format_prompt with both` and `the rendered prompt contains/does NOT contain`
# are provided by features/steps/agent_integration_steps.py — reused via context.fixtures["rendered"].


# ---------------------------------------------------------------------------
# Recipe field default
# ---------------------------------------------------------------------------


@then("the Recipe's include_git_history equals False")
def step_recipe_default_blame(context) -> None:
    # Reuses the "When I construct a Recipe with no arguments" step from
    # autoresearch_recipe_steps.py, which sets context.fixtures["recipe"].
    recipe: Recipe = context.fixtures["recipe"]
    assert recipe.include_git_history is False
