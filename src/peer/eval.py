"""Evaluation harness — score peer reviews against human reviewer comments.

MVP scope (Slice 3a):
- Pull inline review comments humans left on the PR (excluding bots)
- For each peer comment, use a cheap LLM judge (Haiku 4.5) to decide
  if it matches any human comment on the same file
- Report per-PR hit rate (human comments matched) and novel rate
  (peer comments humans didn't flag) plus aggregate

Designed to be wider eval ground later (per-comment severity calibration,
false-positive grading, comment substance) — kept small for v0.1.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import anthropic

from .agent import Agent
from .context import _gh_run, parse_pr_url
from .types import Comment, Review

logger = logging.getLogger(__name__)

JUDGE_MODEL = "claude-haiku-4-5-20251001"
JUDGE_PROMPT = """Two code reviewers commented on a pull request, both on the same file. Decide whether they are flagging the SAME ISSUE or DIFFERENT ISSUES.

Reviewer A (line {peer_line}):
{peer_body}

Reviewer B (line {human_line}):
{human_body}

Same issue = the underlying concern is the same, even if phrased differently or focused on slightly different lines of the same code. Different issue = they're about different things entirely (different bugs, different concerns).

Respond with exactly one word: SAME or DIFFERENT."""


@dataclass
class HumanComment:
    author: str
    path: str
    line: int
    body: str


@dataclass
class Match:
    peer_comment: dict
    human_comment: dict


@dataclass
class EvalResult:
    pr_url: str
    peer_comments: list[dict] = field(default_factory=list)
    human_comments: list[dict] = field(default_factory=list)
    matches: list[Match] = field(default_factory=list)
    peer_unmatched: list[dict] = field(default_factory=list)
    human_unmatched: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    judge_calls: int = 0

    @property
    def hit_rate(self) -> Optional[float]:
        if not self.human_comments:
            return None
        return len(self.matches) / len(self.human_comments)

    @property
    def novel_count(self) -> int:
        return len(self.peer_unmatched)


def fetch_human_comments(owner: str, repo: str, pr_number: int) -> list[HumanComment]:
    """Fetch inline review comments left by humans (excluding bots)."""
    raw = _gh_run(
        ["api", f"repos/{owner}/{repo}/pulls/{pr_number}/comments", "--paginate"]
    )
    out: list[HumanComment] = []
    for c in raw or []:
        login = ((c.get("user") or {}).get("login") or "").lower()
        if not login or "bot" in login or login.endswith("[bot]"):
            continue
        if any(t in login for t in ("coderabbit", "greptile", "qodo", "graphite", "codium")):
            continue
        path = c.get("path", "")
        line_raw = c.get("line") or c.get("original_line") or 0
        try:
            line = int(line_raw) if line_raw else 0
        except (ValueError, TypeError):
            line = 0
        body = (c.get("body") or "").strip()
        if not body or not path:
            continue
        out.append(HumanComment(author=login, path=path, line=line, body=body))
    return out


def judge_match(
    peer: Comment, human: HumanComment, client: Optional[anthropic.Anthropic] = None
) -> bool:
    """Use a cheap LLM judge to decide if peer comment matches human comment."""
    if client is None:
        client = anthropic.Anthropic()
    prompt = JUDGE_PROMPT.format(
        peer_line=peer.line, peer_body=peer.body[:1500],
        human_line=human.line, human_body=human.body[:1500],
    )
    resp = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )
    text = ""
    for block in resp.content:
        t = getattr(block, "text", None)
        if t:
            text = t.strip().upper()
            break
    return text.startswith("SAME")


def eval_pr(
    pr_url: str,
    agent: Optional[Agent] = None,
    review: Optional[Review] = None,
    client: Optional[anthropic.Anthropic] = None,
) -> EvalResult:
    """Run peer on a PR (or accept a pre-computed Review) and score against
    human reviewer comments."""
    if review is None:
        if agent is None:
            agent = Agent()
        logger.info("Running peer on %s", pr_url)
        review = agent.review(pr_url)

    owner, repo, num = parse_pr_url(pr_url)
    humans = fetch_human_comments(owner, repo, num)
    logger.info(
        "  peer: %d comments | human: %d inline reviewer comments",
        len(review.comments), len(humans),
    )

    if client is None:
        client = anthropic.Anthropic()

    matches: list[Match] = []
    matched_human_idx: set[int] = set()
    matched_peer_idx: set[int] = set()
    judge_calls = 0

    for pi, p in enumerate(review.comments):
        for hi, h in enumerate(humans):
            if hi in matched_human_idx:
                continue
            if p.path != h.path:
                continue
            judge_calls += 1
            if judge_match(p, h, client=client):
                matches.append(Match(
                    peer_comment=p.model_dump(),
                    human_comment=asdict(h),
                ))
                matched_human_idx.add(hi)
                matched_peer_idx.add(pi)
                break

    return EvalResult(
        pr_url=pr_url,
        peer_comments=[c.model_dump() for c in review.comments],
        human_comments=[asdict(h) for h in humans],
        matches=matches,
        peer_unmatched=[
            c.model_dump() for i, c in enumerate(review.comments)
            if i not in matched_peer_idx
        ],
        human_unmatched=[
            asdict(h) for i, h in enumerate(humans)
            if i not in matched_human_idx
        ],
        usage=review.usage,
        judge_calls=judge_calls,
    )


def eval_batch(
    pr_urls: list[str], agent: Optional[Agent] = None
) -> list[EvalResult]:
    if agent is None:
        agent = Agent()
    client = anthropic.Anthropic()
    return [eval_pr(u, agent=agent, client=client) for u in pr_urls]


def summarize(results: list[EvalResult]) -> dict:
    total_peer = sum(len(r.peer_comments) for r in results)
    total_human = sum(len(r.human_comments) for r in results)
    total_matches = sum(len(r.matches) for r in results)
    total_judge_calls = sum(r.judge_calls for r in results)

    prs_with_humans = [r for r in results if r.human_comments]
    per_pr_hits = [r.hit_rate for r in prs_with_humans if r.hit_rate is not None]

    return {
        "n_prs": len(results),
        "n_prs_with_human_comments": len(prs_with_humans),
        "total_peer_comments": total_peer,
        "total_human_comments": total_human,
        "total_matches": total_matches,
        "aggregate_hit_rate": total_matches / max(total_human, 1) if total_human else None,
        "mean_per_pr_hit_rate": sum(per_pr_hits) / len(per_pr_hits) if per_pr_hits else None,
        "novel_comments": sum(r.novel_count for r in results),
        "judge_calls": total_judge_calls,
    }


def save_results(results: list[EvalResult], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summarize(results),
        "results": [asdict(r) for r in results],
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="peer.eval",
        description="Score peer reviews against human reviewer comments.",
    )
    parser.add_argument("pr_urls", nargs="+", help="GitHub PR URLs to evaluate")
    parser.add_argument(
        "--model", default="claude-sonnet-4-6",
        help="Model for peer.review (default: claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--out", type=Path, default=Path("data/eval_results.json"),
        help="Where to save the eval results JSON",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    agent = Agent(model=args.model)
    client = anthropic.Anthropic()
    results: list[EvalResult] = []
    for url in args.pr_urls:
        print(f"\n=== {url} ===")
        try:
            r = eval_pr(url, agent=agent, client=client)
        except Exception as e:
            logger.error("Eval failed for %s: %s", url, e)
            continue
        results.append(r)
        hr = r.hit_rate
        hr_str = f"{hr:.0%}" if hr is not None else "n/a (no human comments)"
        print(
            f"  hit rate: {hr_str}  ({len(r.matches)}/{len(r.human_comments)} human)  |  "
            f"peer: {len(r.peer_comments)}  |  novel: {r.novel_count}  |  judge calls: {r.judge_calls}"
        )

    s = summarize(results)
    print("\n=== Aggregate ===")
    for k, v in s.items():
        if isinstance(v, float) and v is not None:
            print(f"  {k}: {v:.0%}" if "rate" in k else f"  {k}: {v:.3f}")
        else:
            print(f"  {k}: {v}")

    save_results(results, args.out)
    print(f"\nSaved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
