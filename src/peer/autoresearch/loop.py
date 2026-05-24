"""`peer autoresearch loop` — autonomous iteration engine.

LOOP semantics (from program.md):
    1. Run baseline (current recipe), record best_utility.
    2. Repeat:
       a. Call mutator hook (default no-op — assume an external agent
          edits recipe.yaml + prompts/ between iterations).
       b. Run one eval iteration.
       c. If iteration_utility > best_utility: git-commit recipe+prompts,
          update best_utility.
       d. Else: git reset --hard to drop the failed mutation.
       e. Write a hypothesis markdown for this iteration; mirror to
          `current_hypothesis.md`.
       f. Halt on --max-iters or --budget-usd.
"""

from __future__ import annotations

import importlib
import logging
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .diagnose import diagnose_report
from .runner import run_one_iteration

logger = logging.getLogger(__name__)


Mutator = Callable[[], str]  # returns a one-line description of what it changed


def no_op_mutator() -> str:
    """Default mutator. Assumes the human-driven agent edits recipe.yaml
    + prompts/ files between loop iterations outside this process. Returns
    an empty description so the iteration prints '(no description)'."""
    return ""


def _resolve_mutator(dotted_path: str | None) -> Mutator:
    if dotted_path is None or dotted_path == "no_op":
        return no_op_mutator
    if "." not in dotted_path:
        raise ValueError(f"--mutator must be 'no_op' or a dotted import path; got {dotted_path!r}")
    module_path, attr = dotted_path.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    fn = getattr(mod, attr)
    if not callable(fn):
        raise ValueError(f"--mutator {dotted_path!r} is not callable")
    return fn  # type: ignore[no-any-return]


def _git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check)


def _run_tag_from_branch() -> str:
    """Pull `<tag>` from `autoresearch/<tag>` branch, else 'default'."""
    res = _git("rev-parse", "--abbrev-ref", "HEAD")
    branch: str = str(res.stdout).strip()
    if branch.startswith("autoresearch/"):
        return branch[len("autoresearch/") :]
    return "default"


def _ensure_hypothesis_dir(run_tag: str) -> Path:
    p = Path("data/autoresearch") / run_tag
    p.mkdir(parents=True, exist_ok=True)
    return p


def _find_latest_report() -> Path | None:
    """Return the most-recently-modified EvalReport JSON in data/eval_runs/."""
    d = Path("data/eval_runs")
    if not d.exists():
        return None
    candidates = [
        p for p in d.glob("*.json") if not p.name.startswith("hard_triage")
    ]  # exclude triage artifacts
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _load_report(path: Path) -> Any:
    from ..eval.types import EvalReport

    return EvalReport.model_validate_json(path.read_text())


def _write_hypothesis_for_iter(run_tag: str, iter_n: int) -> Path | None:
    """Find latest EvalReport, render markdown, write iter-<n>-hypothesis.md
    + update current_hypothesis.md. Returns the iter file path on success."""
    report_path = _find_latest_report()
    if report_path is None:
        logger.warning("no EvalReport found under data/eval_runs/; skipping hypothesis")
        return None
    try:
        report = _load_report(report_path)
    except Exception as e:
        logger.warning("could not load %s as EvalReport: %s", report_path, e)
        return None
    md = diagnose_report(report)
    hdir = _ensure_hypothesis_dir(run_tag)
    iter_path = hdir / f"iter-{iter_n}-hypothesis.md"
    iter_path.write_text(md)
    # Mirror to current_hypothesis.md (copy, not symlink — cross-platform safety).
    current_path = hdir / "current_hypothesis.md"
    shutil.copyfile(iter_path, current_path)
    return iter_path


def run_loop(
    recipe_path: Path,
    dataset_path: Path,
    leaderboard_path: Path,
    program_md_path: Path,
    max_iters: int = 10,
    budget_usd: float = 20.0,
    mutator_dotted: str | None = None,
) -> int:
    """Run the autoresearch loop. Returns total iterations completed."""
    mutator = _resolve_mutator(mutator_dotted)
    run_tag = _run_tag_from_branch()

    # 1. Baseline
    print(f"[autoresearch loop] tag={run_tag} max_iters={max_iters} budget_usd={budget_usd}")
    print("[autoresearch loop] iter 0 (baseline)")
    baseline_row = run_one_iteration(
        recipe_path=recipe_path,
        dataset_path=dataset_path,
        leaderboard_path=leaderboard_path,
        description="baseline",
        program_md_path=program_md_path,
    )
    _write_hypothesis_for_iter(run_tag, 0)
    best_utility = baseline_row.get("utility")
    cumulative_cost = float(baseline_row.get("cost_usd") or 0.0)
    print(f"[autoresearch loop] baseline utility={best_utility} cost=${cumulative_cost:.4f}")

    if best_utility is None:
        print("[autoresearch loop] baseline crashed; halting before mutation.")
        return 0

    for i in range(1, max_iters + 1):
        if cumulative_cost > budget_usd:
            print(
                f"[autoresearch loop] budget exceeded (${cumulative_cost:.2f} > ${budget_usd}); halting"
            )
            return i - 1

        print(f"\n[autoresearch loop] iter {i}/{max_iters}")
        description = mutator()
        row = run_one_iteration(
            recipe_path=recipe_path,
            dataset_path=dataset_path,
            leaderboard_path=leaderboard_path,
            description=description or f"autoresearch iter {i}",
            program_md_path=program_md_path,
        )
        _write_hypothesis_for_iter(run_tag, i)

        iter_utility = row.get("utility")
        iter_cost = float(row.get("cost_usd") or 0.0)
        cumulative_cost += iter_cost

        status = row.get("status")
        if status == "crash":
            print(f"[autoresearch loop] iter {i} CRASHED — reverting working tree")
            _git("reset", "--hard", "HEAD")
            continue

        if iter_utility is None or best_utility is None or iter_utility <= best_utility:
            print(
                f"[autoresearch loop] iter {i} utility={iter_utility} <= best={best_utility}; "
                f"DISCARD (git reset --hard)"
            )
            _git("reset", "--hard", "HEAD")
        else:
            commit_msg = (
                f"autoresearch iter {i}: utility {best_utility} -> {iter_utility} "
                f"— {description or '(no description)'}"
            )
            _git("add", str(recipe_path), str(program_md_path.parent), "prompts")
            r = _git("commit", "-m", commit_msg)
            if r.returncode != 0:
                print(f"[autoresearch loop] git commit failed: {r.stderr[:300]}")
                _git("reset", "--hard", "HEAD")
            else:
                print(
                    f"[autoresearch loop] iter {i} KEEP — utility {best_utility} -> {iter_utility}"
                )
                best_utility = iter_utility

    print(
        f"\n[autoresearch loop] done. best_utility={best_utility} "
        f"cumulative_cost=${cumulative_cost:.4f}"
    )
    return max_iters
