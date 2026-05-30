"""Fresh contamination-free holdout miner (benchmark-the-field Phase 1, peer-4z5).

Mines real, recently-merged PRs that we KNOW were defective because a later
REVERT PR undid them. The reverted ("buggy") PR is what a reviewer is asked to
review; the files/lines the buggy PR touched are the gold-defect locations a
good reviewer should have flagged. Reverts are the highest-precision defect
signal available without human labeling — the team judged the code bad enough
to roll back — which is exactly what a credibility-shield holdout needs.

Contamination-safe by construction when the buggy PR merged *after* the model
training cutoff: the model cannot have seen the eventual revert.

Scope (v0): revert-based pairs only. Mining PRs that repair a bug without a
formal revert ("fix:" references) is a future enrichment; reverts give
unambiguous ground truth first.

All GitHub I/O goes through an injectable `gh` runner (defaults to the
fail-loud peer.context._gh_run), so this whole module is testable offline.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..context import _gh_run
from .types import GoldDefect, GoldSample, GoldSampleMetadata

logger = logging.getLogger(__name__)

GhRunner = Callable[[list[str]], Any]

# GitHub's canonical revert title is `Revert "<original title> (#1234)"` — the
# original PR number sits inside the closing quote, so allow an optional trailing
# quote after `(#N)`. Also matches the bare `... (#1234)` form (no quote).
_REVERT_TITLE_NUM_RE = re.compile(r"\(#(?P<num>\d+)\)[\"']?\s*$")
# "This reverts commit <sha>." — git's default revert commit body line.
_REVERTS_COMMIT_RE = re.compile(r"This reverts commit (?P<sha>[0-9a-f]{7,40})", re.IGNORECASE)
_IS_REVERT_TITLE_RE = re.compile(r"^\s*revert\b", re.IGNORECASE)
# First hunk header: capture the new-file start line.
_HUNK_NEW_START_RE = re.compile(r"@@ -\d+(?:,\d+)? \+(?P<start>\d+)")


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class RevertPair:
    """A (buggy PR, reverting PR) link recovered from a revert PR."""

    repo: str  # "owner/name"
    fix_pr_number: int
    fix_merged_at: datetime | None
    fix_title: str
    buggy_pr_number: int | None  # parsed from "(#N)" in the revert title
    reverted_sha: str | None  # parsed from "This reverts commit <sha>"


def parse_revert_pr(pr: dict, repo: str) -> RevertPair | None:
    """Parse one merged PR dict (gh `pr list --json number,title,body,mergedAt`)
    into a RevertPair, or None if it is not a linkable revert."""
    title = (pr.get("title") or "").strip()
    if not _IS_REVERT_TITLE_RE.search(title):
        return None
    body = pr.get("body") or ""
    num_match = _REVERT_TITLE_NUM_RE.search(title)
    buggy_num = int(num_match.group("num")) if num_match else None
    sha_match = _REVERTS_COMMIT_RE.search(body)
    reverted_sha = sha_match.group("sha") if sha_match else None
    if buggy_num is None and reverted_sha is None:
        return None  # a revert we cannot link back to its source
    try:
        fix_number = int(pr["number"])
    except (KeyError, ValueError, TypeError):
        return None
    return RevertPair(
        repo=repo,
        fix_pr_number=fix_number,
        fix_merged_at=_parse_dt(pr.get("mergedAt")),
        fix_title=title,
        buggy_pr_number=buggy_num,
        reverted_sha=reverted_sha,
    )


def find_revert_pairs(
    repo: str,
    since: datetime | None,
    *,
    limit: int = 200,
    gh: GhRunner = _gh_run,
) -> list[RevertPair]:
    """List merged revert PRs in `repo` (merged at/after `since`) that link back
    to a specific PR number. `since` is the contamination cutoff."""
    prs = (
        gh(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "merged",
                "--search",
                "revert in:title",
                "--json",
                "number,title,body,mergedAt",
                "--limit",
                str(limit),
            ]
        )
        or []
    )
    out: list[RevertPair] = []
    for pr in prs:
        if not isinstance(pr, dict):
            continue
        merged = _parse_dt(pr.get("mergedAt"))
        if since is not None and merged is not None and merged < since:
            continue
        pair = parse_revert_pr(pr, repo)
        if pair is not None and pair.buggy_pr_number is not None:
            out.append(pair)
    return out


def _hunk_new_start(patch: str | None) -> int | None:
    if not patch:
        return None
    m = _HUNK_NEW_START_RE.search(patch)
    return int(m.group("start")) if m else None


def revert_pair_to_gold_sample(
    pair: RevertPair,
    *,
    cutoff: datetime | None,
    gh: GhRunner = _gh_run,
) -> GoldSample | None:
    """Build a GoldSample for the BUGGY PR: gold defects are the files/lines it
    introduced (later reverted). Returns None if the buggy PR has no usable
    changed files."""
    if pair.buggy_pr_number is None:
        return None
    meta = gh(
        [
            "pr",
            "view",
            str(pair.buggy_pr_number),
            "--repo",
            pair.repo,
            "--json",
            "title,body,mergedAt,url",
        ]
    )
    if not isinstance(meta, dict):
        return None
    buggy_merged = _parse_dt(meta.get("mergedAt"))
    contamination_safe = (
        bool(buggy_merged and buggy_merged > cutoff) if cutoff is not None else None
    )
    files = gh(["api", f"repos/{pair.repo}/pulls/{pair.buggy_pr_number}/files", "--paginate"]) or []
    defects: list[GoldDefect] = []
    for f in files:
        if not isinstance(f, dict):
            continue
        path = f.get("filename")
        if not isinstance(path, str) or not path:
            continue
        defects.append(
            GoldDefect(
                path=path,
                line=_hunk_new_start(f.get("patch")),
                category="defect-correctness",
                severity="important",
                description=(
                    f"This change was later reverted by #{pair.fix_pr_number} "
                    f"({pair.fix_title}) — a good reviewer should have flagged the "
                    f"problem here."
                ),
                source=f"fresh-holdout:revert:#{pair.fix_pr_number}",
                confidence="medium",
            )
        )
    if not defects:
        return None
    pr_url = meta.get("url") or f"https://github.com/{pair.repo}/pull/{pair.buggy_pr_number}"
    return GoldSample(
        pr_url=pr_url,
        pr_title=meta.get("title") or "",
        pr_body=meta.get("body") or "",
        merged_at=buggy_merged,
        gold_defects=defects,
        metadata=GoldSampleMetadata(
            defect_comment_count=len(defects),
            has_followup_bugfix=True,
            curation_source="fresh-holdout:revert",
            contamination_safe=contamination_safe,
        ),
    )


def mine_holdout(
    repos: Sequence[str],
    cutoff: datetime | None,
    *,
    per_repo_limit: int = 200,
    gh: GhRunner = _gh_run,
) -> list[GoldSample]:
    """Mine a fresh holdout across `repos`, keeping only revert-linked buggy PRs
    merged after `cutoff`. Returns GoldSamples tagged with provenance +
    contamination_safe."""
    samples: list[GoldSample] = []
    for repo in repos:
        pairs = find_revert_pairs(repo, since=cutoff, limit=per_repo_limit, gh=gh)
        logger.info("holdout: %s -> %d linkable revert pairs", repo, len(pairs))
        for pair in pairs:
            gs = revert_pair_to_gold_sample(pair, cutoff=cutoff, gh=gh)
            if gs is not None:
                samples.append(gs)
    logger.info("holdout: %d gold samples across %d repos", len(samples), len(repos))
    return samples
