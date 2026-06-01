"""Tests for _ensure_repo_checkout fail-fast behavior (peer-jln).

The kubernetes benchmark exposed that an unreachable SHA on a large monorepo
hung to the 300s per-sample cap. The fix caps every git op with a timeout and
falls back fast. These tests pin: (1) a timeout is treated as failure (returns
None), not a hang; (2) the SHA-fetch path is attempted before the PR-head path;
(3) a clean fallback to None when nothing checks out.

All subprocess calls are stubbed; no real git, no network.
"""

from __future__ import annotations

import subprocess

from peer import codebase_context as cc


def _ok(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=""
    )


def test_git_returns_none_on_timeout(monkeypatch):
    def boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="git", timeout=60)

    monkeypatch.setattr(cc.subprocess, "run", boom)
    assert cc._git(["git", "status"], timeout=60) is None


def test_checkout_direct_hit_skips_fetch(monkeypatch, tmp_path):
    # Repo already exists; direct checkout succeeds -> no fetch attempted.
    monkeypatch.setattr(cc, "CACHE_DIR", tmp_path)
    repo_path = tmp_path / "kubernetes__kubernetes"
    repo_path.mkdir(parents=True)
    calls = []

    def fake_run(args, **_k):
        calls.append(args)
        if args[:1] == ["git"] and "checkout" in args:
            return _ok()
        raise AssertionError(f"unexpected call: {args}")

    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    out = cc._ensure_repo_checkout("kubernetes", "kubernetes", 139323, "deadbeef")
    assert out == repo_path
    assert not any("fetch" in c for c in calls)  # no fetch needed


def test_sha_fetch_attempted_before_pr_head(monkeypatch, tmp_path):
    monkeypatch.setattr(cc, "CACHE_DIR", tmp_path)
    (tmp_path / "kubernetes__kubernetes").mkdir(parents=True)
    seq = []

    def fake_run(args, **_k):
        seq.append(args)
        if "checkout" in args:
            # checkout succeeds only after the SHA fetch (2nd checkout call).
            n_co = sum(1 for a in seq if "checkout" in a)
            return _ok() if n_co >= 2 else _ok(returncode=1)
        if "fetch" in args:
            return _ok()  # SHA fetch succeeds
        return _ok()

    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    out = cc._ensure_repo_checkout("kubernetes", "kubernetes", 139323, "abc123")
    assert out is not None
    # The first fetch must be the direct SHA fetch (--depth=1 origin <sha>),
    # not the pull/N/head ref.
    fetches = [c for c in seq if "fetch" in c]
    assert fetches, "expected a fetch"
    assert "abc123" in fetches[0]
    assert "--depth=1" in fetches[0]


def test_returns_none_fast_when_unreachable(monkeypatch, tmp_path):
    # Every checkout fails, every fetch fails -> None (the k8s merged-head case).
    monkeypatch.setattr(cc, "CACHE_DIR", tmp_path)
    (tmp_path / "kubernetes__kubernetes").mkdir(parents=True)

    def fake_run(args, **_k):
        if "checkout" in args:
            return _ok(returncode=1)
        return _ok(returncode=1)

    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    out = cc._ensure_repo_checkout("kubernetes", "kubernetes", 139323, "unreachable")
    assert out is None


def test_timeout_during_checkout_yields_none(monkeypatch, tmp_path):
    monkeypatch.setattr(cc, "CACHE_DIR", tmp_path)
    (tmp_path / "kubernetes__kubernetes").mkdir(parents=True)

    def fake_run(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="git", timeout=60)

    monkeypatch.setattr(cc.subprocess, "run", fake_run)
    out = cc._ensure_repo_checkout("kubernetes", "kubernetes", 1, "sha")
    assert out is None  # fast, not a hang


def test_gather_falls_back_to_base_sha_when_head_unreachable(monkeypatch, tmp_path):
    # head_sha unreachable (squash-merged), base_sha reachable: context checkout
    # must try head, then fall back to base (peer-smz).
    from peer.types import Context

    monkeypatch.setattr(cc, "_have_tree_sitter", lambda: True)
    attempted: list[str] = []

    def fake_ensure(owner, repo, pr_number, sha):
        attempted.append(sha)
        return tmp_path if sha == "basesha" else None  # only base resolves

    monkeypatch.setattr(cc, "_ensure_repo_checkout", fake_ensure)
    # Stop after checkout: make symbol extraction a no-op so we isolate the path.
    monkeypatch.setattr(cc, "_extract_modified_symbols", lambda *a, **k: None)

    ctx = Context(
        pr_url="https://github.com/k/k/pull/1",
        owner="k",
        repo="k",
        number=1,
        title="t",
        body="",
        head_sha="headsha",
        base_sha="basesha",
    )
    cc.gather_codebase_context(ctx)
    assert attempted == ["headsha", "basesha"]  # head first, then base


def test_gather_skips_cleanly_when_both_unreachable(monkeypatch):
    from peer.types import Context

    monkeypatch.setattr(cc, "_have_tree_sitter", lambda: True)
    monkeypatch.setattr(cc, "_ensure_repo_checkout", lambda *a, **k: None)
    ctx = Context(
        pr_url="https://github.com/k/k/pull/1",
        owner="k",
        repo="k",
        number=1,
        title="t",
        body="",
        head_sha="h",
        base_sha="b",
    )
    out = cc.gather_codebase_context(ctx)
    assert len(out.modified_symbols) == 0  # clean empty, no raise
