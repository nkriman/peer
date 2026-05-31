"""Spot-check the QUALITY of human inline review on a candidate repo (peer-7q1).

Density (peer-7q1 measurement) says kubernetes has the most line-anchored human
inline review. But the yield smoke taught us count != quality: comments can be
nits/LGTM/style, not defects. Before committing a repo, eyeball the actual
human inline comment bodies on its densely-reviewed PRs.

Scans recent merged PRs, keeps those with >= MIN_DENSE human inline comments,
and prints each human comment's path:line + body excerpt so we can judge whether
this repo's review is defect-bearing (worth mining) vs cosmetic.

Single process, paced, read-only, zero LLM.
Run: uv run python scripts/inspect_dense_review_quality.py [owner/repo]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

REPO = sys.argv[1] if len(sys.argv) > 1 else "kubernetes/kubernetes"
SCAN = 40  # merged PRs to scan for dense ones
MIN_DENSE = 2  # human inline comments to count a PR as densely reviewed
MAX_SHOW = 6  # dense PRs to print in detail
API_SLEEP = 1.5
BACKOFF = 8.0
MAX_ATTEMPTS = 4


def _gh(args: list[str]):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        proc = subprocess.run(
            ["gh", *args], capture_output=True, text=True, check=False, timeout=120
        )
        if proc.returncode == 0:
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError:
                return None
        if "rate limit" in (proc.stderr or "").lower():
            time.sleep(BACKOFF * attempt)
            continue
        return None
    return None


def _human_inline(repo: str, number: int) -> list[dict]:
    data = _gh(["api", f"repos/{repo}/pulls/{number}/comments", "--paginate"])
    time.sleep(API_SLEEP)
    if not isinstance(data, list):
        return []
    out = []
    for c in data:
        if not isinstance(c, dict):
            continue
        login = (c.get("user") or {}).get("login", "")
        if login and not login.endswith("[bot]"):
            out.append(c)
    return out


def main() -> None:
    print(f"Inspecting human inline-review quality on {REPO}\n")
    nums = _gh(
        [
            "pr",
            "list",
            "--repo",
            REPO,
            "--state",
            "merged",
            "--limit",
            str(SCAN),
            "--json",
            "number",
        ]
    )
    time.sleep(API_SLEEP)
    if not isinstance(nums, list):
        print("NO DATA")
        return
    numbers = [d["number"] for d in nums if "number" in d]

    shown = 0
    dense_found = 0
    for n in numbers:
        comments = _human_inline(REPO, n)
        if len(comments) < MIN_DENSE:
            continue
        dense_found += 1
        if shown >= MAX_SHOW:
            continue
        shown += 1
        print(f"=== PR #{n}  ({len(comments)} human inline comments) ===")
        for c in comments[:8]:
            path = c.get("path", "?")
            line = c.get("line") or c.get("original_line")
            body = " ".join((c.get("body") or "").split())[:160]
            print(f"  {path}:{line}  @{(c.get('user') or {}).get('login', '?')}")
            print(f"    {body}")
        print()

    print("========== SUMMARY ==========")
    print(
        f"scanned {len(numbers)} merged PRs; {dense_found} were dense (>= {MIN_DENSE} human inline)"
    )
    print("Judgement call: are the comments above DEFECTS (mine-worthy) or nits/LGTM?")


if __name__ == "__main__":
    main()
