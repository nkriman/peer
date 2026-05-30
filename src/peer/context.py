"""Slice 1 context gathering: PR metadata, diff, surrounding code, prior comments.

CodebaseContext extraction lands in Slice 2 (src/peer/codebase_context.py).
"""

from __future__ import annotations

import base64
import json
import logging
import re
import shutil
import subprocess
import time
from typing import Any

import tiktoken
from unidiff import PatchSet

from .exceptions import (
    ContextGatherError,
    ContextTooLarge,
    GHCLINotAuthenticated,
    GHCLINotAvailable,
    InvalidPRURL,
    PRNotAccessible,
)
from .types import Context, ContextHunk

logger = logging.getLogger(__name__)

_PR_URL_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)/?")
_ENCODER: tiktoken.Encoding | None = None


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    m = _PR_URL_RE.match(pr_url.strip())
    if not m:
        raise InvalidPRURL(f"Not a GitHub PR URL: {pr_url}")
    return m.group(1), m.group(2), int(m.group(3))


def _gh_check_available() -> None:
    if not shutil.which("gh"):
        raise GHCLINotAvailable("`gh` CLI not found on PATH. Install via https://cli.github.com/")


# Retry budget for transient `gh` failures (5xx, rate-limit, network blips).
# Auth errors and 404s are NOT transient — they short-circuit immediately.
_GH_MAX_ATTEMPTS = 3
_GH_BACKOFF_SECONDS = 2.0


def _gh_run(
    args: list[str],
    parse_json: bool = True,
    *,
    max_attempts: int = _GH_MAX_ATTEMPTS,
    backoff_seconds: float = _GH_BACKOFF_SECONDS,
) -> Any:
    """Run a `gh` subprocess, retrying transient failures with exponential
    backoff. Auth failures (GHCLINotAuthenticated) and missing resources
    (PRNotAccessible) are permanent and raise on the first attempt. Any other
    non-zero exit is treated as transient and retried; if it persists past
    `max_attempts`, a ContextGatherError is raised loudly so callers (and the
    eval runner) record a failed sample rather than proceeding with empty
    context (peer-d55)."""
    _gh_check_available()
    last_stderr = ""
    last_rc = 0
    for attempt in range(1, max_attempts + 1):
        result = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            if parse_json:
                return json.loads(result.stdout)
            return result.stdout
        stderr = (result.stderr or "").strip()
        low = stderr.lower()
        # Permanent failures — do not retry.
        if "authentication" in low or "not logged" in low or "gh auth login" in low:
            raise GHCLINotAuthenticated(f"`gh` is not authenticated: {stderr}")
        if "404" in low or "not found" in low or "could not resolve" in low:
            raise PRNotAccessible(f"Resource not accessible: {stderr}")
        # Transient — log, back off, retry.
        last_rc = result.returncode
        last_stderr = stderr[:300]
        logger.warning(
            "gh %s failed (attempt %d/%d): rc=%d %s",
            " ".join(args[:2]),
            attempt,
            max_attempts,
            last_rc,
            last_stderr,
        )
        if attempt < max_attempts:
            time.sleep(backoff_seconds * (2 ** (attempt - 1)))
    raise ContextGatherError(
        f"gh {' '.join(args)} failed {max_attempts}x: rc={last_rc} stderr={last_stderr!r}"
    )


def _parse_diff(diff_text: str) -> list[ContextHunk]:
    patches = PatchSet.from_string(diff_text)
    hunks: list[ContextHunk] = []
    for patched_file in patches:
        path = patched_file.path
        for hunk in patched_file:
            hunks.append(
                ContextHunk(
                    path=path,
                    old_start=hunk.source_start,
                    old_lines=hunk.source_length,
                    new_start=hunk.target_start,
                    new_lines=hunk.target_length,
                    diff_text=str(hunk),
                )
            )
    return hunks


def _fetch_file_at_sha(owner: str, repo: str, path: str, sha: str) -> str | None:
    try:
        data = _gh_run(["api", f"repos/{owner}/{repo}/contents/{path}?ref={sha}"])
    except PRNotAccessible:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("encoding") != "base64":
        return None
    content = data.get("content")
    if not content:
        return None
    try:
        return base64.b64decode(content).decode("utf-8", errors="replace")
    except Exception:
        return None


def _add_surrounding_code(
    hunks: list[ContextHunk], owner: str, repo: str, head_sha: str, n: int
) -> None:
    file_lines: dict[str, list[str]] = {}
    for h in hunks:
        if h.path in file_lines:
            continue
        content = _fetch_file_at_sha(owner, repo, h.path, head_sha)
        file_lines[h.path] = content.splitlines() if content else []

    for h in hunks:
        lines = file_lines.get(h.path, [])
        if not lines:
            continue
        start = max(0, h.new_start - 1 - n)
        end = min(len(lines), h.new_start - 1 + h.new_lines + n)
        if end > start:
            h.surrounding_code = "\n".join(lines[start:end])


def _fetch_prior_comments(owner: str, repo: str, number: int) -> list[str]:
    issue_comments = _gh_run(
        ["api", f"repos/{owner}/{repo}/issues/{number}/comments", "--paginate"]
    )
    review_comments = _gh_run(
        ["api", f"repos/{owner}/{repo}/pulls/{number}/comments", "--paginate"]
    )
    out: list[str] = []
    for c in issue_comments or []:
        author = (c.get("user") or {}).get("login", "?")
        body = (c.get("body") or "").strip()
        if body:
            out.append(f"[issue comment by @{author}]\n{body}")
    for c in review_comments or []:
        author = (c.get("user") or {}).get("login", "?")
        path = c.get("path", "")
        line = c.get("line") or c.get("original_line") or "?"
        body = (c.get("body") or "").strip()
        if body:
            out.append(f"[inline review by @{author} on {path}:{line}]\n{body}")
    return out


def _estimate_tokens(text: str) -> int:
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return len(_ENCODER.encode(text))


def _serialize_for_estimate(ctx: Context) -> str:
    pieces = [ctx.title, ctx.body, *ctx.prior_comments]
    for h in ctx.hunks:
        pieces.append(h.diff_text)
        if h.surrounding_code:
            pieces.append(h.surrounding_code)
    return "\n".join(pieces)


def gather(pr_url: str, context_lines: int = 20, max_tokens: int = 100_000) -> Context:
    """Pull all Slice-1 context the agent needs to review a PR."""
    owner, repo, number = parse_pr_url(pr_url)

    meta = _gh_run(
        [
            "pr",
            "view",
            str(number),
            "--repo",
            f"{owner}/{repo}",
            "--json",
            "title,body,headRefOid",
        ]
    )
    diff_text = _gh_run(
        ["pr", "diff", str(number), "--repo", f"{owner}/{repo}"],
        parse_json=False,
    )

    head_sha = meta["headRefOid"]
    hunks = _parse_diff(diff_text)
    _add_surrounding_code(hunks, owner, repo, head_sha, context_lines)
    prior_comments = _fetch_prior_comments(owner, repo, number)

    ctx = Context(
        pr_url=pr_url,
        owner=owner,
        repo=repo,
        number=number,
        title=meta.get("title", ""),
        body=meta.get("body") or "",
        head_sha=head_sha,
        hunks=hunks,
        prior_comments=prior_comments,
    )
    ctx.token_estimate = _estimate_tokens(_serialize_for_estimate(ctx))
    if ctx.token_estimate > max_tokens:
        raise ContextTooLarge(
            f"Context for {pr_url} is ~{ctx.token_estimate} tokens, "
            f"exceeds max {max_tokens}. Chunking is not yet supported in v0.1; "
            f"skip this PR or raise the limit."
        )
    return ctx
