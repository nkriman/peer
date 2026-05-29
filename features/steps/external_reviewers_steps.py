"""Steps for features/external_reviewers.feature (benchmark-the-field Phase 0)."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

from behave import given, then, when  # type: ignore[import-untyped]

from peer.external_reviewers import ExternalReviewerError, GitHubAppReviewer

_PR_URL = "https://github.com/o/r/pull/1"


def _completed(stdout: str = "", returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["gh"], returncode=returncode, stdout=stdout, stderr=stderr
    )


@given("a PR whose inline comments are")
@given("a PR whose inline comments are:")
def step_pr_inline_comments(context) -> None:
    payload = []
    for row in context.table:
        line_raw = (row["line"] or "").strip()
        payload.append(
            {
                "user": {
                    "login": row["author"],
                    "type": "Bot" if "[bot]" in row["author"] else "User",
                },
                "path": row["path"],
                "line": int(line_raw) if line_raw else None,
                "body": row["body"],
            }
        )
    context.fixtures["gh_stdout"] = json.dumps(payload)
    context.fixtures["gh_fail"] = False


@given("the gh CLI always fails")
def step_gh_always_fails(context) -> None:
    context.fixtures["gh_stdout"] = ""
    context.fixtures["gh_fail"] = True


def _run_reviewer(context, bot_login: str, max_attempts: int = 1):
    fail = context.fixtures.get("gh_fail", False)
    stdout = context.fixtures.get("gh_stdout", "[]")
    if fail:
        ret = _completed(returncode=1, stderr="boom")
    else:
        ret = _completed(stdout=stdout, returncode=0)
    reviewer = GitHubAppReviewer(
        bot_login=bot_login, gh_max_attempts=max_attempts, gh_backoff_seconds=0.0
    )
    with patch("peer.external_reviewers.subprocess.run", return_value=ret):
        try:
            context.fixtures["review"] = reviewer.review(_PR_URL)
            context.fixtures["error"] = None
        except Exception as e:
            context.fixtures["review"] = None
            context.fixtures["error"] = e


@when('I run GitHubAppReviewer for bot "{bot_login}" on the PR')
def step_run_reviewer(context, bot_login: str) -> None:
    _run_reviewer(context, bot_login)


@when('I run GitHubAppReviewer for bot "{bot_login}" on the PR with max_attempts {n:d}')
def step_run_reviewer_attempts(context, bot_login: str, n: int) -> None:
    _run_reviewer(context, bot_login, max_attempts=n)


@then("the external Review has {n:d} comments")
def step_review_has_n(context, n: int) -> None:
    review = context.fixtures["review"]
    assert review is not None, f"expected a Review, got error {context.fixtures.get('error')!r}"
    assert len(review.comments) == n, f"expected {n} comments, got {len(review.comments)}"


@then('the external Review comment for "{path}" is on line {line:d}')
def step_review_comment_line(context, path: str, line: int) -> None:
    review = context.fixtures["review"]
    match = next((c for c in review.comments if c.path == path), None)
    assert match is not None, f"no comment for {path}"
    assert match.line == line, f"expected line {line}, got {match.line}"


@then("an ExternalReviewerError is raised")
def step_error_raised(context) -> None:
    err = context.fixtures["error"]
    assert isinstance(err, ExternalReviewerError), f"expected ExternalReviewerError, got {err!r}"
