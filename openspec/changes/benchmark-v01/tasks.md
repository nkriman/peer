## 1. Schemas

- [ ] 1.1 Create `src/peer/benchmark/__init__.py` (subpackage).
- [ ] 1.2 Create `src/peer/benchmark/types.py` with Pydantic models: `BugLocation`, `BugSample`, `BugBenchmarkResult`, `BenchmarkReport`. Schema versioned via `report_schema_version`.
- [ ] 1.3 Add exception `InvalidBugSample` in `src/peer/exceptions.py`.

## 2. Dataset loader + vendoring

- [ ] 2.1 Create `src/peer/benchmark/loader.py` with `BugDatasetSource` Protocol + `MacroscopeLoader` default impl.
- [ ] 2.2 Fetch the Macroscope dataset from `github.com/vlad-ko/pr-review-bench` (or wherever it actually lives — verify the URL is correct; the dev.to article and Macroscope research both reference it). Save vendored snapshot to `dataset/benchmark/macroscope_v1.jsonl`.
- [ ] 2.3 Map upstream schema → peer's `BugSample` schema. Document mapping decisions in `dataset/benchmark/MACROSCOPE_PROVENANCE.md`.
- [ ] 2.4 Implement `MacroscopeLoader.load(language="python")` filter.

## 3. Bug-detection judge

- [ ] 3.1 Create `src/peer/benchmark/judge.py` with `judge_bug_caught(bug: BugSample, peer_comment: Comment, client=None) -> bool`. Prompt asks "Did this reviewer comment identify the bug described below? CAUGHT or NOT_CAUGHT." Single Haiku call per pair.
- [ ] 3.2 Pre-filter by path overlap + proximity (±10 lines of bug range) before invoking judge; skip judge call when peer comment is out of range.

## 4. Runner

- [ ] 4.1 Create `src/peer/benchmark/runner.py` with `BugBenchmarkRunner(reviewer, dataset, judge_model="claude-haiku-4-5-20251001")`.
- [ ] 4.2 Implement `run() -> BenchmarkReport`:
  - For each bug: build a synthetic PR URL pointing at the bug's commit (or use `repo_url + "/commit/" + commit_sha`); invoke `reviewer.review(...)`.
  - For each peer comment in proximity, call `judge_bug_caught`; if any CAUGHT, mark bug caught.
  - Capture per-bug result with reason on miss.
- [ ] 4.3 Aggregate detection_rate, comments_per_pr, cost (via `peer.eval.pricing.estimate_cost`), latency.
- [ ] 4.4 Handle per-bug review failures gracefully (log, mark bug as `error`, continue).

## 5. Published baselines

- [ ] 5.1 Create `src/peer/benchmark/baselines.py` with `PUBLISHED_BASELINES` dict for Macroscope dataset (CodeRabbit, Greptile, Cursor BugBot, Graphite Diamond, Macroscope — numbers from `docs/competitive_landscape_research.md`).
- [ ] 5.2 Include source citation URL + date for each baseline.

## 6. Report rendering

- [ ] 6.1 Implement `BenchmarkReport.to_json` / `from_json` (similar pattern to EvalReport).
- [ ] 6.2 Implement `render_leaderboard(report) -> str` showing peer's row + published-baselines block.
- [ ] 6.3 Implement `render_bug_misses(report) -> str` showing the per-bug breakdown for forensics (which bugs missed + reason).

## 7. CLI

- [ ] 7.1 Add `peer benchmark` subcommand with subparsers for `run` (default) and `update-dataset`.
- [ ] 7.2 `peer benchmark run [--dataset NAME-OR-PATH] [--model M] [--out PATH] [--yes]`:
  - Loads the dataset (default `macroscope`)
  - Estimates cost; prompts confirmation unless `--yes`
  - Runs `BugBenchmarkRunner`
  - Saves report + prints `render_leaderboard`
- [ ] 7.3 `peer benchmark update-dataset --source URL [--apply]`:
  - Fetches upstream; diffs vs vendored; with `--apply` overwrites + updates provenance.

## 8. Tests

- [ ] 8.1 `tests/test_benchmark_types.py` — BugSample / BenchmarkReport round-trip; InvalidBugSample on malformed.
- [ ] 8.2 `tests/test_benchmark_judge.py` — judge_bug_caught with mocked Anthropic; CAUGHT positive, NOT_CAUGHT negative, no-proximity skip.
- [ ] 8.3 `tests/test_benchmark_runner.py` — mock reviewer + small fixture dataset; verify detection_rate, per-bug breakdown, cost reporting.
- [ ] 8.4 `tests/test_benchmark_cli.py` — `peer benchmark` arg parsing; cost-prompt behavior (skip with --yes); subcommand dispatch.

## 9. Verification

- [ ] 9.1 Run `peer benchmark --dataset macroscope --yes` with the default agent (`claude-sonnet-4-6`, no conventions, no linters yet). Save to `data/benchmark_runs/macroscope_default_<run_id>.json`.
- [ ] 9.2 Run again with `+linters +conventions +config` configurations once those changes land. Document deltas.
- [ ] 9.3 Update `docs/competitive_landscape_research.md` with peer's actual benchmark numbers vs the published baselines.

## 10. Documentation

- [ ] 10.1 Add a "Benchmarks" section to README pointing at `peer benchmark` and explaining the published-baselines comparison.
- [ ] 10.2 Add a section to `docs/framework_overview.md` explaining the bug-benchmark vs human-comment-eval distinction (different ground truth, different metrics, both useful).
