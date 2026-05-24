"""CLI-only Pareto-frontier sweep.

Runs autoresearch iterations through the `claude` CLI (no API spend),
never discards, sweeps a grid of (temperature × severity_floor ×
max_comments_per_pr). After each iter, recipe.yaml is mutated, the iter
runs, the leaderboard accumulates a row. At the end, we compute the
non-dominated frontier over (detection_rate ↑, n_comments_total ↓,
cost_usd ↓) and write a Markdown report.

Usage:
    unset ANTHROPIC_API_KEY  # proves zero API spend
    uv run python3 scripts/cli_pareto_sweep.py [--max-iters N]
"""  # noqa: RUF002

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from peer.autoresearch.runner import run_one_iteration  # noqa: E402
from peer.recipe import Recipe  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cli_pareto_sweep")


RECIPE_PATH = ROOT / "recipe.yaml"
DATASET_PATH = ROOT / "dataset/reference/django_pydantic_v2_hard.jsonl"
LEADERBOARD_PATH = ROOT / "data/eval_runs/leaderboard.tsv"
FRONTIER_OUT = ROOT / "data/autoresearch/may24/pareto_frontier.md"

# Sweep grid. Cardinality: temp × sev_floor × max_comments = 5 × 4 × 3 = 60.  # noqa: RUF003
# Take the first N depending on --max-iters.
_TEMPERATURES = [0.0, 0.2, 0.4, 0.6, 0.8]
_SEVERITY_FLOORS: list[str | None] = [None, "nit", "minor", "important"]
_MAX_COMMENTS: list[int | None] = [None, 5, 10]


def _grid() -> list[tuple[float, str | None, int | None]]:
    """Deterministic ordering: temperature outermost (slowest), severity middle,
    max_comments innermost."""
    return list(product(_TEMPERATURES, _SEVERITY_FLOORS, _MAX_COMMENTS))


def _mutate_recipe(temperature: float, severity_floor: str | None, max_comments: int | None) -> str:
    """Mutate recipe.yaml to the next sweep point. Returns a one-line description."""
    recipe = Recipe.from_file(RECIPE_PATH)
    recipe.temperature = temperature
    recipe.use_claude_code = True
    recipe.post_processing_severity_floor = severity_floor  # type: ignore[assignment]
    recipe.post_processing_max_comments_per_pr = max_comments
    RECIPE_PATH.write_text(recipe.to_yaml())
    return f"sweep[T={temperature},sev_floor={severity_floor},max_comments={max_comments}]"


def _compute_pareto(rows: list[dict]) -> list[dict]:
    """Non-dominated set over (detection_rate ↑, n_comments_total ↓, cost_usd ↓).

    A row dominates another iff it is >= on all three (DR higher, comments
    lower, cost lower) AND strictly better on at least one. Returns rows
    that are not dominated by any other.
    """

    def _strictly_better(a: dict, b: dict) -> bool:
        a_dr = a.get("detection_rate") or 0.0
        a_nc = a.get("n_comments_total") or 0
        a_co = a.get("cost_usd") or 0.0
        b_dr = b.get("detection_rate") or 0.0
        b_nc = b.get("n_comments_total") or 0
        b_co = b.get("cost_usd") or 0.0
        # a dominates b: a is >= on all dims AND > on at least one.
        ge = (a_dr >= b_dr) and (a_nc <= b_nc) and (a_co <= b_co)
        gt = (a_dr > b_dr) or (a_nc < b_nc) or (a_co < b_co)
        return ge and gt

    frontier: list[dict] = []
    for r in rows:
        if r.get("status") != "ok":
            continue
        if any(_strictly_better(other, r) for other in rows if other is not r):
            continue
        frontier.append(r)
    return frontier


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


def _write_frontier_report(rows: list[dict], frontier: list[dict]) -> None:
    """Write the Pareto frontier report."""
    FRONTIER_OUT.parent.mkdir(parents=True, exist_ok=True)
    n_ok = sum(1 for r in rows if r.get("status") == "ok")
    lines: list[str] = []
    lines.append("# Pareto frontier — CLI-only sweep")
    lines.append("")
    lines.append(
        "All metrics are from runs through the `claude` CLI on `dataset/reference/django_pydantic_v2_hard.jsonl`."
    )
    lines.append("Cost is Claude Code's *would-be* SDK billing — real API spend was $0.")
    lines.append("")
    lines.append(f"- total rows in TSV: {len(rows)}")
    lines.append(f"- successful rows: {n_ok}")
    lines.append(f"- frontier size: {len(frontier)}")
    lines.append("")
    lines.append("## Objectives (and direction)")
    lines.append("- `detection_rate` — higher is better")
    lines.append("- `n_comments_total` — lower is better (less noise per review)")
    lines.append("- `cost_usd` — lower is better")
    lines.append("")
    lines.append("## Pareto-optimal recipes")
    lines.append("")
    lines.append("| commit | recipe | DR | comments | cost | description |")
    lines.append("|---|---|---:|---:|---:|---|")
    by_dr = sorted(frontier, key=lambda r: r.get("detection_rate") or 0, reverse=True)
    for r in by_dr:
        lines.append(
            f"| `{r['commit_sha']}` | `{r['recipe_hash']}` | "
            f"{r.get('detection_rate'):.4f} | "
            f"{r.get('n_comments_total')} | "
            f"${r.get('cost_usd'):.4f} | "
            f"{r.get('description', '')[:80]} |"
        )
    lines.append("")
    lines.append("## All successful runs (sorted by detection_rate ↓)")
    lines.append("")
    lines.append("| commit | recipe | DR | comments | cost | on frontier? | description |")
    lines.append("|---|---|---:|---:|---:|:---:|---|")
    front_keys = {(r["commit_sha"], r["recipe_hash"]) for r in frontier}
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    ok_sorted = sorted(ok_rows, key=lambda r: r.get("detection_rate") or 0, reverse=True)
    for r in ok_sorted:
        marker = "★" if (r["commit_sha"], r["recipe_hash"]) in front_keys else ""
        lines.append(
            f"| `{r['commit_sha']}` | `{r['recipe_hash']}` | "
            f"{(r.get('detection_rate') or 0):.4f} | "
            f"{r.get('n_comments_total')} | "
            f"${(r.get('cost_usd') or 0):.4f} | {marker} | "
            f"{r.get('description', '')[:80]} |"
        )
    FRONTIER_OUT.write_text("\n".join(lines))
    logger.info("wrote frontier report to %s", FRONTIER_OUT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-iters", type=int, default=60, help="cap on sweep iterations")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip sweep points whose (T,sev,maxc) signature already appears in the TSV by description.",
    )
    args = parser.parse_args()

    grid = _grid()
    logger.info("sweep grid has %d points; running up to %d iters", len(grid), args.max_iters)

    # Build the "already done" signature set to avoid re-running.
    prior_descriptions: set[str] = set()
    for row in _read_leaderboard():
        d = row.get("description") or ""
        if d.startswith("sweep["):
            prior_descriptions.add(d.split("]")[0] + "]")

    n_run = 0
    n_skipped = 0
    t0 = time.monotonic()
    for temp, sev, maxc in grid:
        if n_run >= args.max_iters:
            logger.info("reached --max-iters=%d; stopping", args.max_iters)
            break
        sig = f"sweep[T={temp},sev_floor={sev},max_comments={maxc}]"
        if args.skip_existing and sig in prior_descriptions:
            n_skipped += 1
            continue
        desc = _mutate_recipe(temp, sev, maxc)
        elapsed = time.monotonic() - t0
        logger.info(
            "[iter %d / target %d] %s (elapsed=%.0fs)",
            n_run + 1,
            args.max_iters,
            desc,
            elapsed,
        )
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
            logger.error("iter %d crashed: %s", n_run + 1, e)
        n_run += 1

    # Pareto extraction at the end.
    rows = _read_leaderboard()
    frontier = _compute_pareto(rows)
    _write_frontier_report(rows, frontier)
    logger.info(
        "DONE — ran %d new iters, skipped %d, total elapsed %.0fs, frontier=%d",
        n_run,
        n_skipped,
        time.monotonic() - t0,
        len(frontier),
    )
    # Dump JSON next to MD for downstream tooling
    json_out = FRONTIER_OUT.with_suffix(".json")
    json_out.write_text(json.dumps({"frontier": frontier, "n_total": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
