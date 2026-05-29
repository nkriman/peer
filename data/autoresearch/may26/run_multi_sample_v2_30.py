"""Multi-sample v2-30 experiment runner (multi-sample-v01).

Builds a narrower-context reviewer at T=0.7, wraps it in
MultiSampleReviewer(k=5), runs N=3 reruns against v2-30, then runs the
bare baseline N=3 times. Writes comparison + RecipeVerdict.

Run with: uv run python data/autoresearch/may26/run_multi_sample_v2_30.py
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
log = logging.getLogger("multi_sample_experiment")


def build_agent_with_multi_sample(k: int) -> Agent:
    """Load recipe.yaml in narrower-context mode and wrap inner reviewer with MultiSampleReviewer.

    Note: the Claude CLI (ClaudeCodeCLIReviewer) does not expose a temperature
    knob. Diversity across the K samples comes from the CLI's inherent
    run-to-run non-determinism — which we measured at ~0.06 detection_rate
    variance at the noise-floor experiment. That's enough natural sampling
    spread for the union strategy to potentially work.
    """
    recipe = Recipe.from_file(ROOT / "recipe.yaml")
    recipe.reviewer_dotted_path = None
    recipe.reviewer_kwargs = {}
    recipe.use_claude_code = True

    agent = Agent(recipe=recipe)
    inner = agent.reviewer
    agent.reviewer = MultiSampleReviewer(inner=inner, k=k)
    log.info("built agent: inner=%s, k=%d (CLI non-det provides diversity)", type(inner).__name__, k)
    return agent


async def main() -> int:
    dataset_path = ROOT / "dataset/reference/django_pydantic_v2.jsonl"
    out_dir = ROOT / "data/eval_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    samples = JSONLStorage(dataset_path).load_all()
    log.info("loaded %d samples from %s", len(samples), dataset_path.name)

    n_runs = 3
    k = 5

    # ---- Recipe phase ----
    log.info("[multi_sample] running recipe N=%d, k=%d", n_runs, k)
    agent = build_agent_with_multi_sample(k=k)
    recipe_runner = CrossRunRunner(reviewer=agent, dataset=samples, n_runs=n_runs)
    recipe_report = await recipe_runner.run_async()

    recipe_out = out_dir / "multirun_multi_sample_v2_30.json"
    recipe_out.write_text(recipe_report.model_dump_json(indent=2))
    log.info("[multi_sample] wrote recipe report → %s", recipe_out)
    print()
    print(render_multirun_summary(recipe_report))

    # ---- Baseline phase ----
    log.info("[multi_sample] running bare baseline N=%d", n_runs)
    baseline = BareClaudeCodeReviewer(model_id="sonnet")
    baseline_runner = CrossRunRunner(reviewer=baseline, dataset=samples, n_runs=n_runs)
    baseline_report = await baseline_runner.run_async()

    baseline_out = out_dir / "multirun_baseline_v2_30_multi_sample.json"
    baseline_out.write_text(baseline_report.model_dump_json(indent=2))
    log.info("[multi_sample] wrote baseline report → %s", baseline_out)

    # ---- Comparison + verdict ----
    cmp = compare_to_baseline(recipe_report, baseline_report)
    cmp_out = out_dir / "comparison_multi_sample_v2_30.json"
    cmp_out.write_text(cmp.model_dump_json(indent=2))
    print()
    print(render_comparison_summary(cmp))

    verdict = classify_comparison(cmp)
    print()
    print(render_recipe_verdict(verdict))

    # Persist a small JSON summary for the report writeup.
    summary = {
        "experiment": "multi_sample_v01 (k=5, CLI non-determinism for diversity)",
        "dataset": "django_pydantic_v2 (30 PRs)",
        "n_runs": n_runs,
        "k": k,
        "recipe_medians": {e.metric: e.recipe_median for e in cmp.per_metric},
        "baseline_medians": {e.metric: e.baseline_median for e in cmp.per_metric},
        "verdict": verdict.overall,
        "above_noise": verdict.n_above_noise,
        "in_noise": verdict.n_in_noise,
        "below_noise": verdict.n_below_noise,
    }
    summary_out = Path(__file__).parent / "multi_sample_v2_30_summary.json"
    summary_out.write_text(json.dumps(summary, indent=2))
    log.info("wrote summary → %s", summary_out)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
