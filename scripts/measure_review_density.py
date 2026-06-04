"""Measure human inline-review density on candidate benchmark repos (peer-7q1).

The real selector for the human-gold benchmark is NOT reputation but whether a
repo's merged PRs actually carry line-anchored human review comments our
curation pipeline can read (pulls/{n}/comments). This measures that empirically.

For each repo: sample recent merged PRs, and per PR count human (non-[bot])
inline review comments. Reports, per repo: %PRs with >=2 human inline comments
(dense), mean human inline comments/PR, and median. The 1-2 repos with the
highest density become the benchmark source.

Single process, paced gh calls with rate-limit backoff (the shell-loop version
kept getting truncated). Read-only, zero LLM.

Run: uv run python scripts/measure_review_density.py
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time

# Default candidates; override by passing repos as CLI args (peer-y5t).
CANDIDATES = sys.argv[1:] or [
    "rust-lang/rust",
    "symfony/symfony",
    "kubernetes/kubernetes",
    "pandas-dev/pandas",
    "microsoft/TypeScript",
    "apache/airflow",
]
PER_REPO = 20
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
        err = (proc.stderr or "").lower()
        if "rate limit" in err:
            wait = BACKOFF * attempt
            print(f"    [rate-limit] backoff {wait:.0f}s")
            time.sleep(wait)
            continue
        return None
    return None


def _merged_pr_numbers(repo: str, limit: int) -> list[int]:
    data = _gh(
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "merged",
            "--limit",
            str(limit),
            "--json",
            "number",
        ]
    )
    time.sleep(API_SLEEP)
    if not isinstance(data, list):
        return []
    return [d["number"] for d in data if isinstance(d, dict) and "number" in d]


def _human_inline_count(repo: str, number: int) -> int | None:
    data = _gh(["api", f"repos/{repo}/pulls/{number}/comments", "--paginate"])
    time.sleep(API_SLEEP)
    if not isinstance(data, list):
        return None
    n = 0
    for c in data:
        if not isinstance(c, dict):
            continue
        login = (c.get("user") or {}).get("login", "")
        if login and not login.endswith("[bot]"):
            n += 1
    return n


def main() -> None:
    print(f"Measuring human inline-review density ({PER_REPO} merged PRs/repo)\n")
    rows = []
    for repo in CANDIDATES:
        print(f"=== {repo} ===")
        nums = _merged_pr_numbers(repo, PER_REPO)
        if not nums:
            print("  NO DATA (lookup failed)")
            rows.append((repo, 0, 0, 0.0, 0.0))
            continue
        counts = []
        for i, n in enumerate(nums, 1):
            c = _human_inline_count(repo, n)
            if c is None:
                continue
            counts.append(c)
            if i % 5 == 0:
                print(f"  ...{i}/{len(nums)} sampled")
        if not counts:
            print("  NO comment data")
            rows.append((repo, 0, 0, 0.0, 0.0))
            continue
        dense = sum(1 for c in counts if c >= 2)
        mean = statistics.mean(counts)
        med = statistics.median(counts)
        rows.append((repo, len(counts), dense, mean, med))
        print(f"  n={len(counts)} dense(>=2)={dense} mean={mean:.1f} median={med:.0f}")

    print("\n========== DENSITY SUMMARY ==========")
    print(f"{'repo':<28} {'n':>4} {'dense%':>7} {'mean':>6} {'median':>7}")
    print("-" * 56)
    for repo, n, dense, mean, med in sorted(rows, key=lambda r: -(r[2] / r[1] if r[1] else 0)):
        densepct = f"{100 * dense / n:.0f}%" if n else "—"
        print(f"{repo:<28} {n:>4} {densepct:>7} {mean:>6.1f} {med:>7.0f}")
    print("\nPick the 1-2 highest dense% (and mean) — those have the line-anchored")
    print("human review our curation pipeline can mine into gold.")


if __name__ == "__main__":
    main()
