"""External GitHub-app reviewer adapters (benchmark-the-field Phase 0, peer-ya3).

Scores a third-party AI reviewer (CodeRabbit, Greptile, Qodo Merge, ...) by
reading the inline review comments it ALREADY posted on a PR and mapping them
to peer Comments. Matches the EvalRunner `.review(pr_url) -> Review` seam
(exactly like BareClaudeCodeReviewer), so commercial tools flow through the
same CrossRunRunner + scoring (DetectionRate / SignalToNoiseRatio /
classify_comment) as peer itself.

We read what the tool actually said on real PRs rather than driving it
ourselves: these tools run as GitHub apps on PR events, so the honest
measurement is "what comments did it post on this PR".
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
from dataclasses import dataclass

from .types import Comment, Review, Severity

logger = logging.getLogger(__name__)


class ExternalReviewerError(RuntimeError):
    """gh fetch failed persistently, or returned an unusable payload. Raised
    (not swallowed) so EvalRunner records an errored sample instead of a fake
    zero-comment 'success' — the same fail-loud contract as BaselineInfraError
    (peer-7op). A silently-empty external review would corrupt the leaderboard
    exactly the way collapsed baselines faked a KEEP."""


_PR_URL_RE = re.compile(r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)")


def _parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    m = _PR_URL_RE.search(pr_url)
    if not m:
        raise ExternalReviewerError(f"could not parse owner/repo/number from {pr_url!r}")
    return m["owner"], m["repo"], int(m["number"])


def _parse_paginated_json(stdout: str) -> list:
    """Parse `gh api --paginate` output, which may be a single JSON array OR
    several concatenated JSON values (one per page, depending on gh version).
    Returns a flat list."""
    s = stdout.strip()
    if not s:
        return []
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, list) else [obj]
    except json.JSONDecodeError:
        pass
    merged: list = []
    decoder = json.JSONDecoder()
    idx, n = 0, len(s)
    while idx < n:
        while idx < n and s[idx].isspace():
            idx += 1
        if idx >= n:
            break
        obj, end = decoder.raw_decode(s, idx)
        if isinstance(obj, list):
            merged.extend(obj)
        else:
            merged.append(obj)
        idx = end
    return merged


def _matches_bot(comment: dict, bot_login: str) -> bool:
    user = comment.get("user") or {}
    login = user.get("login") if isinstance(user, dict) else None
    return isinstance(login, str) and login.lower() == bot_login.lower()


@dataclass
class GitHubAppReviewer:
    """Read a GitHub-app reviewer's inline comments on a PR as a peer Review.

    `bot_login` is the GitHub account the tool posts as, e.g.
    "coderabbitai[bot]". These logins must be verified against real PRs in
    Phase 2 — the convenience constructors below carry best-known defaults.
    """

    bot_login: str
    name: str = "external"
    model: str = "external:unknown"
    gh_bin: str = "gh"
    # External tools don't emit peer's 4-tier severity. Headline metrics
    # (DetectionRate, recall, SNR) don't depend on severity; only
    # PrecisionPerSeverity / SeverityCalibration do, so we default and document.
    default_severity: Severity = "minor"
    gh_max_attempts: int = 3
    gh_backoff_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.gh_max_attempts < 1:
            raise ValueError(f"gh_max_attempts must be >= 1; got {self.gh_max_attempts}")
        if self.model == "external:unknown" and self.name != "external":
            self.model = f"external:{self.name}"

    def review(self, pr_url: str) -> Review:
        owner, repo, number = _parse_pr_url(pr_url)
        raw = self._fetch_inline_comments(owner, repo, number)
        comments: list[Comment] = []
        for c in raw:
            if not isinstance(c, dict) or not _matches_bot(c, self.bot_login):
                continue
            mapped = self._to_comment(c)
            if mapped is not None:
                comments.append(mapped)
        usage = {"input_tokens": 0, "output_tokens": 0, "model": self.model}
        reason = None if comments else f"{self.name}: no line-anchored comments on this PR"
        return Review(comments=comments, usage=usage, reason=reason)

    def _fetch_inline_comments(self, owner: str, repo: str, number: int) -> list:
        gh = shutil.which(self.gh_bin) or self.gh_bin
        endpoint = f"repos/{owner}/{repo}/pulls/{number}/comments"
        last_stderr = ""
        last_rc = 0
        for attempt in range(1, self.gh_max_attempts + 1):
            proc = subprocess.run(
                [gh, "api", endpoint, "--paginate"],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
            if proc.returncode == 0:
                try:
                    return _parse_paginated_json(proc.stdout)
                except (json.JSONDecodeError, ValueError) as e:
                    raise ExternalReviewerError(
                        f"gh api {endpoint} returned unparseable JSON: {e}"
                    ) from e
            last_rc = proc.returncode
            last_stderr = (proc.stderr or "")[:300]
            logger.warning(
                "gh api %s failed (attempt %d/%d): rc=%d %s",
                endpoint,
                attempt,
                self.gh_max_attempts,
                last_rc,
                last_stderr,
            )
            if attempt < self.gh_max_attempts:
                time.sleep(self.gh_backoff_seconds * (2 ** (attempt - 1)))
        raise ExternalReviewerError(
            f"gh api {endpoint} failed {self.gh_max_attempts}x: rc={last_rc} stderr={last_stderr!r}"
        )

    def _to_comment(self, c: dict) -> Comment | None:
        path = c.get("path")
        if not isinstance(path, str) or not path:
            return None  # file-level / outdated comment, not line-anchored — skip
        line = c.get("line")
        if line is None:
            line = c.get("original_line")
        body = c.get("body") or ""
        if not body.strip():
            return None
        return Comment(
            path=path,
            line=line if isinstance(line, int) else None,
            severity=self.default_severity,
            body=body,
            rationale="(external reviewer: rationale folded into comment body)",
        )


# Convenience constructors. Bot logins VERIFIED against real PRs in Phase 2
# (peer-2sw, 2026-05-30) by reading actual posted comments — see each note.
# IMPORTANT (peer-2sw finding): all three tools post the bulk of their review as
# a single ISSUE-LEVEL summary comment (issues/{n}/comments), and only
# SOMETIMES add line-anchored inline comments (pulls/{n}/comments). This adapter
# reads inline only, so on PRs with no inline findings a tool scores as zero
# here even though it posted a summary. Issue-level handling is tracked
# separately; until then these numbers are an inline-only lower bound.
def coderabbit() -> GitHubAppReviewer:
    # VERIFIED: posts as coderabbitai[bot]; inline comments are line-anchored
    # (path+line). Org account id=132028505.
    return GitHubAppReviewer(bot_login="coderabbitai[bot]", name="coderabbit")


def greptile() -> GitHubAppReviewer:
    # VERIFIED: real login is greptile-apps[bot] (NOT greptileai[bot] — that
    # org exists but is not the posting account). Inline comments line-anchored.
    return GitHubAppReviewer(bot_login="greptile-apps[bot]", name="greptile")


def qodo_merge() -> GitHubAppReviewer:
    # VERIFIED: free tier posts as codiumai-pr-agent-free[bot] (qodo-merge-pro[bot]
    # is the paid tier and was not observable on public PRs). Qodo posts
    # issue-level summaries; inline comments were absent on the sampled PRs.
    return GitHubAppReviewer(bot_login="codiumai-pr-agent-free[bot]", name="qodo")
