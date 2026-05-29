"""Unified `peer` CLI with subcommands: review, eval, dataset.

Decision 10 (eval-v01/design.md): single entry point via argparse subparsers.
Legacy `python -m peer.review <pr_url>` keeps working as a thin alias
forwarder so existing scripts don't break.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import Review


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="peer",
        description="Build AI PR review agents with evaluation built in.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose (DEBUG) logging",
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    # --- peer review --------------------------------------------------------
    p_review = sub.add_parser(
        "review",
        help="Review a single PR",
        description="Run the configured Agent on one GitHub PR URL.",
    )
    p_review.add_argument("pr_url", help="GitHub PR URL")
    p_review.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Model id (default: claude-sonnet-4-6)",
    )
    p_review.add_argument(
        "--system-prompt-file",
        type=Path,
        default=None,
        help="Path to a custom system prompt",
    )

    # --- peer eval ----------------------------------------------------------
    p_eval = sub.add_parser(
        "eval",
        help="Evaluate the configured agent against a gold dataset",
        description=("Run EvalRunner on a dataset of GoldSamples and report metrics."),
    )
    p_eval.add_argument(
        "--dataset",
        type=Path,
        default=Path("dataset/reference/django_pydantic_v1.jsonl"),
        help="Path to JSONL dataset (default: bundled reference dataset)",
    )
    p_eval.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Model id for the reviewer under test",
    )
    p_eval.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Path to a prior EvalReport JSON for A/B diff",
    )
    p_eval.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Where to write the new EvalReport JSON (default: data/eval_runs/<run_id>.json)",
    )
    p_eval.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Number of parallel reviewer runs (default: 5)",
    )
    # Opt-in for now per eval-v02 design: ~$0.09 of Haiku calls per 30-PR run
    # for a metric that rarely fires on well-behaved reviewers.
    p_eval.add_argument(
        "--with-rationale-grounding",
        dest="with_rationale_grounding",
        action="store_true",
        default=False,
        help="Add the RationaleGrounding LLMJudge to the metric set (opt-in).",
    )
    p_eval.add_argument(
        "--no-rationale-grounding",
        dest="with_rationale_grounding",
        action="store_false",
        help="Explicitly disable the RationaleGrounding LLMJudge.",
    )
    p_eval.add_argument(
        "--use-claude-code",
        action="store_true",
        default=False,
        help="Route every model call through the claude CLI (free, no ANTHROPIC_API_KEY). See claude-code-everywhere-v01.",
    )
    p_eval.add_argument(
        "--cross-judge",
        default=None,
        help=(
            "Comma-separated judge model names (e.g. 'sonnet,haiku,opus'). "
            "When set, runs CrossJudgeRunner instead of EvalRunner and emits a "
            "CrossJudgeReport with per-metric variance bands."
        ),
    )

    # --- peer dataset (parent for subcommands) ------------------------------
    p_ds = sub.add_parser(
        "dataset",
        help="Manage gold datasets",
        description="Add / list / show gold samples.",
    )
    ds_sub = p_ds.add_subparsers(dest="ds_cmd", required=True, metavar="DS_COMMAND")

    # peer dataset add
    p_ds_add = ds_sub.add_parser(
        "add",
        help="Curate a PR and add it to the dataset",
    )
    p_ds_add.add_argument("pr_url", help="GitHub PR URL")
    p_ds_add.add_argument(
        "--dataset",
        type=Path,
        default=Path("dataset/reference/django_pydantic_v1.jsonl"),
        help="JSONL dataset to append to",
    )
    p_ds_add.add_argument(
        "--auto-accept",
        action="store_true",
        help="Skip interactive spot-check prompt",
    )

    # peer dataset list
    p_ds_list = ds_sub.add_parser(
        "list",
        help="List the samples in a dataset",
    )
    p_ds_list.add_argument(
        "--dataset",
        type=Path,
        default=Path("dataset/reference/django_pydantic_v1.jsonl"),
    )
    p_ds_list.add_argument(
        "--show-classifications",
        action="store_true",
        help="Also show per-defect path/severity/category",
    )

    # peer dataset show
    p_ds_show = ds_sub.add_parser(
        "show",
        help="Pretty-print one full sample",
    )
    p_ds_show.add_argument("pr_url", help="GitHub PR URL of the sample to show")
    p_ds_show.add_argument(
        "--dataset",
        type=Path,
        default=Path("dataset/reference/django_pydantic_v1.jsonl"),
    )

    # --- peer benchmark (parent for subcommands) ----------------------------
    p_bench = sub.add_parser(
        "benchmark",
        help="Run the bug-benchmark capability",
        description="Run BugBenchmarkRunner against a bug-dataset and emit a BenchmarkReport.",
    )
    bench_sub = p_bench.add_subparsers(dest="ds_cmd", required=True, metavar="BENCH_COMMAND")

    # peer benchmark run
    p_bench_run = bench_sub.add_parser(
        "run",
        help="Run peer over a bug dataset and report detection_rate vs published baselines",
    )
    p_bench_run.add_argument(
        "--dataset",
        type=str,
        default="macroscope",
        help=(
            "Dataset name (e.g. 'macroscope') or path to a JSONL file in "
            "BugSample-shape. Default: macroscope."
        ),
    )
    p_bench_run.add_argument(
        "--model",
        default="anthropic:claude-sonnet-4-6",
        help="Model id for the reviewer under test (default: anthropic:claude-sonnet-4-6)",
    )
    p_bench_run.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Where to write the BenchmarkReport JSON (default: data/benchmark_runs/<run_id>.json)",
    )
    p_bench_run.add_argument(
        "--yes",
        action="store_true",
        help="Skip the cost-confirmation prompt",
    )
    p_bench_run.add_argument(
        "--language",
        default="python",
        help="Filter the dataset by language (default: python)",
    )
    p_bench_run.add_argument(
        "--use-claude-code",
        action="store_true",
        default=False,
        help="Route every model call through the claude CLI (free, no ANTHROPIC_API_KEY).",
    )

    # --- peer autoresearch (parent for subcommands) -------------------------
    p_ar = sub.add_parser(
        "autoresearch",
        help="Autonomous recipe experimentation loop",
        description=(
            "Edit recipe.yaml + prompts/default_system_prompt.md, evaluate, "
            "keep-or-revert. See program.md at the repo root."
        ),
    )
    ar_sub = p_ar.add_subparsers(dest="ds_cmd", required=True, metavar="AR_COMMAND")

    p_ar_run = ar_sub.add_parser(
        "run",
        help="Run one autoresearch iteration; append one TSV row",
    )
    p_ar_run.add_argument("--recipe", type=Path, default=Path("recipe.yaml"))
    p_ar_run.add_argument(
        "--dataset",
        type=Path,
        default=Path("dataset/reference/django_pydantic_v2_hard.jsonl"),
    )
    p_ar_run.add_argument(
        "--leaderboard", type=Path, default=Path("data/eval_runs/leaderboard.tsv")
    )
    p_ar_run.add_argument("--description", default="", help="One-line description of this mutation")
    p_ar_run.add_argument(
        "--program-md", type=Path, default=Path("program.md"), help="Path to program.md"
    )
    p_ar_run.add_argument(
        "--use-claude-code",
        action="store_true",
        default=False,
        help="Route every model call through the claude CLI (free, no ANTHROPIC_API_KEY).",
    )
    p_ar_run.add_argument(
        "--n-runs",
        type=int,
        default=1,
        help=(
            "Number of reruns of the same recipe (default 1). When >=2, dispatches "
            "through CrossRunRunner and writes a MultiRunReport. Required for any "
            "defensible 'recipe X beats Y' claim — see cross-run-v01."
        ),
    )
    p_ar_run.add_argument(
        "--baseline-cmp",
        action="store_true",
        default=False,
        help=(
            "Also run the bare baseline (BareClaudeCodeReviewer) N times and emit a "
            "ComparisonReport. Requires --n-runs >= 3."
        ),
    )

    p_ar_loop = ar_sub.add_parser(
        "loop",
        help="Run the autonomous autoresearch loop (mutate + eval + keep-or-revert)",
    )
    p_ar_loop.add_argument("--recipe", type=Path, default=Path("recipe.yaml"))
    p_ar_loop.add_argument(
        "--dataset",
        type=Path,
        default=Path("dataset/reference/django_pydantic_v2_hard.jsonl"),
    )
    p_ar_loop.add_argument(
        "--leaderboard", type=Path, default=Path("data/eval_runs/leaderboard.tsv")
    )
    p_ar_loop.add_argument("--program-md", type=Path, default=Path("program.md"))
    p_ar_loop.add_argument("--max-iters", type=int, default=10)
    p_ar_loop.add_argument("--budget-usd", type=float, default=20.0)
    p_ar_loop.add_argument(
        "--mutator",
        default="no_op",
        help="Dotted path to a mutator callable; default 'no_op' assumes you edit files between iters",
    )
    p_ar_loop.add_argument(
        "--use-claude-code",
        action="store_true",
        default=False,
        help="Route every model call through the claude CLI (free, no ANTHROPIC_API_KEY).",
    )

    p_ar_frontier = ar_sub.add_parser(
        "frontier",
        help="Compute + print the Pareto front over comparison_*.json reports",
    )
    p_ar_frontier.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("data/eval_runs"),
        help="Directory containing comparison_*.json reports (default: data/eval_runs)",
    )

    p_ar_diag = ar_sub.add_parser(
        "diagnose",
        help="Render a hypothesis markdown from an EvalReport JSON",
    )
    p_ar_diag.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Path to an EvalReport JSON (default: latest under data/eval_runs/)",
    )
    p_ar_diag.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Where to write the hypothesis markdown (default: data/autoresearch/<tag>/current_hypothesis.md)",
    )

    return parser


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _format_review_output(review: Review, pr_url: str) -> str:
    """Pure formatter for `peer review` output — returns the full string the
    CLI prints. Extracted so BDD scenarios can assert on rendering without
    spawning a subprocess.
    """
    lines: list[str] = []
    lines.append(f"\n=== Review for {pr_url} ===")
    lines.append(
        f"Model: {review.usage.get('model')}  |  "
        f"in={review.usage.get('input_tokens')}  out={review.usage.get('output_tokens')}"
    )

    if not review.comments:
        lines.append(f"\nNo comments. Reason: {review.reason or 'n/a'}")
        return "\n".join(lines)

    counts: dict[str, int] = {}
    for c in review.comments:
        counts[c.severity] = counts.get(c.severity, 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in counts.items())
    lines.append(f"\n{len(review.comments)} comment(s)  ({summary})")

    for severity in ("critical", "important", "minor", "nit"):
        for c in review.comments:
            if c.severity != severity:
                continue
            anchor = f":{c.line}" if c.line is not None else ""
            if getattr(c, "end_line", None) is not None and c.end_line != c.line:
                anchor = f":{c.line}-{c.end_line}"
            header_prefix = ""
            if getattr(c, "issue_header", None):
                header_prefix = f"{c.issue_header} · "
            lines.append(f"\n[{c.severity.upper()}] {header_prefix}{c.path}{anchor}")
            lines.append(f"  {c.body}")
            lines.append(f"  -- {c.rationale}")
            if c.suggestion:
                lines.append("  --- suggested change ---")
                for sline in c.suggestion.splitlines():
                    lines.append(f"  {sline}")
                lines.append("  -------------------------")
    return "\n".join(lines)


def _cmd_review(args: argparse.Namespace) -> int:
    from .agent import Agent

    agent = Agent(model=args.model, system_prompt_file=args.system_prompt_file)
    review = agent.review(args.pr_url)
    print(_format_review_output(review, args.pr_url))
    return 0


def _maybe_set_claude_code_env(args: argparse.Namespace) -> None:
    """If --use-claude-code was passed, set PEER_USE_CLAUDE_CODE=1 before
    any client is constructed downstream."""
    import os

    if getattr(args, "use_claude_code", False):
        os.environ["PEER_USE_CLAUDE_CODE"] = "1"


def _cmd_eval(args: argparse.Namespace) -> int:
    _maybe_set_claude_code_env(args)
    from .agent import Agent
    from .dataset import JSONLStorage
    from .eval import EvalReport, EvalRunner, render_diff, render_summary
    from .exceptions import DatasetNotFound

    # eval-cross-judge-v01: --cross-judge cannot be combined with --baseline
    # (cross-judge produces a different report shape; A/B vs single-judge
    # baseline is not meaningful today).
    if getattr(args, "cross_judge", None) and args.baseline is not None:
        print(
            "--cross-judge and --baseline cannot be combined "
            "(cross-judge reports don't A/B against single-judge baselines).",
            file=sys.stderr,
        )
        return 2

    if not args.dataset.exists():
        raise DatasetNotFound(f"Dataset not found at {args.dataset}")

    samples = JSONLStorage(args.dataset).load_all()
    if not samples:
        print(f"Dataset {args.dataset} is empty.", file=sys.stderr)
        return 2

    agent = Agent(model=args.model)
    metrics: list | None = None
    if getattr(args, "with_rationale_grounding", False):
        # Build the default metric set + append RationaleGrounding.
        from .eval import (
            CommentsPerPR,
            DetectionRate,
            MeanPerPRRecall,
            NoveltyRate,
            PrecisionPerSeverity,
            RationaleGrounding,
            SeverityCalibration,
            SuggestionRate,
        )

        metrics = [
            DetectionRate(),
            CommentsPerPR(),
            PrecisionPerSeverity(),
            MeanPerPRRecall(),
            NoveltyRate(),
            SeverityCalibration(),
            SuggestionRate(),
            RationaleGrounding(),
        ]

    # eval-cross-judge-v01: when --cross-judge is set, swap the runner.
    cross_judge_models = getattr(args, "cross_judge", None)
    if cross_judge_models:
        from .eval import CrossJudgeRunner, render_cross_judge_summary

        judge_models = [m.strip() for m in cross_judge_models.split(",") if m.strip()]
        cj_runner = CrossJudgeRunner(
            reviewer=agent,
            dataset=samples,
            judge_models=judge_models,
            concurrency=getattr(args, "concurrency", 5),
        )
        cj_report = cj_runner.run()
        out_path = args.out
        if out_path is None:
            out_dir = Path("data/eval_runs")
            out_dir.mkdir(parents=True, exist_ok=True)
            # Use a run-id-less name since CrossJudgeReport doesn't carry one
            out_path = out_dir / "cross_judge_report.json"
        out_path.write_text(cj_report.model_dump_json(indent=2))
        print(render_cross_judge_summary(cj_report))
        print(f"\nCross-judge report saved to {out_path}")
        return 0

    runner = EvalRunner(
        reviewer=agent,
        dataset=samples,
        metrics=metrics,
        concurrency=getattr(args, "concurrency", 5),
    )
    report = runner.run()

    out_path = args.out
    if out_path is None:
        out_dir = Path("data/eval_runs")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{report.run_id}.json"

    report.to_json(out_path)  # type: ignore[attr-defined]
    print(render_summary(report))
    print(f"\nReport saved to {out_path}")

    if args.baseline is not None:
        if not args.baseline.exists():
            print(f"Baseline {args.baseline} not found.", file=sys.stderr)
            return 2
        baseline = EvalReport.from_json(args.baseline)  # type: ignore[attr-defined]
        print("\n=== A/B diff vs baseline ===")
        print(render_diff(baseline, report))

    return 0


def _cmd_dataset_add(args: argparse.Namespace) -> int:
    from .dataset import Curator, JSONLStorage

    storage = JSONLStorage(args.dataset)
    curator = Curator(storage=storage)
    sample = curator.add(args.pr_url, auto_accept=args.auto_accept)
    print(f"Added {sample.pr_url} ({len(sample.gold_defects)} defects)")
    print(f"  spot_checked: {sample.metadata.spot_checked}")
    print(f"  dataset: {args.dataset}")
    return 0


def _cmd_dataset_list(args: argparse.Namespace) -> int:
    from .dataset import JSONLStorage
    from .exceptions import DatasetNotFound

    if not args.dataset.exists():
        raise DatasetNotFound(f"Dataset not found at {args.dataset}")

    samples = JSONLStorage(args.dataset).load_all()
    print(f"Dataset {args.dataset}  —  {len(samples)} sample(s)\n")
    for s in samples:
        checked = "✓" if s.metadata.spot_checked else " "
        curated = (
            s.curated_at.strftime("%Y-%m-%d")
            if isinstance(s.curated_at, datetime)
            else str(s.curated_at)[:10]
        )
        print(f"  [{checked}] {s.pr_url}  defects={len(s.gold_defects)}  curated={curated}")
        if args.show_classifications:
            for d in s.gold_defects:
                line = f":{d.line}" if d.line is not None else ""
                desc = d.description[:80].replace("\n", " ")
                print(f"      - [{d.severity}] {d.category} @ {d.path}{line}")
                print(f"          {desc}")
    return 0


def _cmd_dataset_show(args: argparse.Namespace) -> int:
    from .dataset import JSONLStorage
    from .exceptions import DatasetNotFound

    if not args.dataset.exists():
        raise DatasetNotFound(f"Dataset not found at {args.dataset}")

    storage = JSONLStorage(args.dataset)
    sample = storage.find(args.pr_url)
    if sample is None:
        print(f"Not found: {args.pr_url} in {args.dataset}", file=sys.stderr)
        return 2

    import json

    print(json.dumps(sample.model_dump(mode="json"), indent=2, default=str))
    return 0


def _cmd_autoresearch_run(args: argparse.Namespace) -> int:
    _maybe_set_claude_code_env(args)

    n_runs = int(getattr(args, "n_runs", 1) or 1)
    baseline_cmp = bool(getattr(args, "baseline_cmp", False))

    # Spec constraint: --baseline-cmp requires --n-runs >= 3
    if baseline_cmp and n_runs < 3:
        print(
            "--baseline-cmp requires --n-runs >= 3 (single-run comparisons aren't defensible).",
            file=sys.stderr,
        )
        return 2

    # Single-run path: back-compat. Unchanged.
    if n_runs == 1:
        from .autoresearch import run_one_iteration

        row = run_one_iteration(
            recipe_path=args.recipe,
            dataset_path=args.dataset,
            leaderboard_path=args.leaderboard,
            description=args.description,
            program_md_path=args.program_md,
        )
        status = row.get("status")
        print(
            f"\n=== autoresearch iter ===\n"
            f"  status:        {status}\n"
            f"  utility:       {row.get('utility')}\n"
            f"  detection:     {row.get('detection_rate')}\n"
            f"  precision:     minor={row.get('precision_minor')} "
            f"important={row.get('precision_important')} critical={row.get('precision_critical')}\n"
            f"  cost_usd:      {row.get('cost_usd')}\n"
            f"  n_comments:    {row.get('n_comments_total')}\n"
            f"  description:   {row.get('description')}"
        )
        return 0 if status == "ok" else 1

    # Multi-run path (cross-run-v01).
    from .autoresearch.multirun import run_multirun_iteration

    return run_multirun_iteration(
        recipe_path=args.recipe,
        dataset_path=args.dataset,
        leaderboard_path=args.leaderboard,
        description=args.description,
        program_md_path=args.program_md,
        n_runs=n_runs,
        baseline_cmp=baseline_cmp,
    )


def _cmd_autoresearch_loop(args: argparse.Namespace) -> int:
    _maybe_set_claude_code_env(args)
    from .autoresearch import run_loop

    iters = run_loop(
        recipe_path=args.recipe,
        dataset_path=args.dataset,
        leaderboard_path=args.leaderboard,
        program_md_path=args.program_md,
        max_iters=args.max_iters,
        budget_usd=args.budget_usd,
        mutator_dotted=args.mutator,
    )
    return 0 if iters >= 0 else 1


def _cmd_autoresearch_frontier(args: argparse.Namespace) -> int:
    from .autoresearch.frontier import (
        compute_pareto_front,
        read_comparison_reports,
        render_frontier,
    )

    paired = read_comparison_reports(args.reports_dir)
    if not paired:
        print(
            f"No comparison_*.json reports found under {args.reports_dir}. "
            f"Run `peer autoresearch run --baseline-cmp --n-runs N` first.",
            file=sys.stderr,
        )
        return 2
    reports = [r for _, r in paired]
    front, _dominated = compute_pareto_front(reports)
    front_paths = {id(r) for r in front}
    paired_front = [(p, r) for p, r in paired if id(r) in front_paths]
    paired_dominated = [(p, r) for p, r in paired if id(r) not in front_paths]
    print(render_frontier(paired_front, paired_dominated))
    return 0


def _cmd_autoresearch_diagnose(args: argparse.Namespace) -> int:
    from .autoresearch import diagnose_report

    report_path = args.report
    if report_path is None:
        d = Path("data/eval_runs")
        candidates = list(d.glob("*.json")) if d.exists() else []
        if not candidates:
            print(
                f"No EvalReport found under {d}. Pass --report PATH explicitly.",
                file=sys.stderr,
            )
            return 2
        report_path = max(candidates, key=lambda p: p.stat().st_mtime)
        print(f"[autoresearch diagnose] using latest report: {report_path}", file=sys.stderr)

    from .eval.types import EvalReport

    report = EvalReport.model_validate_json(report_path.read_text())
    md = diagnose_report(report)

    out_path = args.out
    if out_path is None:
        out_dir = Path("data/autoresearch/default")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "current_hypothesis.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md)
    print(f"wrote hypothesis to {out_path}")
    return 0


def _cmd_benchmark_run(args: argparse.Namespace) -> int:
    _maybe_set_claude_code_env(args)
    from .agent import Agent
    from .benchmark import BugBenchmarkRunner, MacroscopeLoader

    # Resolve dataset: named dataset → vendored path under dataset/benchmark/,
    # explicit path → that path.
    if args.dataset == "macroscope":
        ds_path = Path("dataset/benchmark/macroscope_v1.jsonl")
    else:
        ds_path = Path(args.dataset)
    if not ds_path.exists():
        print(
            f"Bug-benchmark dataset not found: {ds_path}. "
            f"Run `peer benchmark update-dataset` once it's implemented, "
            f"or pass --dataset <path-to.jsonl>.",
            file=sys.stderr,
        )
        return 2

    samples = MacroscopeLoader(ds_path).load(language=args.language)
    if not samples:
        print(
            f"Dataset {ds_path} has no samples for language={args.language!r}.",
            file=sys.stderr,
        )
        return 2

    if not args.yes:
        print(
            f"About to run {len(samples)} bug(s) through {args.model}. "
            f"Each bug fires one reviewer call + up to N judge calls. "
            f"Pass --yes to skip this prompt.",
            file=sys.stderr,
        )
        try:
            reply = input("Continue? [y/N] ").strip().lower()
        except EOFError:
            reply = ""
        if reply not in ("y", "yes"):
            print("aborted.", file=sys.stderr)
            return 1

    from .claude_code_client import make_client as _make_client

    agent = Agent(model=args.model)
    runner = BugBenchmarkRunner(
        reviewer=agent,
        dataset=samples,
        judge_client=_make_client(),
    )
    report = runner.run()

    out_path = args.out
    if out_path is None:
        out_dir = Path("data/benchmark_runs")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{report.run_id}.json"
    out_path.write_text(report.model_dump_json(indent=2))
    print(
        f"\n=== BenchmarkReport ===\n"
        f"  bugs total:   {report.n_bugs_total}\n"
        f"  bugs caught:  {report.n_bugs_caught}\n"
        f"  detection:    {report.detection_rate}\n"
        f"  cost:         {report.cost_usd_total}\n"
        f"\nReport saved to {out_path}"
    )
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


_DISPATCH = {
    ("review", None): _cmd_review,
    ("eval", None): _cmd_eval,
    ("dataset", "add"): _cmd_dataset_add,
    ("dataset", "list"): _cmd_dataset_list,
    ("dataset", "show"): _cmd_dataset_show,
    ("benchmark", "run"): _cmd_benchmark_run,
    ("autoresearch", "run"): lambda args: _cmd_autoresearch_run(args),
    ("autoresearch", "loop"): lambda args: _cmd_autoresearch_loop(args),
    ("autoresearch", "diagnose"): lambda args: _cmd_autoresearch_diagnose(args),
    ("autoresearch", "frontier"): lambda args: _cmd_autoresearch_frontier(args),
}


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    key = (args.cmd, getattr(args, "ds_cmd", None))
    handler = _DISPATCH.get(key)
    if handler is None:
        parser.print_help()
        return 1

    try:
        return handler(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            raise
        return 2


if __name__ == "__main__":
    sys.exit(main())
