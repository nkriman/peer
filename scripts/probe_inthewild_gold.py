"""Feasibility probe for the in-the-wild commercial-reviewer track (peer-b8t).

RISKIEST ASSUMPTION under test: we can attach trustworthy gold defects, at
scale, to PRs that CodeRabbit/Greptile/Qodo actually reviewed. If gold is too
sparse, the two-track benchmark (peer-b8t Option C) can't carry a credible
commercial comparison.

This script samples PRs each bot reviewed and measures, per PR, the two gold
signals we know how to mine:
  1. HUMAN review comments — feeds peer's existing curation pipeline
     (dataset/curation.py), the same path that built the django_pydantic sets.
  2. A downstream REVERT/FIX of the PR — the holdout.py revert signal.
It also measures 2+-tool overlap (PRs reviewed by more than one commercial tool),
which decides single-set vs. two-track.

Zero LLM quota. All GitHub I/O is PACED (sleep between calls) to stay under the
secondary rate limit that tripped during the volume probe. Read-only.

Run: uv run python scripts/probe_inthewild_gold.py
Output: /tmp/inthewild_probe.json + a printed summary.

GO/KILL gate (per peer-b8t analysis): if >= ~30% of sampled PRs have at least
one mineable gold signal, the in-the-wild track is viable -> build peer-5u5.
Below that, rethink the gold source before sinking build time.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict, dataclass

# Verified bot logins (peer-2sw). Track 2 reads what these already posted.
BOTS = {
    "coderabbit": "coderabbitai[bot]",
    "greptile": "greptile-apps[bot]",
    "qodo": "codiumai-pr-agent-free[bot]",
}

# Bot/automation logins that do NOT count as "human review" for gold mining.
_BOT_SUFFIX = "[bot]"
_KNOWN_AUTOMATION = {
    "github-actions[bot]",
    "codecov[bot]",
    "dependabot[bot]",
    "pre-commit-ci[bot]",
    "sonarcloud[bot]",
    "netlify[bot]",
    "vercel[bot]",
}

# Pacing: GitHub secondary-rate-limit is aggressive on search. Keep it slow.
SEARCH_SLEEP = 6.0  # between search/issues calls
API_SLEEP = 2.0  # between per-PR REST calls
PER_BOT_SAMPLE = 30  # PRs sampled per tool (90 total ~ a few minutes paced)

# Repo-maturity filter (peer-5u5): the yield check showed gold contamination
# concentrates in 0-star, just-created AI-tooling/demo repos, while real human
# review lives in established repos. Validated 2026-05-31: every contaminated
# source was <=18 stars created 2025-26; every real-review repo was >=86 stars
# created <=2024. A stars>=MIN_STARS gate excludes all the contaminated sources.
MIN_STARS = 50


def is_mature_repo(stars: int | None) -> bool:
    """Pure predicate: a repo is 'mature' enough to expect genuine human review
    if it clears the star threshold. None (lookup failed) -> not mature
    (conservative — don't admit a repo we couldn't verify)."""
    return isinstance(stars, int) and stars >= MIN_STARS


def _gh_json(args: list[str], *, max_attempts: int = 4, backoff: float = 10.0):
    """Paced gh call that backs off hard on secondary-rate-limit. Returns parsed
    JSON, or None on persistent failure (probe tolerates gaps)."""
    for attempt in range(1, max_attempts + 1):
        proc = subprocess.run(
            ["gh", *args], capture_output=True, text=True, check=False, timeout=120
        )
        if proc.returncode == 0:
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError:
                return None
        stderr = (proc.stderr or "") + (proc.stdout or "")
        if "secondary rate limit" in stderr.lower() or "rate limit" in stderr.lower():
            wait = backoff * attempt
            print(f"  [rate-limit] backing off {wait:.0f}s (attempt {attempt})")
            time.sleep(wait)
            continue
        return None
    return None


def _search_bot_prs(bot_login: str, limit: int) -> list[dict]:
    """Sample recent merged PRs the bot commented on. Returns repo/number/url."""
    data = _gh_json(
        [
            "api",
            "-X",
            "GET",
            "search/issues",
            "--raw-field",
            f"q=commenter:{bot_login} type:pr is:merged",
            "--raw-field",
            "sort=updated",
            "--raw-field",
            f"per_page={limit}",
        ]
    )
    time.sleep(SEARCH_SLEEP)
    if not isinstance(data, dict):
        return []
    out = []
    for it in data.get("items", []):
        url = it.get("pull_request", {}).get("html_url") or it.get("html_url", "")
        # repository_url like https://api.github.com/repos/owner/name
        repo = (it.get("repository_url") or "").replace("https://api.github.com/repos/", "")
        if repo and it.get("number"):
            out.append({"repo": repo, "number": it["number"], "url": url})
    return out


def _is_human(login: str) -> bool:
    return bool(login) and not login.endswith(_BOT_SUFFIX) and login not in _KNOWN_AUTOMATION


@dataclass
class PRProbe:
    repo: str
    number: int
    url: str
    human_review_comments: int  # inline review comments by humans
    human_issue_comments: int  # issue-level comments by humans
    has_downstream_revert: bool  # a later "Revert ...(#N)" referencing this PR
    other_bots: list[str]  # which OTHER commercial tools also reviewed this PR


def _probe_pr(pr: dict, source_bot: str) -> PRProbe:
    repo, number = pr["repo"], pr["number"]

    review = _gh_json(["api", f"repos/{repo}/pulls/{number}/comments", "--paginate"]) or []
    time.sleep(API_SLEEP)
    issue = _gh_json(["api", f"repos/{repo}/issues/{number}/comments", "--paginate"]) or []
    time.sleep(API_SLEEP)

    def _login(c):
        return (c.get("user") or {}).get("login", "") if isinstance(c, dict) else ""

    review_logins = [_login(c) for c in review] if isinstance(review, list) else []
    issue_logins = [_login(c) for c in issue] if isinstance(issue, list) else []
    all_logins = set(review_logins) | set(issue_logins)

    other_bots = [
        name for name, login in BOTS.items() if name != source_bot and login in all_logins
    ]

    # Downstream revert: search the repo for a merged revert PR naming this number.
    rev = _gh_json(
        [
            "api",
            "-X",
            "GET",
            "search/issues",
            "--raw-field",
            f'q=repo:{repo} type:pr is:merged "#{number}" revert in:title',
            "--raw-field",
            "per_page=3",
        ]
    )
    time.sleep(SEARCH_SLEEP)
    has_revert = bool(isinstance(rev, dict) and rev.get("total_count", 0) > 0)

    return PRProbe(
        repo=repo,
        number=number,
        url=pr["url"],
        human_review_comments=sum(1 for x in review_logins if _is_human(x)),
        human_issue_comments=sum(1 for x in issue_logins if _is_human(x)),
        has_downstream_revert=has_revert,
        other_bots=other_bots,
    )


def main() -> None:
    results: dict[str, list[dict]] = {}
    for name, login in BOTS.items():
        print(f"=== sampling {name} ({login}) ===")
        prs = _search_bot_prs(login, PER_BOT_SAMPLE)
        print(f"  got {len(prs)} PRs")
        probes = []
        for i, pr in enumerate(prs, 1):
            p = _probe_pr(pr, name)
            probes.append(asdict(p))
            print(
                f"  [{i}/{len(prs)}] {p.repo}#{p.number} "
                f"human_review={p.human_review_comments} human_issue={p.human_issue_comments} "
                f"revert={p.has_downstream_revert} other_bots={p.other_bots}"
            )
        results[name] = probes

    out_path = "/tmp/inthewild_probe.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    # ---- summary + GO/KILL gate ----
    print("\n========== SUMMARY ==========")
    grand_total = 0
    grand_goldable = 0
    overlap_total = 0
    for name, probes in results.items():
        n = len(probes)
        if not n:
            print(f"{name}: 0 sampled")
            continue
        # "mineable gold" = has a downstream revert OR >=1 human review/issue comment.
        goldable = sum(
            1
            for p in probes
            if p["has_downstream_revert"]
            or p["human_review_comments"] > 0
            or p["human_issue_comments"] > 0
        )
        revertable = sum(1 for p in probes if p["has_downstream_revert"])
        overlap = sum(1 for p in probes if p["other_bots"])
        grand_total += n
        grand_goldable += goldable
        overlap_total += overlap
        print(
            f"{name}: n={n} goldable={goldable} ({100 * goldable / n:.0f}%) "
            f"[revert={revertable}, human-comments={goldable - revertable}] "
            f"2+tool-overlap={overlap}"
        )
    if grand_total:
        pct = 100 * grand_goldable / grand_total
        print(f"\nOVERALL goldable: {grand_goldable}/{grand_total} ({pct:.0f}%)")
        print(f"OVERALL 2+ tool overlap: {overlap_total}/{grand_total}")
        gate = "GO (build peer-5u5)" if pct >= 30 else "KILL/RETHINK gold source"
        print(f"GATE (>=30% goldable): {gate}")
    print(f"\nfull results: {out_path}")


if __name__ == "__main__":
    main()
