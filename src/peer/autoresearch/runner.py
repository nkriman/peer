"""`peer autoresearch run` — one iteration; one TSV row.

Loads a Recipe, builds an Agent + EvalRunner, runs the eval, computes
utility from program.md (or falls back), appends a leaderboard row.
Catches everything: a crash still produces a row with status=crash so
the loop has a forensic trail.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from ..agent import Agent
from ..dataset import JSONLStorage
from ..eval import EvalRunner
from ..recipe import Recipe
from .leaderboard import append_row
from .utility import parse_utility_formula

logger = logging.getLogger(__name__)


def _append_row(path: Path, row: dict[str, Any]) -> None:
    """Type-erased wrapper around append_row so the mypy-typed kwargs above
    don't fight the dict-spread."""
    append_row(
        path,
        commit_sha=row["commit_sha"],
        recipe_hash=row["recipe_hash"],
        utility=row.get("utility"),
        detection_rate=row.get("detection_rate"),
        precision_minor=row.get("precision_minor"),
        precision_important=row.get("precision_important"),
        precision_critical=row.get("precision_critical"),
        cost_usd=row.get("cost_usd"),
        n_comments_total=row.get("n_comments_total"),
        status=row["status"],
        description=row["description"],
    )


def _current_commit_sha(default: str = "uncommitted") -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        sha = out.stdout.strip()
        return sha or default
    except Exception:
        return default


def _read_program_md(path: Path | str = "program.md") -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    return p.read_text()


def _extract_precision_per_severity(report: Any) -> dict[str, float | None]:
    """Extract per-severity precision from the EvalReport's metric_details."""
    details = (report.summary.metric_details or {}).get("precision_per_severity") or {}
    out: dict[str, float | None] = {"minor": None, "important": None, "critical": None}
    for sev in out:
        entry = details.get(sev) or {}
        if isinstance(entry, dict):
            v = entry.get("precision")
            if isinstance(v, (int, float)):
                out[sev] = float(v)
    return out


def _sum_n_comments(report: Any) -> int:
    total = 0
    for s in report.per_sample:
        rs = s.review_summary or {}
        n = rs.get("n_comments")
        if isinstance(n, int):
            total += n
    return total


def run_one_iteration(
    recipe_path: Path | str,
    dataset_path: Path | str,
    leaderboard_path: Path | str,
    description: str = "",
    program_md_path: Path | str = "program.md",
    report_out: Path | str | None = None,
) -> dict[str, Any]:
    """Run one autoresearch iteration. Returns the row dict that was appended.

    Catches all exceptions during recipe load / Agent construction / eval
    and still writes a crash row. The returned dict carries `status`
    (`"ok"` or `"crash"`) and `utility`. The CLI uses this to decide the
    exit code.
    """
    leaderboard_path = Path(leaderboard_path)
    commit_sha = _current_commit_sha()
    utility_fn = parse_utility_formula(_read_program_md(program_md_path))

    try:
        recipe = Recipe.from_file(recipe_path)
        recipe_hash = recipe.canonical_hash()
    except Exception as e:
        logger.warning("recipe load failed: %s", e)
        row: dict[str, Any] = {
            "commit_sha": commit_sha,
            "recipe_hash": "loadfail",
            "utility": None,
            "detection_rate": None,
            "precision_minor": None,
            "precision_important": None,
            "precision_critical": None,
            "cost_usd": None,
            "n_comments_total": None,
            "status": "crash",
            "description": f"{description} | recipe load: {type(e).__name__}: {e}",
        }
        _append_row(leaderboard_path, row)
        return row

    try:
        samples = JSONLStorage(Path(dataset_path)).load_all()
        agent = Agent(recipe=recipe)
        runner = EvalRunner(reviewer=agent, dataset=samples, concurrency=5)
        report = runner.run()
    except Exception as e:
        logger.warning("eval failed: %s", e)
        row = {
            "commit_sha": commit_sha,
            "recipe_hash": recipe_hash,
            "utility": None,
            "detection_rate": None,
            "precision_minor": None,
            "precision_important": None,
            "precision_critical": None,
            "cost_usd": None,
            "n_comments_total": None,
            "status": "crash",
            "description": f"{description} | eval: {type(e).__name__}: {e}",
        }
        _append_row(leaderboard_path, row)
        return row

    # Persist the EvalReport so `peer autoresearch diagnose` (or the loop's
    # post-iter hypothesis writer) can find this iteration's failure modes.
    out_path = (
        Path(report_out)
        if report_out
        else (Path("data/eval_runs") / f"autoresearch_{recipe_hash}_{commit_sha}.json")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.model_dump_json(indent=2))

    metric_values = report.summary.metric_values or {}
    detection = metric_values.get("detection_rate")
    sev = _extract_precision_per_severity(report)
    n_comments_total = _sum_n_comments(report)
    metrics_dict: dict[str, float | int | None] = {
        "detection_rate": detection,
        "precision_minor": sev["minor"],
        "precision_important": sev["important"],
        "precision_critical": sev["critical"],
        "cost_usd": report.summary.cost_usd_total,
        "cost_usd_total": report.summary.cost_usd_total,
        "n_comments_total": n_comments_total,
        "dataset_size": len(report.per_sample),
        "suggestion_rate": metric_values.get("suggestion_rate"),
    }
    utility = utility_fn(metrics_dict)

    row = {
        "commit_sha": commit_sha,
        "recipe_hash": recipe_hash,
        "utility": utility,
        "detection_rate": detection,
        "precision_minor": sev["minor"],
        "precision_important": sev["important"],
        "precision_critical": sev["critical"],
        "cost_usd": report.summary.cost_usd_total,
        "n_comments_total": n_comments_total,
        "status": "ok",
        "description": description or "(no description)",
    }
    _append_row(leaderboard_path, row)
    # Surface a quick console summary.
    logger.info(
        "autoresearch run: utility=%s detection_rate=%s cost=%s comments=%s",
        utility,
        detection,
        report.summary.cost_usd_total,
        n_comments_total,
    )
    return row
