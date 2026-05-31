"""RawSampleSource Protocol + GitHubInlineCommentSource default impl.

Promoted from the v0 MVP `fetch_human_comments` in `peer.eval`, generalized
to return RawSample (PR metadata + RawComment list, both inline-review and
issue-comment kinds).
"""

from __future__ import annotations

import re
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


# AI-orchestration comments: a human author whose comment body is DIRECTING an
# AI agent (e.g. "@qodo-merge-pro review the following", "@codeant-ai make
# changes"), rather than reporting a defect. These pass _is_bot (the author is a
# real human) but their content is not human code review — treating them as gold
# contaminates the dataset (peer-5u5 yield check found this on AI-tooling repos).
_AI_AGENT_HANDLE_RE = re.compile(
    r"@(?:coderabbitai|coderabbit|greptile(?:ai)?|qodo(?:-merge(?:-pro)?|-ai)?"
    r"|codium(?:ai)?|codeant-ai|codeant|sourcery-ai|sweep-ai|devin-ai|"
    r"copilot|cursor|graphite-app)\b",
    re.IGNORECASE,
)
# Imperative directed at an agent on the same line as the handle.
_AI_DIRECTIVE_RE = re.compile(
    r"@[\w-]+\b[^.\n]{0,80}\b(review|fix|implement|make changes|address|resolve|"
    r"check if this issue is valid|commit changes)\b",
    re.IGNORECASE,
)


def _is_ai_orchestration_comment(body: str) -> bool:
    """True when a human comment is directing an AI agent rather than reporting a
    defect. Conservative: requires both an agent handle AND an imperative, so a
    normal mention ("thanks @coderabbitai") is not dropped."""
    if not body:
        return False
    return bool(_AI_AGENT_HANDLE_RE.search(body) and _AI_DIRECTIVE_RE.search(body))


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
            if _is_ai_orchestration_comment(body):
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
                if _is_ai_orchestration_comment(body):
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
