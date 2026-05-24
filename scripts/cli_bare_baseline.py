"""Run the BareClaudeCodeReviewer baseline on the hard subset.

This is the falsifiability test: if `claude --print <diff>` alone scores
as well as peer's full pipeline, peer's codebase-context + prompt-tuning
machinery is providing no value.

Doesn't go through `peer.autoresearch.runner` because that path requires
a Recipe and Agent. Constructs EvalRunner directly with the baseline as
the reviewer, runs sync, appends to the leaderboard with a
`baseline[...]` description so it slots into the existing Pareto analysis.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from peer.autoresearch.leaderboard import append_row  # noqa: E402
from peer.baselines import BareClaudeCodeReviewer  # noqa: E402
from peer.dataset import JSONLStorage  # noqa: E402
from peer.eval import EvalRunner  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cli_bare_baseline")


DATASET_PATH = ROOT / "dataset/reference/django_pydantic_v2_hard.jsonl"
LEADERBOARD_PATH = ROOT / "data/eval_runs/leaderboard.tsv"


def _extract_precision_per_severity(report: Any) -> dict[str, float | None]:
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


def _git_commit_sha() -> str:
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return out.stdout.strip() or "uncommitted"
    except Exception:
        return "uncommitted"


def main() -> int:
    if os.environ.get("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY set — unsetting for this run to prove $0 spend")
        del os.environ["ANTHROPIC_API_KEY"]
    # The baseline shells out directly; doesn't use peer.claude_code_client.
    # But the JUDGE used by EvalRunner DOES — set the env flag so judges
    # route through the CLI too.
    os.environ["PEER_USE_CLAUDE_CODE"] = "1"

    samples = JSONLStorage(DATASET_PATH).load_all()
    reviewer = BareClaudeCodeReviewer(model_id="sonnet")
    runner = EvalRunner(reviewer=reviewer, dataset=samples, concurrency=5)

    logger.info("Running BareClaudeCodeReviewer on %d samples (CLI, $0 spend)", len(samples))
    t0 = time.monotonic()
    report = runner.run()
    elapsed = time.monotonic() - t0
    logger.info("done in %.0fs", elapsed)

    # Append a leaderboard row so this sits alongside the arch sweep + iter runs.
    metric_values = report.summary.metric_values or {}
    detection = metric_values.get("detection_rate")
    sev = _extract_precision_per_severity(report)
    n_comments_total = _sum_n_comments(report)
    append_row(
        LEADERBOARD_PATH,
        commit_sha=_git_commit_sha(),
        recipe_hash="bare----",
        utility=detection,
        detection_rate=detection,
        precision_minor=sev["minor"],
        precision_important=sev["important"],
        precision_critical=sev["critical"],
        cost_usd=report.summary.cost_usd_total,
        n_comments_total=n_comments_total,
        status="ok",
        description="baseline[pure claude code: gh pr diff -> claude --print, NO peer context/prompt/strategies]",
    )

    # Save full EvalReport
    out_path = ROOT / "data/eval_runs/bare_baseline.json"
    out_path.write_text(report.model_dump_json(indent=2))
    logger.info("EvalReport saved to %s", out_path)

    print()
    print("=== BARE BASELINE RESULT ===")
    print(f"  detection_rate:   {detection}")
    print(f"  n_comments_total: {n_comments_total}")
    print(f"  cost_usd:         {report.summary.cost_usd_total}")
    print()
    print("Compare against peer recipes:")
    print("  arch[narrower context]:       DR=0.0980, n=29, $0.83  <- current peer best")
    print("  arch[baseline] (sonnet/30K):  DR=0.0784, n=31, $0.75")
    if detection is not None:
        if detection >= 0.0980:
            print()
            print("  ⚠️  BASELINE MATCHES OR BEATS PEER — framework value at risk.")
        elif detection >= 0.08:
            print()
            print("  ⚠️  Baseline close to peer's best. Marginal framework value.")
        else:
            print()
            print(
                f"  ✓  Peer's best beats baseline by {0.0980 - detection:+.4f} DR. Framework adds value."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
