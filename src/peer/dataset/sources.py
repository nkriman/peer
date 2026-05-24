"""RawSampleSource Protocol + GitHubInlineCommentSource default impl.

Promoted from the v0 MVP `fetch_human_comments` in `peer.eval`, generalized
to return RawSample (PR metadata + RawComment list, both inline-review and
issue-comment kinds).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..context import _gh_run, parse_pr_url
from .types import RawComment, RawSample

# Explicit deny-list of known reviewer-bot logins (lowercased).
_BOT_DENY_LIST = {
    "coderabbit",
    "coderabbitai",
    "greptile",
    "greptileai",
    "qodo-ai",
    "qodo",
    "graphite-app",
    "codium",
    "codiumai",
    "github-actions",
    "dependabot",
}


def _is_bot(login: str) -> bool:
    """Heuristic: ends with [bot], contains 'bot', or in explicit deny-list."""
    if not login:
        return True
    low = login.lower()
    if low.endswith("[bot]"):
        return True
    if "bot" in low:
        return True
    if low in _BOT_DENY_LIST:
        return True
    return bool(any(deny in low for deny in _BOT_DENY_LIST))


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # GitHub returns ISO-8601 with trailing Z
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


class RawSampleSource(Protocol):
    """A source of raw, pre-classification samples."""

    def fetch(self, pr_url: str) -> RawSample: ...


class GitHubInlineCommentSource:
    """Default RawSampleSource: pulls PR metadata + bot-filtered inline review
    comments + issue comments via the `gh` CLI."""

    def __init__(self, include_issue_comments: bool = True) -> None:
        self.include_issue_comments = include_issue_comments

    def fetch(self, pr_url: str) -> RawSample:
        owner, repo, number = parse_pr_url(pr_url)

        meta = _gh_run(
            [
                "pr",
                "view",
                str(number),
                "--repo",
                f"{owner}/{repo}",
                "--json",
                "title,body,headRefOid,mergedAt",
            ]
        )
        head_sha = meta.get("headRefOid", "") or ""
        pr_title = meta.get("title", "") or ""
        pr_body = meta.get("body") or ""
        merged_at = _parse_dt(meta.get("mergedAt"))

        comments: list[RawComment] = []

        # Inline review comments.
        inline_raw = (
            _gh_run(["api", f"repos/{owner}/{repo}/pulls/{number}/comments", "--paginate"]) or []
        )
        for c in inline_raw:
            login = ((c.get("user") or {}).get("login") or "").strip()
            if _is_bot(login):
                continue
            body = (c.get("body") or "").strip()
            path = c.get("path") or ""
            if not body or not path:
                continue
            line_raw = c.get("line") or c.get("original_line") or 0
            try:
                line = int(line_raw) if line_raw else None
            except (ValueError, TypeError):
                line = None
            comments.append(
                RawComment(
                    source_id=f"github:pulls/comments/{c.get('id', '')}",
                    author=login,
                    path=path,
                    line=line,
                    body=body,
                    kind="inline_review",
                    created_at=_parse_dt(c.get("created_at")),
                )
            )

        # Issue comments (top-level conversation).
        if self.include_issue_comments:
            issue_raw = (
                _gh_run(
                    [
                        "api",
                        f"repos/{owner}/{repo}/issues/{number}/comments",
                        "--paginate",
                    ]
                )
                or []
            )
            for c in issue_raw:
                login = ((c.get("user") or {}).get("login") or "").strip()
                if _is_bot(login):
                    continue
                body = (c.get("body") or "").strip()
                if not body:
                    continue
                comments.append(
                    RawComment(
                        source_id=f"github:issues/comments/{c.get('id', '')}",
                        author=login,
                        path=None,
                        line=None,
                        body=body,
                        kind="issue_comment",
                        created_at=_parse_dt(c.get("created_at")),
                    )
                )

        return RawSample(
            pr_url=pr_url,
            pr_title=pr_title,
            pr_body=pr_body,
            head_sha=head_sha,
            merged_at=merged_at,
            comments=comments,
        )
