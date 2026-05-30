"""Unit tests for _gh_run retry/fail-loud behavior (peer-d55).

The context-gathering `gh` chokepoint must retry transient failures with
exponential backoff and raise a typed ContextGatherError on persistent
failure — never silently proceed with empty PR context. Auth/404 failures are
permanent and must short-circuit without retry.

All subprocess + sleep calls are stubbed; no network, no real waiting.
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from peer import context
from peer.exceptions import (
    ContextGatherError,
    GHCLINotAuthenticated,
    PRNotAccessible,
)


def _proc(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["gh"], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture(autouse=True)
def _no_real_gh(monkeypatch):
    # _gh_check_available() does a shutil.which("gh"); pretend gh is present.
    monkeypatch.setattr(context.shutil, "which", lambda _: "/usr/bin/gh")
    # Never actually sleep during backoff.
    monkeypatch.setattr(context.time, "sleep", lambda _seconds: None)


def test_gh_run_retries_transient_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_run(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            return _proc(1, stderr="HTTP 503: server error")
        return _proc(0, stdout='{"ok": true}')

    monkeypatch.setattr(context.subprocess, "run", fake_run)
    out = context._gh_run(["pr", "view", "1"])
    assert out == {"ok": True}
    assert calls["n"] == 3  # two transient failures, then success


def test_gh_run_raises_context_gather_error_after_max_attempts(monkeypatch):
    calls = {"n": 0}

    def fake_run(*_args, **_kwargs):
        calls["n"] += 1
        return _proc(1, stderr="HTTP 502: bad gateway")

    monkeypatch.setattr(context.subprocess, "run", fake_run)
    with pytest.raises(ContextGatherError):
        context._gh_run(["pr", "view", "1"], max_attempts=3)
    assert calls["n"] == 3  # exhausted the full retry budget


def test_gh_run_does_not_retry_auth_failure(monkeypatch):
    calls = {"n": 0}

    def fake_run(*_args, **_kwargs):
        calls["n"] += 1
        return _proc(1, stderr="To get started with GitHub CLI, please run: gh auth login")

    monkeypatch.setattr(context.subprocess, "run", fake_run)
    with pytest.raises(GHCLINotAuthenticated):
        context._gh_run(["pr", "view", "1"])
    assert calls["n"] == 1  # permanent failure — no retry


def test_gh_run_does_not_retry_not_found(monkeypatch):
    calls = {"n": 0}

    def fake_run(*_args, **_kwargs):
        calls["n"] += 1
        return _proc(1, stderr="GraphQL: Could not resolve to a PullRequest (404 not found)")

    monkeypatch.setattr(context.subprocess, "run", fake_run)
    with pytest.raises(PRNotAccessible):
        context._gh_run(["pr", "view", "999999"])
    assert calls["n"] == 1


def test_gh_run_non_json_passthrough(monkeypatch):
    monkeypatch.setattr(
        context.subprocess, "run", lambda *_a, **_k: _proc(0, stdout="raw diff text")
    )
    out = context._gh_run(["pr", "diff", "1"], parse_json=False)
    assert out == "raw diff text"


def test_gh_run_single_attempt_does_not_sleep(monkeypatch):
    slept = SimpleNamespace(called=False)
    monkeypatch.setattr(context.time, "sleep", lambda _s: setattr(slept, "called", True))
    monkeypatch.setattr(context.subprocess, "run", lambda *_a, **_k: _proc(1, stderr="HTTP 500"))
    with pytest.raises(ContextGatherError):
        context._gh_run(["pr", "view", "1"], max_attempts=1)
    assert slept.called is False  # last attempt must not sleep
