## Why

The framework's value proposition is "build AI PR review agents with evaluation built in" — but until we can demonstrate that a peer-built reviewer holds up against industry-standard benchmarks, that pitch is unsubstantiated. The competitive landscape research (`docs/competitive_landscape_research.md`) identified Macroscope's 118-runtime-bug benchmark as the de facto industry yardstick (Macroscope 48% / CodeRabbit 46% / BugBot 42% / Greptile 24% / Graphite 18% detection). The dataset is MIT-licensed at `github.com/vlad-ko/pr-review-bench`.

This change ships a benchmark capability: load a runtime-bug dataset, run peer against it, report numbers comparable to the published baselines. No live commercial-API calls in v0.1 — we compare peer's numbers vs the published Macroscope leaderboard.

The chosen scope (runtime bugs with known ground truth, not human-comment matching) reframes peer's eval credibility. peer's reference dataset (`django_pydantic_v2.jsonl`) is harder than runtime bugs because most defects are style / docs / Django-specific conventions — peer's 7.9% on that dataset isn't directly comparable to Macroscope's 48% on runtime bugs. The benchmark capability lets us produce an apples-to-apples number.

## What Changes

- Add a `BugDataset` JSONL schema: each line is a `BugSample` — a PR / commit / file-range with a known runtime bug + ground-truth metadata (root cause, suggested fix, severity).
- Add a `BugBenchmarkRunner` (separate from `EvalRunner`) that runs peer against `BugDataset` and scores: did peer's review include a comment whose path + line range overlaps the bug location AND whose body semantically references the bug's root cause? Uses an `LLMJudge` instance (per `eval-v02`) with bug-specific rubric — not a separate hardcoded judge function.
- **Use `Agent.override()` pattern (per `peer-deps-v01`)** instead of constructing a separate `RepoAwareAgent`. The runner takes ONE Agent and, per-sample, uses `with agent.override(deps=deps_for_this_sample):` to swap deps. Cleaner than per-repo Agent instances; benefits from peer-deps-v01's testing primitives (e.g., `agent.override(reviewer=TestReviewer())` for dry-run cost validation before a real benchmark run).
- Ship a `peer.benchmark.macroscope` loader that fetches + parses the Macroscope dataset from `github.com/vlad-ko/pr-review-bench` (or a vendored snapshot — see Decision 5).
- Add a `peer benchmark` CLI subcommand: `peer benchmark --dataset macroscope` (or `--dataset path/to/custom.jsonl`) runs the full benchmark and produces a leaderboard-style report.
- Add a `BenchmarkReport` schema: detection_rate, comments_per_pr, cost, latency, plus the per-bug breakdown.
- Include a `compare_to_published` mode that renders peer's numbers side-by-side with Macroscope's published baselines (CodeRabbit, Greptile, Graphite Diamond, BugBot, Macroscope) so users see where their custom-built reviewer sits in the landscape.

## Capabilities

### New Capabilities

- `bug-benchmark`: load runtime-bug datasets, run reviewers against them, score detection + precision, produce comparable leaderboard reports.

### Modified Capabilities

- `unified-cli` (from `eval-v01`): add `peer benchmark` subcommand.

## Impact

- **Code**: new subpackage `src/peer/benchmark/` with `types.py` (BugSample, BenchmarkReport), `loader.py` (BugDatasetSource + MacroscopeLoader), `runner.py` (BugBenchmarkRunner), `judge.py` (bug-detection judge prompt), `report.py` (leaderboard renderer). Update `src/peer/cli.py` with `peer benchmark` subcommand. New `tests/test_benchmark.py`.
- **Dataset**: ship a vendored snapshot of the Macroscope dataset at `dataset/benchmark/macroscope_v1.jsonl` (one-time fetch from the upstream MIT-licensed repo, with provenance file noting source commit SHA + date).
- **No new pip deps.** Existing `anthropic` (judge) and stdlib.
- **Cost note:** running benchmark on full 118 bugs = ~$5–10 per peer config tested (118 reviews × ~$0.05). One-time per A/B; reports cached as JSON.
- **Out of scope**: live commercial-baseline runs (would require CodeRabbit / Greptile / Macroscope API access; many tools don't expose APIs at all). The comparison mode uses *published* numbers, not freshly-run ones. Also out of scope: building peer's own larger bug dataset (could be a follow-on); multi-language benchmarks (Macroscope's dataset covers 8 languages but peer is Python-only until linter-context-v01 lands more languages).
