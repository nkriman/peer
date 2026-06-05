"""ClaudeCodeCLIReviewer must fail loud on CLI failure (peer-2sw).

A non-zero `claude` exit or unparseable output previously logged a warning and
returned a 0-comment Review — so a CLI failure (network drop, transient error)
was silently recorded by EvalRunner as "peer found nothing", a fake zero that
corrupts the benchmark. These pin the fail-loud contract (matches
BareClaudeCodeReviewer / BaselineInfraError).
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from peer import deps as _deps_module
from peer.exceptions import ReviewerInfraError
from peer.reviewers import ClaudeCodeCLIReviewer
from peer.types import Context, ContextHunk


def _ctx() -> Context:
    return Context(
        pr_url="https://github.com/o/r/pull/1",
        owner="o",
        repo="r",
        number=1,
        title="t",
        body="",
        head_sha="h",
        hunks=[
            ContextHunk(
                path="a.py", old_start=1, old_lines=1, new_start=1, new_lines=1, diff_text="+x"
            )
        ],
    )


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture(autouse=True)
def _allow_llm(monkeypatch):
    monkeypatch.setattr(_deps_module, "ALLOW_LLM_CALLS", True)


def test_nonzero_cli_exit_raises():
    r = ClaudeCodeCLIReviewer()
    with (
        patch(
            "peer.reviewers.subprocess.run", return_value=_completed(1, stdout="", stderr="boom")
        ),
        pytest.raises(ReviewerInfraError, match="exited 1"),
    ):
        r.review(_ctx())


def test_unparseable_stdout_raises():
    r = ClaudeCodeCLIReviewer()
    with (
        patch("peer.reviewers.subprocess.run", return_value=_completed(0, stdout="not json")),
        pytest.raises(ReviewerInfraError, match="non-JSON"),
    ):
        r.review(_ctx())
