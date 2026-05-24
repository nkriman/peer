"""Run two experiments back-to-back, both via the CLI (no API spend):

1. Blame run: narrower-context recipe + include_git_history=true.
   Does adding git-blame as a prompt section lift detection_rate?

2. Cross-judge run: narrower-context recipe (no blame), re-judged across
   sonnet/haiku/opus via the cross-judge utility. Reports the variance
   band so we know the noise floor of our published DR numbers.

Both write to the standard leaderboard / report locations. After both
complete, prints a summary section comparing:
   - blame on/off DR delta
   - DR variance across judges
"""  # noqa: RUF002

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from peer.autoresearch.runner import run_one_iteration  # noqa: E402
from peer.recipe import Recipe  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cli_blame_and_xjudge")


RECIPE_PATH = ROOT / "recipe.yaml"
DATASET_PATH = ROOT / "dataset/reference/django_pydantic_v2_hard.jsonl"
LEADERBOARD_PATH = ROOT / "data/eval_runs/leaderboard.tsv"
PROMPT_PATH = ROOT / "prompts/default_system_prompt.md"
XJUDGE_OUT = ROOT / "data/eval_runs/cross_judge_narrower.json"
SUMMARY_OUT = ROOT / "data/autoresearch/may24/blame_and_xjudge_findings.md"


def _narrower_recipe(include_git_history: bool) -> Recipe:
    return Recipe(
        model="anthropic:claude-sonnet-4-6",
        temperature=0.0,
        use_claude_code=True,
        system_prompt_path=PROMPT_PATH,
        codebase_context_max_tokens=10000,
        codebase_context_max_call_sites_per_symbol=2,
        include_git_history=include_git_history,
    )


# ---------------------------------------------------------------------------
# Phase 1: blame on/off comparison
# ---------------------------------------------------------------------------


def run_blame_experiment() -> dict:
    """Run one autoresearch iter with include_git_history=True. Compare to
    the existing narrower-context row from the prior arch sweep."""
    os.environ["PEER_USE_CLAUDE_CODE"] = "1"

    recipe = _narrower_recipe(include_git_history=True)
    RECIPE_PATH.write_text(recipe.to_yaml())
    logger.info("Phase 1: blame ON (narrower context, include_git_history=true)")
    t0 = time.monotonic()
    row = run_one_iteration(
        recipe_path=RECIPE_PATH,
        dataset_path=DATASET_PATH,
        leaderboard_path=LEADERBOARD_PATH,
        description="arch[narrower context + git_blame]",
        program_md_path=ROOT / "program.md",
    )
    elapsed = time.monotonic() - t0
    logger.info(
        "Phase 1 done in %.0fs: DR=%s comments=%s cost=%s",
        elapsed,
        row.get("detection_rate"),
        row.get("n_comments_total"),
        row.get("cost_usd"),
    )
    return row


# ---------------------------------------------------------------------------
# Phase 2: cross-judge on narrower-context (no blame)
# ---------------------------------------------------------------------------


def run_xjudge_experiment() -> Any:
    """Re-judge cached reviews against sonnet, haiku, opus."""
    os.environ["PEER_USE_CLAUDE_CODE"] = "1"

    # Reset recipe to narrower-context without blame for cross-judge — we
    # want to characterize the noise on the current frontier point.
    recipe = _narrower_recipe(include_git_history=False)
    RECIPE_PATH.write_text(recipe.to_yaml())

    from peer.agent import Agent
    from peer.dataset import JSONLStorage
    from peer.eval import CrossJudgeRunner, render_cross_judge_summary

    samples = JSONLStorage(DATASET_PATH).load_all()
    agent = Agent(recipe=recipe)
    logger.info(
        "Phase 2: cross-judge (narrower context, no blame) across sonnet/haiku/opus"
    )
    t0 = time.monotonic()
    runner = CrossJudgeRunner(
        reviewer=agent,
        dataset=samples,
        judge_models=["sonnet", "haiku", "opus"],
        concurrency=5,
    )
    report = runner.run()
    elapsed = time.monotonic() - t0

    XJUDGE_OUT.parent.mkdir(parents=True, exist_ok=True)
    XJUDGE_OUT.write_text(report.model_dump_json(indent=2))
    logger.info("Phase 2 done in %.0fs; report at %s", elapsed, XJUDGE_OUT)
    print(render_cross_judge_summary(report))
    return report


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def write_summary(blame_row: dict, xjudge_report: Any) -> None:
    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    blame_dr = blame_row.get("detection_rate")
    # Compare to the existing narrower-context row (DR=0.0980 per the arch sweep).
    narrower_dr = 0.0980
    blame_delta = (blame_dr or 0.0) - narrower_dr

    dr_band = xjudge_report.metric_bands.get("detection_rate")
    detection_min = dr_band.min if dr_band else None
    detection_max = dr_band.max if dr_band else None
    detection_median = dr_band.median if dr_band else None
    detection_range = dr_band.range if dr_band else None

    lines: list[str] = []
    lines.append("# Findings: blame enricher + cross-judge variance")
    lines.append("")
    lines.append("Both experiments run via the `claude` CLI on the hard subset")
    lines.append("(`dataset/reference/django_pydantic_v2_hard.jsonl`, 7 PRs / 51 gold defects).")
    lines.append("Zero API spend — all calls subscription-routed.")
    lines.append("")
    lines.append("## Phase 1: does git-blame as context lift detection?")
    lines.append("")
    lines.append("Comparison against the prior narrower-context frontier point (DR=0.0980).")
    lines.append("")
    lines.append("| variant | DR | n_comments | cost |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| narrower context (no blame, prior) | 0.0980 | 29 | $0.83 |")
    lines.append(
        f"| narrower context + git_blame | "
        f"{(blame_dr or 0.0):.4f} | "
        f"{blame_row.get('n_comments_total')} | "
        f"${(blame_row.get('cost_usd') or 0.0):.4f} |"
    )
    lines.append("")
    if blame_delta > 0.01:
        verdict = f"**Blame LIFTS detection by {blame_delta:+.4f}.** Worth enabling by default."
    elif blame_delta < -0.01:
        verdict = (
            f"**Blame HURTS detection by {blame_delta:+.4f}.** Don't enable by default; revisit "
            "the rendering or scope of the section."
        )
    else:
        verdict = (
            f"**Blame is neutral on detection ({blame_delta:+.4f}).** Below the judge-variance "
            "noise floor (see Phase 2). Inconclusive."
        )
    lines.append(verdict)
    lines.append("")
    lines.append("## Phase 2: how noisy is the cross-judge measurement?")
    lines.append("")
    if dr_band:
        lines.append(f"- DR min: {detection_min:.4f}")
        lines.append(f"- DR median: {detection_median:.4f}")
        lines.append(f"- DR max: {detection_max:.4f}")
        lines.append(f"- DR range: {detection_range:.4f}")
        lines.append(f"- n judges: {dr_band.n_judges_included}")
        lines.append("")
        if detection_min and detection_min > 0 and detection_max / detection_min >= 2.0:
            lines.append(
                f"**⚠️ HIGH VARIANCE**: {detection_max / detection_min:.1f}× spread across judges. "
                "Published DR numbers must include bands; point estimates from a single judge are misleading."
            )
        else:
            lines.append(
                "Judge variance is below the 2× threshold. Point estimates are reasonable but "
                "should still cite the judge model."
            )
    else:
        lines.append("(no detection_rate band — cross-judge didn't compute it)")
    lines.append("")
    lines.append("## Implications")
    lines.append("")
    lines.append(
        f"1. The blame delta ({blame_delta:+.4f}) must be interpreted against the "
        f"cross-judge variance band (range {detection_range:.4f} if non-None). If the blame "
        "delta is smaller than the variance range, it's noise."
    )
    lines.append("")
    lines.append(
        "2. Whatever the next defaults are, they should be expressed with cross-judge bands, "
        "not point estimates. The `peer eval --cross-judge` workflow is now first-class."
    )
    SUMMARY_OUT.write_text("\n".join(lines))
    logger.info("Summary written to %s", SUMMARY_OUT)


def main() -> int:
    if os.environ.get("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY is set — unsetting for this run to prove zero API spend")
        del os.environ["ANTHROPIC_API_KEY"]

    blame_row = run_blame_experiment()
    xjudge_report = run_xjudge_experiment()
    write_summary(blame_row, xjudge_report)
    return 0


if __name__ == "__main__":
    from typing import Any  # noqa: F401  (used by run_xjudge_experiment's annotation)

    raise SystemExit(main())
