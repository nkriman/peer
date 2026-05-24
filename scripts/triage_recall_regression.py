"""Triage script for the v0.2 recall regression.

Runs the hard subset twice with the CURRENT prompt (to bound stochastic
noise) and once with the v1-era prompt (to isolate the prompt-change
hypothesis). Prints detection_rate + per-PR match deltas.

Usage:
    set -a; . .env; set +a
    uv run python3 scripts/triage_recall_regression.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from peer.agent import Agent  # noqa: E402
from peer.dataset import JSONLStorage  # noqa: E402
from peer.eval import EvalRunner  # noqa: E402

DATASET = ROOT / "dataset/reference/django_pydantic_v2_hard.jsonl"
MODEL = "anthropic:claude-sonnet-4-6"

# Pre-v0.2 system prompt (peer-5is removed the optional-field descriptions
# for end_line / issue_header / suggestion). Built from the current default
# minus those bullets.
from peer.prompts import DEFAULT_SYSTEM_PROMPT  # noqa: E402

# Strip the 3 added bullets (end_line / issue_header / suggestion) for the
# A/B test. The full pre-v0.2 prompt was otherwise identical.
_LINES_TO_DROP = [
    "- end_line: (optional)",
    "- issue_header: (optional)",
    "- suggestion: (optional)",
]


def _v1_prompt() -> str:
    out_lines: list[str] = []
    in_drop = False
    for line in DEFAULT_SYSTEM_PROMPT.splitlines():
        if any(line.startswith(p) for p in _LINES_TO_DROP):
            in_drop = True
            continue
        if in_drop:
            # Drop continuation lines (start with spaces) and the
            # nested bullet * sub-criteria for suggestion.
            stripped = line.lstrip()
            if (
                stripped.startswith("*")
                or stripped.startswith("DO NOT")
                or stripped.startswith("the fix is")
                or stripped.startswith("you are confident")
                or line.startswith("  ")
            ):
                continue
            # A blank line or a new top-level bullet ends the drop region.
            in_drop = False
        out_lines.append(line)
    return "\n".join(out_lines)


async def _run(label: str, prompt: str | None) -> dict:
    samples = JSONLStorage(DATASET).load_all()
    agent_kwargs: dict = {"model": MODEL}
    if prompt is not None:
        agent_kwargs["system_prompt"] = prompt
    agent = Agent(**agent_kwargs)
    runner = EvalRunner(reviewer=agent, dataset=samples, concurrency=5)
    print(f"\n[{label}] running on {len(samples)} samples ...")
    report = await runner.run_async()
    return {"label": label, "report": report}


def _summarize(label: str, report) -> dict:
    detection = (report.summary.metric_values or {}).get("detection_rate")
    per_pr_matches: dict[str, int] = {}
    n_comments = 0
    for s in report.per_sample:
        url = s.pr_url
        d = s.metrics.get("detection_rate") or None
        if d and d.per_sample_detail:
            per_pr_matches[url] = d.per_sample_detail.get("matched_count", 0)
        if s.review_summary:
            n_comments += int(s.review_summary.get("n_comments", 0))
    out = {
        "label": label,
        "detection_rate": detection,
        "n_comments_total": n_comments,
        "per_pr_matches": per_pr_matches,
        "cost_usd_total": report.summary.cost_usd_total,
    }
    print(
        f"  [{label}] detection_rate={detection!r}  n_comments={n_comments}  "
        f"cost=${report.summary.cost_usd_total or 0:.4f}"
    )
    for url, m in per_pr_matches.items():
        print(f"    matches={m:2d}  {url.split('/')[-1]}")
    return out


async def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set — load .env first.", file=sys.stderr)
        return 2

    # Run 1: current prompt
    r1 = await _run("current-1", prompt=None)
    s1 = _summarize("current-1", r1["report"])

    # Run 2: current prompt again (noise bound)
    r2 = await _run("current-2", prompt=None)
    s2 = _summarize("current-2", r2["report"])

    # Run 3: v1-era prompt (no end_line/issue_header/suggestion guidance)
    v1p = _v1_prompt()
    r3 = await _run("v1-prompt", prompt=v1p)
    s3 = _summarize("v1-prompt", r3["report"])

    print("\n=== Triage summary ===")
    print(json.dumps({"runs": [s1, s2, s3]}, indent=2))

    # Save full reports for forensics.
    out_dir = ROOT / "data/eval_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    for label, report in (
        ("triage_current_1", r1["report"]),
        ("triage_current_2", r2["report"]),
        ("triage_v1prompt", r3["report"]),
    ):
        path = out_dir / f"hard_{label}.json"
        path.write_text(report.model_dump_json(indent=2))
        print(f"saved {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
