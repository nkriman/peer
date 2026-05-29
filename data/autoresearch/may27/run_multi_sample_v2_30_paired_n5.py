"""Multi-sample v2-30 PAIRED re-run (N=5, K=5) — peer-eby.

Re-run after peer-7op (baseline raise-on-error + retry) and
peer-8w1 / peer-4dn (polarity-corrected compare + bootstrap CI).

What's different from the may26 run:
  - N=5 recipe runs AND N=5 baseline runs at the same commit, same script.
  - BareClaudeCodeReviewer now raises on `gh pr diff` failures and on
    zero-token claude calls — collapses won't silently corrupt medians.
  - Verdict uses both the polarity-corrected floor gate AND the bootstrap
    CI gate. The CI verdict is the load-bearing one; the floor is shown
    for continuity with prior reports.

Outputs (under data/eval_runs/):
  multirun_multi_sample_v2_30_n5.json
  multirun_baseline_v2_30_n5_paired.json
  comparison_multi_sample_v2_30_n5_paired_floor.json
  comparison_multi_sample_v2_30_n5_paired_ci.json

Run with: nohup uv run python data/autoresearch/may27/run_multi_sample_v2_30_paired_n5.py \
    > /tmp/multi_sample_n5_paired.log 2>&1 &
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("PEER_USE_CLAUDE_CODE", "1")

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from peer.agent import Agent  # noqa: E402
from peer.baselines import BareClaudeCodeReviewer  # noqa: E402
from peer.dataset import JSONLStorage  # noqa: E402
from peer.eval import (  # noqa: E402
    CrossRunRunner,
    classify_comparison,
    compare_to_baseline,
    compare_to_baseline_ci,
    render_comparison_summary,
    render_multirun_summary,
    render_recipe_verdict,
)
from peer.recipe import Recipe  # noqa: E402
from peer.strategies import MultiSampleReviewer  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("multi_sample_n5_paired")


def build_agent_with_multi_sample(k: int) -> Agent:
    """Narrower-context inner reviewer wrapped in MultiSampleReviewer(k).

    Diversity across the K samples comes from CLI run-to-run non-determinism
    (~0.06 dr variance measured in the noise-floor experiment).
    """
    recipe = Recipe.from_file(ROOT / "recipe.yaml")
    recipe.reviewer_dotted_path = None
    recipe.reviewer_kwargs = {}
    recipe.use_claude_code = True
    agent = Agent(recipe=recipe)
    inner = agent.reviewer
    agent.reviewer = MultiSampleReviewer(inner=inner, k=k)
    log.info("built agent: inner=%s k=%d (CLI non-det provides diversity)", type(inner).__name__, k)
    return agent


async def main() -> int:
    dataset_path = ROOT / "dataset/reference/django_pydantic_v2.jsonl"
    out_dir = ROOT / "data/eval_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    samples = JSONLStorage(dataset_path).load_all()
    log.info("loaded %d samples from %s", len(samples), dataset_path.name)

    n_runs = 5
    k = 5

    # ---- Recipe phase ----
    log.info("[multi_sample] recipe N=%d k=%d", n_runs, k)
    agent = build_agent_with_multi_sample(k=k)
    recipe_runner = CrossRunRunner(reviewer=agent, dataset=samples, n_runs=n_runs)
    recipe_report = await recipe_runner.run_async()
    recipe_out = out_dir / "multirun_multi_sample_v2_30_n5.json"
    recipe_out.write_text(recipe_report.model_dump_json(indent=2))
    log.info("[multi_sample] wrote recipe report → %s", recipe_out)
    print()
    print(render_multirun_summary(recipe_report))

    # ---- Baseline phase ----
    log.info("[multi_sample] baseline N=%d", n_runs)
    baseline = BareClaudeCodeReviewer(model_id="sonnet")
    baseline_runner = CrossRunRunner(reviewer=baseline, dataset=samples, n_runs=n_runs)
    baseline_report = await baseline_runner.run_async()
    baseline_out = out_dir / "multirun_baseline_v2_30_n5_paired.json"
    baseline_out.write_text(baseline_report.model_dump_json(indent=2))
    log.info("[multi_sample] wrote baseline report → %s", baseline_out)

    # ---- Comparison (floor + CI) ----
    cmp_floor = compare_to_baseline(recipe_report, baseline_report)
    (out_dir / "comparison_multi_sample_v2_30_n5_paired_floor.json").write_text(
        cmp_floor.model_dump_json(indent=2)
    )
    print()
    print("# Floor-based verdict (polarity-corrected)")
    print(render_comparison_summary(cmp_floor))
    print()
    print(render_recipe_verdict(classify_comparison(cmp_floor)))

    cmp_ci = compare_to_baseline_ci(recipe_report, baseline_report, n_resamples=2000, seed=0)
    (out_dir / "comparison_multi_sample_v2_30_n5_paired_ci.json").write_text(
        cmp_ci.model_dump_json(indent=2)
    )
    print()
    print("# Bootstrap CI verdict (load-bearing)")
    print(render_comparison_summary(cmp_ci))
    print()
    print(render_recipe_verdict(classify_comparison(cmp_ci)))

    v_floor = classify_comparison(cmp_floor)
    v_ci = classify_comparison(cmp_ci)
    summary = {
        "experiment": "multi_sample_v01 PAIRED re-run (peer-eby)",
        "dataset": "django_pydantic_v2 (30 PRs)",
        "n_runs": n_runs,
        "k": k,
        "fixes_applied": ["peer-7op", "peer-8w1", "peer-4dn"],
        "recipe_medians": {e.metric: e.recipe_median for e in cmp_floor.per_metric},
        "baseline_medians": {e.metric: e.baseline_median for e in cmp_floor.per_metric},
        "floor_verdict": {
            "overall": v_floor.overall,
            "above": v_floor.n_above_noise,
            "in": v_floor.n_in_noise,
            "below": v_floor.n_below_noise,
        },
        "ci_verdict": {
            "overall": v_ci.overall,
            "above": v_ci.n_above_noise,
            "in": v_ci.n_in_noise,
            "below": v_ci.n_below_noise,
            "per_metric_ci": {
                e.metric: {
                    "delta": e.delta,
                    "ci_lower": e.ci_lower,
                    "ci_upper": e.ci_upper,
                    "verdict": e.verdict,
                }
                for e in cmp_ci.per_metric
            },
        },
    }
    summary_out = Path(__file__).parent / "multi_sample_v2_30_n5_paired_summary.json"
    summary_out.write_text(json.dumps(summary, indent=2))
    log.info("wrote summary → %s", summary_out)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
