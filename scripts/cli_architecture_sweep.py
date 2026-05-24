"""Architecture + code-understanding sweep on the CLI (no API spend).

Unlike `cli_pareto_sweep.py` (which only varies temperature/severity_floor/
max_comments — all sampling+filtering knobs), this sweep varies the levers
that actually change what the model sees and how it processes it:

  - codebase context depth (token budget + call-site fan-out)
  - reviewer architecture (none / draft_critique / self_filter)
  - model (sonnet vs haiku vs opus)

Each variant is a hand-crafted Recipe that mutates ONE axis from the
baseline. After the sweep, computes Pareto frontier over (DR ↑, comments ↓,
cost ↓) and writes a Markdown report.

Usage:
    unset ANTHROPIC_API_KEY  # proves zero API spend
    uv run python3 scripts/cli_architecture_sweep.py
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from peer.autoresearch.runner import run_one_iteration  # noqa: E402
from peer.recipe import Recipe  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cli_architecture_sweep")


RECIPE_PATH = ROOT / "recipe.yaml"
DATASET_PATH = ROOT / "dataset/reference/django_pydantic_v2_hard.jsonl"
LEADERBOARD_PATH = ROOT / "data/eval_runs/leaderboard.tsv"
FRONTIER_OUT = ROOT / "data/autoresearch/may24/pareto_frontier.md"
PROMPT_PATH = ROOT / "prompts/default_system_prompt.md"


# -----------------------------------------------------------------------------
# Variants: each returns (recipe, description). Recipe is written to disk
# before `run_one_iteration` loads it back.
# -----------------------------------------------------------------------------


def _base_recipe() -> Recipe:
    """Common starting point for all variants — CLI-routed, T=0."""
    return Recipe(
        model="anthropic:claude-sonnet-4-6",
        temperature=0.0,
        use_claude_code=True,
        system_prompt_path=PROMPT_PATH,
    )


def variant_baseline() -> tuple[Recipe, str]:
    return _base_recipe(), "arch[baseline: sonnet, ctx=30K, call_sites=5, no strategy]"


def variant_wider_context() -> tuple[Recipe, str]:
    r = _base_recipe()
    r.codebase_context_max_tokens = 60000
    r.codebase_context_max_call_sites_per_symbol = 15
    return r, "arch[wider context: ctx=60K, call_sites=15]"


def variant_narrower_context() -> tuple[Recipe, str]:
    r = _base_recipe()
    r.codebase_context_max_tokens = 10000
    r.codebase_context_max_call_sites_per_symbol = 2
    return r, "arch[narrower context: ctx=10K, call_sites=2]"


def variant_haiku() -> tuple[Recipe, str]:
    r = _base_recipe()
    r.model = "anthropic:claude-haiku-4-5-20251001"
    return r, "arch[model=haiku]"


def variant_opus() -> tuple[Recipe, str]:
    r = _base_recipe()
    r.model = "anthropic:claude-opus-4-7"
    return r, "arch[model=opus]"


def variant_draft_critique() -> tuple[Recipe, str]:
    r = _base_recipe()
    r.reviewer_dotted_path = "draft_critique"
    r.reviewer_kwargs = {
        "inner": "peer.reviewers.ClaudeCodeCLIReviewer",
        "critique": "peer.reviewers.ClaudeCodeCLIReviewer",
        "n_critique_rounds": 1,
    }
    return r, "arch[strategy=draft_critique (CLI inner + CLI critique)]"


def variant_self_filter() -> tuple[Recipe, str]:
    r = _base_recipe()
    r.reviewer_dotted_path = "self_filter"
    r.reviewer_kwargs = {
        "inner": "peer.reviewers.ClaudeCodeCLIReviewer",
        # inner_judge is required by SelfFilterReviewer but can't be expressed
        # as a callable in YAML — the sweep will fail and we'll see that as
        # a "crash" row, which is itself useful Pareto data.
        "min_confidence": 0.5,
    }
    return r, "arch[strategy=self_filter (CLI inner)]"


# Sweep order — fastest first so we get signal quickly.
_VARIANTS = [
    variant_baseline,
    variant_narrower_context,  # less context → faster
    variant_wider_context,
    variant_haiku,  # smaller model → faster
    variant_opus,  # bigger model → slower
    variant_draft_critique,  # 2× passes → slowest  # noqa: RUF003
    variant_self_filter,
]


def _read_leaderboard() -> list[dict]:
    """Parse the TSV into a list of dicts."""
    if not LEADERBOARD_PATH.exists():
        return []
    lines = LEADERBOARD_PATH.read_text().splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    out: list[dict] = []
    for line in lines[1:]:
        if not line:
            continue
        cells = line.split("\t")
        row: dict = {}
        for k, v in zip(header, cells, strict=False):
            if v == "n/a":
                row[k] = None
            elif k in {
                "utility",
                "detection_rate",
                "precision_minor",
                "precision_important",
                "precision_critical",
                "cost_usd",
            }:
                try:
                    row[k] = float(v)
                except ValueError:
                    row[k] = None
            elif k == "n_comments_total":
                try:
                    row[k] = int(v)
                except ValueError:
                    row[k] = None
            else:
                row[k] = v
        out.append(row)
    return out


def _compute_pareto(rows: list[dict]) -> list[dict]:
    """Non-dominated set over (DR ↑, comments ↓, cost ↓)."""

    def _strictly_better(a: dict, b: dict) -> bool:
        a_dr = a.get("detection_rate") or 0.0
        a_nc = a.get("n_comments_total") or 0
        a_co = a.get("cost_usd") or 0.0
        b_dr = b.get("detection_rate") or 0.0
        b_nc = b.get("n_comments_total") or 0
        b_co = b.get("cost_usd") or 0.0
        ge = (a_dr >= b_dr) and (a_nc <= b_nc) and (a_co <= b_co)
        gt = (a_dr > b_dr) or (a_nc < b_nc) or (a_co < b_co)
        return ge and gt

    out: list[dict] = []
    for r in rows:
        if r.get("status") != "ok":
            continue
        if any(_strictly_better(other, r) for other in rows if other is not r):
            continue
        out.append(r)
    return out


def _write_frontier_report(rows: list[dict], frontier: list[dict]) -> None:
    FRONTIER_OUT.parent.mkdir(parents=True, exist_ok=True)
    n_ok = sum(1 for r in rows if r.get("status") == "ok")
    lines: list[str] = []
    lines.append("# Pareto frontier — architecture sweep")
    lines.append("")
    lines.append("Sweep over recipe architecture (model, context depth, strategy).")
    lines.append("All runs go through the `claude` CLI; real API spend is $0 — cost values")
    lines.append("are Claude Code's *would-be* SDK billing.")
    lines.append("")
    lines.append(f"- total rows in TSV: {len(rows)}")
    lines.append(f"- successful rows: {n_ok}")
    lines.append(f"- Pareto frontier size: {len(frontier)}")
    lines.append("")
    lines.append("## Pareto-optimal recipes (DR ↑, comments ↓, cost ↓)")
    lines.append("")
    lines.append("| DR | comments | cost | description |")
    lines.append("|---:|---:|---:|---|")
    for r in sorted(frontier, key=lambda r: r.get("detection_rate") or 0, reverse=True):
        lines.append(
            f"| {(r.get('detection_rate') or 0):.4f} | "
            f"{r.get('n_comments_total')} | "
            f"${(r.get('cost_usd') or 0):.4f} | "
            f"{r.get('description', '')[:90]} |"
        )
    lines.append("")
    lines.append("## All sweep runs (sorted by detection_rate ↓)")
    lines.append("")
    lines.append("| DR | comments | cost | on frontier? | description |")
    lines.append("|---:|---:|---:|:---:|---|")
    front_keys = {(r["commit_sha"], r["recipe_hash"]) for r in frontier}
    arch_rows = [r for r in rows if (r.get("description") or "").startswith("arch[")]
    arch_sorted = sorted(arch_rows, key=lambda r: r.get("detection_rate") or 0, reverse=True)
    for r in arch_sorted:
        marker = "★" if (r["commit_sha"], r["recipe_hash"]) in front_keys else ""
        lines.append(
            f"| {(r.get('detection_rate') or 0):.4f} | "
            f"{r.get('n_comments_total')} | "
            f"${(r.get('cost_usd') or 0):.4f} | {marker} | "
            f"{r.get('description', '')[:90]} |"
        )
    FRONTIER_OUT.write_text("\n".join(lines))
    logger.info("wrote frontier report to %s", FRONTIER_OUT)


def main() -> int:
    t0 = time.monotonic()
    prior_descriptions = {row.get("description") or "" for row in _read_leaderboard()}

    for i, variant_fn in enumerate(_VARIANTS, start=1):
        recipe, desc = variant_fn()
        if desc in prior_descriptions:
            logger.info("[%d/%d] SKIP (already in leaderboard): %s", i, len(_VARIANTS), desc)
            continue

        # Write recipe.yaml so run_one_iteration can pick it up.
        RECIPE_PATH.write_text(recipe.to_yaml())
        elapsed = time.monotonic() - t0
        logger.info("[%d/%d] %s (elapsed=%.0fs)", i, len(_VARIANTS), desc, elapsed)
        try:
            row = run_one_iteration(
                recipe_path=RECIPE_PATH,
                dataset_path=DATASET_PATH,
                leaderboard_path=LEADERBOARD_PATH,
                description=desc,
                program_md_path=ROOT / "program.md",
            )
            logger.info(
                "  -> status=%s DR=%s comments=%s cost=%s",
                row.get("status"),
                row.get("detection_rate"),
                row.get("n_comments_total"),
                row.get("cost_usd"),
            )
        except Exception as e:
            logger.error("variant %s crashed: %s", desc, e)

    rows = _read_leaderboard()
    frontier = _compute_pareto(rows)
    _write_frontier_report(rows, frontier)
    logger.info(
        "DONE — total elapsed %.0fs (%.1f min); frontier=%d",
        time.monotonic() - t0,
        (time.monotonic() - t0) / 60,
        len(frontier),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
