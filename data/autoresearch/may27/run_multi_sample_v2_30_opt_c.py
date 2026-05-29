"""Multi-sample v2-30 PAIRED Option C: N=1 K=3 (peer-eby, quota-mindful).

Scope cut to respect Max 20x quota (~120 CLI calls + judge API spend):
  * 30 PRs, but only K=3 samples per PR (vs original K=5)
  * N=1 run per arm (vs original N=5)
  * Paired (recipe + baseline see same 30 PRs at same commit)
  * Verdict: per-PR PAIRED BOOTSTRAP CI (not run-level CI). With n=30
    paired diffs the CI is much tighter than the run-level bootstrap
    on N=3-5 medians could ever be.

Outputs (under data/eval_runs/):
  multirun_multi_sample_v2_30_optc.json
  multirun_baseline_v2_30_optc_paired.json
  comparison_multi_sample_v2_30_optc_paired_bootstrap.json

Run with: nohup uv run python data/autoresearch/may27/run_multi_sample_v2_30_opt_c.py \
    > /tmp/multi_sample_optc.log 2>&1 &
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
    compare_to_baseline_paired_bootstrap,
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
log = logging.getLogger("multi_sample_optc")


def build_agent_with_multi_sample(k: int) -> Agent:
    recipe = Recipe.from_file(ROOT / "recipe.yaml")
    recipe.reviewer_dotted_path = None
    recipe.reviewer_kwargs = {}
    recipe.use_claude_code = True
    agent = Agent(recipe=recipe)
    inner = agent.reviewer
    agent.reviewer = MultiSampleReviewer(inner=inner, k=k)
    log.info("built agent: inner=%s k=%d", type(inner).__name__, k)
    return agent


async def main() -> int:
    dataset_path = ROOT / "dataset/reference/django_pydantic_v2.jsonl"
    out_dir = ROOT / "data/eval_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    samples = JSONLStorage(dataset_path).load_all()
    log.info("loaded %d samples from %s", len(samples), dataset_path.name)

    n_runs = 1
    k = 3

    # ---- Recipe phase ----
    log.info("[opt-c] recipe N=%d k=%d", n_runs, k)
    agent = build_agent_with_multi_sample(k=k)
    recipe_runner = CrossRunRunner(reviewer=agent, dataset=samples, n_runs=n_runs)
    recipe_report = await recipe_runner.run_async()
    recipe_out = out_dir / "multirun_multi_sample_v2_30_optc.json"
    recipe_out.write_text(recipe_report.model_dump_json(indent=2))
    log.info("[opt-c] wrote recipe report → %s", recipe_out)
    print()
    print(render_multirun_summary(recipe_report))

    # ---- Baseline phase (fail-loud on infra errors) ----
    log.info("[opt-c] baseline N=%d", n_runs)
    baseline = BareClaudeCodeReviewer(model_id="sonnet")
    baseline_runner = CrossRunRunner(reviewer=baseline, dataset=samples, n_runs=n_runs)
    baseline_report = await baseline_runner.run_async()
    baseline_out = out_dir / "multirun_baseline_v2_30_optc_paired.json"
    baseline_out.write_text(baseline_report.model_dump_json(indent=2))
    log.info("[opt-c] wrote baseline report → %s", baseline_out)

    # Sanity check: how many baseline samples actually succeeded?
    base_per_sample = baseline_report.per_run[0].per_sample
    n_baseline_ok = sum(1 for s in base_per_sample if s.error is None)
    n_baseline_err = sum(1 for s in base_per_sample if s.error is not None)
    log.info("[opt-c] baseline samples: %d ok / %d errored", n_baseline_ok, n_baseline_err)
    if n_baseline_ok < 5:
        log.warning(
            "[opt-c] baseline produced <5 usable samples — verdict will be unreliable. "
            "Inspect baseline errors in the JSON before drawing conclusions."
        )

    # ---- Comparison (floor-based for continuity + paired bootstrap for verdict) ----
    cmp_floor = compare_to_baseline(recipe_report, baseline_report)
    print()
    print("# Floor-based summary (polarity-corrected)")
    print(render_comparison_summary(cmp_floor))

    cmp_paired = compare_to_baseline_paired_bootstrap(
        recipe_report, baseline_report, n_resamples=2000, seed=0
    )
    paired_out = out_dir / "comparison_multi_sample_v2_30_optc_paired_bootstrap.json"
    paired_out.write_text(cmp_paired.model_dump_json(indent=2))
    print()
    print("# Per-PR paired bootstrap CI (load-bearing)")
    print(render_comparison_summary(cmp_paired))
    v_paired = classify_comparison(cmp_paired)
    print()
    print(render_recipe_verdict(v_paired))

    # Final summary persisted for the writeup.
    summary = {
        "experiment": "multi_sample_v01 Option C paired (peer-eby)",
        "dataset": "django_pydantic_v2 (30 PRs)",
        "n_runs": n_runs,
        "k": k,
        "fixes_applied": ["peer-7op", "peer-8w1", "peer-4dn"],
        "baseline_samples_ok": n_baseline_ok,
        "baseline_samples_errored": n_baseline_err,
        "recipe_medians": {e.metric: e.recipe_median for e in cmp_paired.per_metric},
        "baseline_medians": {e.metric: e.baseline_median for e in cmp_paired.per_metric},
        "paired_bootstrap_verdict": {
            "overall": v_paired.overall,
            "above": v_paired.n_above_noise,
            "in": v_paired.n_in_noise,
            "below": v_paired.n_below_noise,
            "per_metric": {
                e.metric: {
                    "delta": e.delta,
                    "ci_lower": e.ci_lower,
                    "ci_upper": e.ci_upper,
                    "verdict": e.verdict,
                    "method": e.ci_method,
                }
                for e in cmp_paired.per_metric
            },
        },
    }
    summary_out = Path(__file__).parent / "multi_sample_v2_30_optc_summary.json"
    summary_out.write_text(json.dumps(summary, indent=2))
    log.info("wrote summary → %s", summary_out)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
