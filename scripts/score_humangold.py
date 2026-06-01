"""Score reviewers on the human-gold benchmark (peer-2sw, pilot first).

Runs peer (Agent) + the bare-Claude baseline over the kubernetes human-gold
dataset (peer-e94) through EvalRunner — the core falsifiability test: does
peer's full pipeline beat the 5-line diff-only baseline on real human-found
defects?

Both reviewers route through the Claude Code subscription (claude-code:sonnet /
BareClaudeCodeReviewer model_id=sonnet), $0 marginal cost. Judge (DetectionRate
etc.) also goes through the subscription via make_client(). Sequential
(concurrency=1) per the user's instruction.

--limit N : pilot on the first N PRs (validate the path + directional number)
            before the full run.

Run (subscription):
  PEER_USE_CLAUDE_CODE=1 uv run python scripts/score_humangold.py --limit 8
  PEER_USE_CLAUDE_CODE=1 uv run python scripts/score_humangold.py        # full
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from peer.agent import Agent
from peer.baselines import BareClaudeCodeReviewer
from peer.dataset.storage import JSONLStorage
from peer.eval.runner import EvalRunner

DATASET = Path("dataset/reference/benchmark_humangold.jsonl")
OUT_DIR = Path("data/eval_runs")


def _run(name: str, reviewer, dataset, dataset_path: str) -> dict:
    print(f"\n========== {name} ==========")
    runner = EvalRunner(
        reviewer=reviewer,
        dataset=dataset,
        dataset_path=dataset_path,
        concurrency=1,  # sequential
    )
    report = runner.run()
    s = report.summary
    dr = s.metric_values.get("detection_rate")
    cpp = s.metric_values.get("comments_per_pr")
    print(f"  detection_rate: {dr}")
    print(f"  comments_per_pr: {cpp}")
    print(f"  samples ok/failed: {s.n_samples_succeeded}/{s.n_samples_failed}")
    dd = s.metric_details.get("detection_rate", {})
    print(f"  matches/gold: {dd.get('total_matches')}/{dd.get('total_gold')}")
    return {
        "reviewer": name,
        "detection_rate": dr,
        "comments_per_pr": cpp,
        "n_ok": s.n_samples_succeeded,
        "n_failed": s.n_samples_failed,
        "detection_detail": dd,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="pilot on first N PRs (0 = all)")
    args = ap.parse_args()

    dataset = JSONLStorage(DATASET).load_all()
    if args.limit:
        dataset = dataset[: args.limit]
    print(f"Scoring on {len(dataset)} human-gold PRs (kubernetes)")

    results = []
    results.append(
        _run("peer (claude-code:sonnet)", Agent(model="claude-code:sonnet"), dataset, str(DATASET))
    )
    results.append(
        _run(
            "bare-claude baseline", BareClaudeCodeReviewer(model_id="sonnet"), dataset, str(DATASET)
        )
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = f"humangold_{'pilot' + str(args.limit) if args.limit else 'full'}"
    out = OUT_DIR / f"score_{tag}.json"
    out.write_text(json.dumps(results, indent=2))

    print("\n========== HEAD-TO-HEAD ==========")
    for r in results:
        print(f"  {r['reviewer']:<32} DR={r['detection_rate']}  comments/PR={r['comments_per_pr']}")
    print(f"\nwrote {out}")
    print("NOTE: this is peer vs baseline only. Commercial tools (CodeRabbit/Qodo)")
    print("come via peer-frr replay. Detection-rate gaps need BCa+permutation")
    print("(compare.py) on paired per-PR values for a real verdict — pilot is directional.")


if __name__ == "__main__":
    main()
