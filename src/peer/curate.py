"""Curate PRs with substantive human review for eval gold-standard data.

Pulls merged PRs from one or more repos within a date range, filters for
substantive human-only review activity (excludes bot accounts), and writes
clean PRRecord rows to JSONL.

Defaults are tuned for the eval-against-history use case:

- Date range: 2023-01-01 to 2023-12-31 (pre-AI-tool-era for a clean
  human-only baseline; commercial PR-review bots adoption took off in 2024).
- Repos: django/django + pydantic/pydantic (validated 2026-05-23 — both
  have substantive multi-reviewer culture in 2023).
- Threshold: at least 2 human reviewers OR at least 2 human inline comments
  per PR (filters out drive-by approvals and pure dependency bumps).

Uses the `gh` CLI under the hood (already authed in most dev environments;
no need for a PyGithub token at curation time).

Usage:
    python -m peer.curate
    # → writes data/curated_<date>.jsonl

Or programmatically:
    from peer.curate import curate
    records = curate(repos=["pydantic/pydantic"], date_range=("2023-06-01", "2023-12-31"))

TODOs for v0.1:
- Fetch the diff (currently only diff_url is captured)
- Configurable bot pattern list via project config
- Resume/retry on transient gh failures
- argparse / typer CLI surface
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

BOT_PATTERNS: list[str] = [
    # CI / repo automation
    "github-actions",
    "dependabot",
    "renovate",
    "codecov",
    "vercel",
    "netlify",
    "linear-app",
    # AI PR-review tools (the contamination we're filtering against)
    "greptile",
    "coderabbit",
    "graphite-app",
    "qodo-ai",
    "qodo-merge",
    "sweep-ai",
    "codium",
    "pr-agent",
]

DEFAULT_REPOS: list[str] = ["django/django", "pydantic/pydantic"]
DEFAULT_DATE_RANGE: tuple[str, str] = ("2023-01-01", "2023-12-31")
DEFAULT_MIN_REVIEWERS: int = 2
DEFAULT_MIN_INLINE_COMMENTS: int = 2
DEFAULT_LIMIT_PER_REPO: int = 100


@dataclass
class ReviewComment:
    """A single inline review comment on a PR."""

    path: str
    line: int | None
    author: str
    body: str
    created_at: str


@dataclass
class PRRecord:
    """The canonical curated PR record. JSONL row shape."""

    repo: str
    number: int
    title: str
    author: str
    merged_at: str
    body: str
    diff_url: str
    human_reviewers: list[str] = field(default_factory=list)
    human_inline_comments: list[ReviewComment] = field(default_factory=list)


def is_bot(login: str | None) -> bool:
    """True if the login matches a known bot pattern."""
    if not login:
        return True
    lower = login.lower()
    return any(pattern in lower for pattern in BOT_PATTERNS)


def _run_gh(args: list[str]) -> str:
    """Run a gh CLI command and return stdout, raising on non-zero exit."""
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def fetch_pr_list(
    repo: str,
    date_range: tuple[str, str],
    limit: int = DEFAULT_LIMIT_PER_REPO,
) -> list[dict]:
    """List merged PRs in the given date range via gh CLI."""
    stdout = _run_gh(
        [
            "pr", "list",
            "--repo", repo,
            "--state", "merged",
            "--search", f"merged:{date_range[0]}..{date_range[1]}",
            "--limit", str(limit),
            "--json", "number,title,author,body,mergedAt,reviews",
        ]
    )
    return json.loads(stdout)


def fetch_inline_comments(repo: str, pr_number: int) -> list[dict]:
    """Fetch all inline review comments for a PR via gh api."""
    stdout = _run_gh(
        ["api", "--paginate", f"repos/{repo}/pulls/{pr_number}/comments"]
    )
    # Paginated output may concatenate JSON arrays; handle both cases.
    stdout = stdout.strip()
    if not stdout:
        return []
    # If multiple pages, gh --paginate concatenates without separators.
    # Simplest robust parse: try direct, then split on `][`.
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        merged = stdout.replace("][", ",")
        return json.loads(merged)


def to_record(repo: str, pr: dict, inline_comments: list[dict]) -> PRRecord:
    """Build a clean PRRecord from raw gh JSON, filtering bots."""
    reviewers = sorted(
        {
            (r.get("author") or {}).get("login", "")
            for r in pr.get("reviews", [])
            if not is_bot((r.get("author") or {}).get("login"))
        }
        - {""}
    )

    human_inline: list[ReviewComment] = []
    for c in inline_comments:
        login = (c.get("user") or {}).get("login")
        if is_bot(login):
            continue
        body = c.get("body") or ""
        # Skip near-empty comments (often just emoji or "lgtm" noise)
        if len(body.strip()) < 5:
            continue
        human_inline.append(
            ReviewComment(
                path=c.get("path", ""),
                line=c.get("line") or c.get("original_line"),
                author=login or "unknown",
                body=body,
                created_at=c.get("created_at", ""),
            )
        )

    return PRRecord(
        repo=repo,
        number=pr["number"],
        title=pr.get("title", ""),
        author=((pr.get("author") or {}).get("login")) or "unknown",
        merged_at=pr.get("mergedAt", ""),
        body=pr.get("body") or "",
        diff_url=f"https://github.com/{repo}/pull/{pr['number']}.diff",
        human_reviewers=reviewers,
        human_inline_comments=human_inline,
    )


def curate(
    repos: list[str] | None = None,
    date_range: tuple[str, str] | None = None,
    min_reviewers: int = DEFAULT_MIN_REVIEWERS,
    min_inline_comments: int = DEFAULT_MIN_INLINE_COMMENTS,
    limit_per_repo: int = DEFAULT_LIMIT_PER_REPO,
    output_path: Path | None = None,
) -> list[PRRecord]:
    """Curate substantive-review PRs from the given repos and write JSONL.

    A PR qualifies if it has at least `min_reviewers` distinct human
    reviewers OR at least `min_inline_comments` substantive inline comments.

    Returns the list of qualifying PRRecord objects and also writes them
    to `output_path` (default: data/curated_<today>.jsonl).
    """
    repos = repos or DEFAULT_REPOS
    date_range = date_range or DEFAULT_DATE_RANGE
    output_path = output_path or Path("data") / f"curated_{date.today().isoformat()}.jsonl"

    records: list[PRRecord] = []
    for repo in repos:
        print(f"=== {repo} ===")
        try:
            prs = fetch_pr_list(repo, date_range, limit_per_repo)
        except subprocess.CalledProcessError as exc:
            print(f"  failed to list PRs for {repo}: {exc.stderr or exc}")
            continue

        for pr in prs:
            try:
                inline = fetch_inline_comments(repo, pr["number"])
            except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
                print(f"  skip #{pr['number']}: comment fetch failed ({type(exc).__name__})")
                continue

            rec = to_record(repo, pr, inline)
            if (
                len(rec.human_reviewers) >= min_reviewers
                or len(rec.human_inline_comments) >= min_inline_comments
            ):
                records.append(rec)
                print(
                    f"  ✓ #{rec.number}: "
                    f"{len(rec.human_reviewers)} reviewers, "
                    f"{len(rec.human_inline_comments)} inline comments"
                )
            else:
                print(f"  - #{pr['number']}: below threshold")

    # Write JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        for rec in records:
            f.write(json.dumps(asdict(rec), default=str) + "\n")

    print(f"\nCurated {len(records)} PRs → {output_path}")
    return records


if __name__ == "__main__":
    curate()
