"""Run peer eval against the v2 dataset with per-repo team_conventions
injected into the Agent's system prompt.

Compares against the v2 baseline (no conventions) to measure whether
team-style context lifts recall.

Conventions docs come from dataset/reference/conventions/<repo>.md and
are derived ONLY from public sources (Django coding-style docs, Pydantic
CONTRIBUTING) — never from the dataset PRs themselves.

Run: .venv/bin/python scripts/eval_with_conventions.py
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

from peer.agent import Agent
from peer.dataset import JSONLStorage
from peer.eval import EvalReport, EvalRunner, render_diff, render_summary
from peer.types import Review

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

CONVENTIONS_DIR = Path("dataset/reference/conventions")
DATASET = Path("dataset/reference/django_pydantic_v2.jsonl")
BASELINE = Path("data/eval_runs/reference_v2_sonnet46.json")
OUT = Path("data/eval_runs/reference_v2_sonnet46_with_conventions.json")


class RepoAwareAgent:
    """Reviewer-like that picks the right Agent (and conventions) per repo.

    Caches Agent instances by repo so we don't reconstruct on every review.
    """

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self.model = model
        self._agents: dict[str, Agent] = {}

    def _repo_key(self, pr_url: str) -> str | None:
        m = re.match(r"https?://github\.com/[^/]+/([^/]+)/", pr_url)
        return m.group(1) if m else None

    def _agent_for(self, pr_url: str) -> Agent:
        repo = self._repo_key(pr_url)
        if repo not in self._agents:
            kwargs: dict = {"model": self.model}
            if repo:
                conv = CONVENTIONS_DIR / f"{repo}.md"
                if conv.exists():
                    kwargs["team_conventions_file"] = conv
                    print(f"  [conventions] {repo} -> {conv}")
                else:
                    print(f"  [conventions] {repo} -> (none — no {conv})")
            self._agents[repo] = Agent(**kwargs)
        return self._agents[repo]

    def review(self, pr_url: str) -> Review:
        return self._agent_for(pr_url).review(pr_url)


def main() -> int:
    if not DATASET.exists():
        print(f"Dataset not found: {DATASET}", file=sys.stderr)
        return 1
    if not BASELINE.exists():
        print(f"Baseline not found: {BASELINE} (run plain `peer eval` first)", file=sys.stderr)
        return 1

    samples = JSONLStorage(DATASET).load_all()
    print(f"Loaded {len(samples)} samples from {DATASET}")
    print(f"Conventions dir: {CONVENTIONS_DIR}")
    for p in sorted(CONVENTIONS_DIR.glob("*.md")):
        print(f"  - {p.name} ({p.stat().st_size} bytes)")

    reviewer = RepoAwareAgent(model="claude-sonnet-4-6")
    runner = EvalRunner(
        reviewer=reviewer,
        dataset=samples,
        dataset_path=str(DATASET),
    )

    print("\nRunning eval...")
    report = runner.run()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    report.to_json(OUT)
    print(render_summary(report))
    print(f"\nReport saved to {OUT}")

    baseline = EvalReport.from_json(BASELINE)
    print("\n=== A/B diff vs baseline (v2, no conventions) ===")
    print(render_diff(baseline, report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
