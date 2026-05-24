## 1. CrossRunRunner + MultiRunReport

- [ ] 1.1 Create `src/peer/eval/cross_run.py` with `MultiRunReport` Pydantic model (`per_run: list[EvalReport]`, `metric_bands: dict[str, MetricBand]`, `n_runs: int`).
- [ ] 1.2 Implement `compute_run_bands(reports) -> dict[str, MetricBand]` — delegates to cross_judge's existing logic (rename or share).
- [ ] 1.3 Implement `CrossRunRunner(reviewer, dataset, n_runs=3, concurrency=5)` per spec. Raises `ValueError` on `n_runs <= 0`.
- [ ] 1.4 Sync `.run()` + async `.run_async()` (sync wraps async).
- [ ] 1.5 `render_multirun_summary(report) -> str` — markdown rendering.

## 2. compare_to_baseline + ComparisonReport

- [ ] 2.1 Create `src/peer/eval/compare.py` with `ComparisonReport` Pydantic model (per-metric `recipe_median`, `baseline_median`, `delta`, `verdict`).
- [ ] 2.2 `compare_to_baseline(recipe_report, baseline_report, noise_floor=0.06)` per spec.

## 3. Exports

- [ ] 3.1 Export `CrossRunRunner`, `MultiRunReport`, `compute_run_bands`, `render_multirun_summary`, `ComparisonReport`, `compare_to_baseline` from `peer.eval`.

## 4. CLI wiring

- [ ] 4.1 Add `--n-runs N` (int, default 1) to `peer autoresearch run`.
- [ ] 4.2 Add `--baseline-cmp` (flag) to `peer autoresearch run`. Conflicts with `--n-runs 1` (exit non-zero).
- [ ] 4.3 When `--n-runs > 1`: dispatch through CrossRunRunner; write `multirun_<hash>_<sha>.json`; write leaderboard row with median values + ` (N runs: median)` description suffix.
- [ ] 4.4 When `--baseline-cmp`: also run BareClaudeCodeReviewer N times; call compare_to_baseline; write ComparisonReport JSON; print verdict table.

## 5. BDD

- [ ] 5.1 `features/cross_run.feature` covering: N reviewer invocations, MultiRunReport len, n_runs=0 ValueError, bands across 3 reruns.
- [ ] 5.2 `features/compare_to_baseline.feature` covering: above_noise / in_noise / below_noise.
- [ ] 5.3 CLI scenarios in `features/cross_run.feature`: --n-runs 1 preserves behavior, --n-runs 3 writes MultiRunReport, --baseline-cmp conflicts with --n-runs 1.

## 6. Gates

- [ ] 6.1 ruff / format / mypy / pytest / behave all clean.
