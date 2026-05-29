"""Tests for BareClaudeCodeReviewer infra-error handling (peer-7op).

The fail-loud-on-infra behaviour was added after the multi_sample_v2_30
baseline collapse: 90/90 samples returned 0 comments / 0 tokens because
`gh pr diff` failed transiently and the reviewer silently produced
empty Reviews. EvalRunner could not distinguish those from real
"no issues" verdicts, so the metric medians went to zero.

These tests pin the new contract: any subprocess error → raise
BaselineInfraError so EvalRunner records the sample as failed.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from peer.baselines import BareClaudeCodeReviewer, BaselineInfraError


def _completed(args, returncode, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=args, returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_gh_pr_diff_failure_raises_after_retries() -> None:
    """Persistent `gh pr diff` failure raises BaselineInfraError."""
    reviewer = BareClaudeCodeReviewer(gh_max_attempts=3, gh_backoff_seconds=0.0)
    with (
        patch(
            "peer.baselines.subprocess.run",
            return_value=_completed(["gh"], 1, stderr="auth required"),
        ) as mock_run,
        pytest.raises(BaselineInfraError, match="gh pr diff failed 3x"),
    ):
        reviewer.review("https://github.com/x/y/pull/1")
    # gh diff attempted exactly gh_max_attempts times; claude was never called.
    gh_calls = [
        c for c in mock_run.call_args_list if c.args[0][0].endswith("gh") or "gh" in c.args[0][0]
    ]
    assert len(gh_calls) == 3


def test_gh_pr_diff_succeeds_on_retry() -> None:
    """Transient gh failure followed by a successful retry proceeds normally."""
    reviewer = BareClaudeCodeReviewer(gh_max_attempts=3, gh_backoff_seconds=0.0)
    diff_text = "diff --git a/x.py b/x.py\n+pass\n"
    claude_envelope = json.dumps(
        {
            "result": '{"comments":[]}',
            "usage": {"input_tokens": 200, "output_tokens": 5},
            "total_cost_usd": 0.0,
        }
    )
    side_effects = [
        _completed(["gh"], 1, stderr="transient"),
        _completed(["gh"], 0, stdout=diff_text),
        _completed(["claude"], 0, stdout=claude_envelope),
    ]
    with patch("peer.baselines.subprocess.run", side_effect=side_effects):
        review = reviewer.review("https://github.com/x/y/pull/1")
    assert review.comments == []
    assert review.usage["input_tokens"] == 200


def test_claude_nonzero_exit_raises() -> None:
    """A nonzero claude exit must raise — not silently return zero comments."""
    reviewer = BareClaudeCodeReviewer(gh_max_attempts=1)
    side_effects = [
        _completed(["gh"], 0, stdout="diff --git a/x.py b/x.py\n+pass\n"),
        _completed(["claude"], 1, stderr="rate limit"),
    ]
    with (
        patch("peer.baselines.subprocess.run", side_effect=side_effects),
        pytest.raises(BaselineInfraError, match="claude exit=1"),
    ):
        reviewer.review("https://github.com/x/y/pull/1")


def test_claude_zero_usage_raises() -> None:
    """input_tokens=0 + output_tokens=0 is impossible; raise rather than report."""
    reviewer = BareClaudeCodeReviewer(gh_max_attempts=1)
    # claude returns a valid JSON envelope but with zero usage — the call
    # plainly did not execute (this is exactly the pattern observed in the
    # multi_sample_v2_30 collapse).
    envelope = json.dumps(
        {
            "result": "",
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "total_cost_usd": 0.0,
        }
    )
    side_effects = [
        _completed(["gh"], 0, stdout="diff --git a/x.py b/x.py\n+pass\n"),
        _completed(["claude"], 0, stdout=envelope),
    ]
    with (
        patch("peer.baselines.subprocess.run", side_effect=side_effects),
        pytest.raises(BaselineInfraError, match="zero usage"),
    ):
        reviewer.review("https://github.com/x/y/pull/1")


def test_claude_non_json_envelope_raises() -> None:
    """If claude returns garbage on stdout, raise rather than treat as empty review."""
    reviewer = BareClaudeCodeReviewer(gh_max_attempts=1)
    side_effects = [
        _completed(["gh"], 0, stdout="diff --git a/x.py b/x.py\n+pass\n"),
        _completed(["claude"], 0, stdout="not json at all"),
    ]
    with (
        patch("peer.baselines.subprocess.run", side_effect=side_effects),
        pytest.raises(BaselineInfraError, match="non-JSON envelope"),
    ):
        reviewer.review("https://github.com/x/y/pull/1")


def test_happy_path_returns_comments() -> None:
    """When everything works, comments parse out of the result text."""
    reviewer = BareClaudeCodeReviewer(gh_max_attempts=1)
    envelope = json.dumps(
        {
            "result": json.dumps(
                {
                    "comments": [
                        {
                            "path": "x.py",
                            "line": 10,
                            "severity": "minor",
                            "body": "consider X",
                            "rationale": "Y",
                        }
                    ]
                }
            ),
            "usage": {"input_tokens": 200, "output_tokens": 50},
            "total_cost_usd": 0.0,
        }
    )
    side_effects = [
        _completed(["gh"], 0, stdout="diff --git a/x.py b/x.py\n+pass\n"),
        _completed(["claude"], 0, stdout=envelope),
    ]
    with patch("peer.baselines.subprocess.run", side_effect=side_effects):
        review = reviewer.review("https://github.com/x/y/pull/1")
    assert len(review.comments) == 1
    assert review.comments[0].path == "x.py"
