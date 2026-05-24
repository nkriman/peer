## ADDED Requirements

### Requirement: CrossRunRunner reruns the same reviewer N times against the same dataset

The framework SHALL define `peer.eval.cross_run.CrossRunRunner(reviewer, dataset, n_runs: int = 3, concurrency: int = 5)`. The runner SHALL:

1. For each of `n_runs`, construct an `EvalRunner(reviewer=self.reviewer, dataset=self.dataset, concurrency=self.concurrency)` and call `.run()`.
2. Collect the resulting `EvalReport`s into `per_run: list[EvalReport]`.
3. Compute per-metric bands via `compute_run_bands(per_run)`.
4. Return a `MultiRunReport` carrying both.

The runner SHALL expose `run() -> MultiRunReport` and `run_async() -> MultiRunReport`. Reviewer state SHALL NOT be shared between runs — each EvalRunner call is independent. `n_runs <= 0` SHALL raise `ValueError`.

#### Scenario: CrossRunRunner invokes the reviewer N times

- **GIVEN** a counting reviewer and a 2-sample dataset
- **WHEN** `CrossRunRunner(reviewer, dataset, n_runs=3).run()` is called
- **THEN** the counting reviewer was invoked exactly 6 times (2 samples × 3 runs)

#### Scenario: MultiRunReport has N per-run EvalReports

- **GIVEN** a 1-sample dataset and a reviewer that always returns the same Review
- **WHEN** `CrossRunRunner(reviewer, dataset, n_runs=4).run()` is called
- **THEN** the returned MultiRunReport's `per_run` has length 4

#### Scenario: n_runs <= 0 raises ValueError

- **WHEN** `CrossRunRunner(reviewer, dataset, n_runs=0)` is constructed
- **THEN** `ValueError` is raised

### Requirement: compute_run_bands aggregates per-metric values across runs

The framework SHALL define `compute_run_bands(reports: list[EvalReport]) -> dict[str, MetricBand]` (re-uses the `MetricBand` model from `peer.eval.cross_judge`). The function SHALL behave identically to `compute_variance_bands` from `cross_judge` — the only difference is semantic (reruns vs judges). None values SHALL be excluded from each band; `n_judges_included` field SHALL count non-None values (the field's name is semantic-historical; it tracks "values included in the band" regardless of whether the variance source is judges or reruns).

#### Scenario: bands computed across 3 reruns

- **GIVEN** per-run `detection_rate` values `[0.04, 0.10, 0.07]` from 3 reruns of the same recipe
- **WHEN** `compute_run_bands(reports)` is called
- **THEN** the band has `min=0.04`, `max=0.10`, `median=0.07`, `range` approximately `0.06`

### Requirement: compare_to_baseline produces a structured verdict

The framework SHALL define `peer.eval.compare.compare_to_baseline(recipe_report: MultiRunReport, baseline_report: MultiRunReport, noise_floor: float = 0.06) -> ComparisonReport`. The function SHALL:

1. For each metric appearing in either report's `metric_bands`, compute `delta = recipe_median - baseline_median`.
2. Classify each metric's verdict: `"above_noise"` when `delta > noise_floor`, `"below_noise"` when `delta < -noise_floor`, `"in_noise"` otherwise.
3. Return a `ComparisonReport` with per-metric entries.

#### Scenario: recipe beats baseline by more than the noise floor

- **GIVEN** recipe `detection_rate` median 0.15 and baseline median 0.04, noise_floor 0.06
- **WHEN** `compare_to_baseline(...)` is called
- **THEN** the comparison's `detection_rate` verdict is `"above_noise"`
- **AND** the delta is approximately 0.11

#### Scenario: recipe is in the noise band

- **GIVEN** recipe median 0.08 and baseline median 0.05, noise_floor 0.06
- **WHEN** `compare_to_baseline(...)` is called
- **THEN** the comparison's `detection_rate` verdict is `"in_noise"`
- **AND** the delta is approximately 0.03

#### Scenario: recipe regresses below baseline beyond the noise floor

- **GIVEN** recipe median 0.02 and baseline median 0.15, noise_floor 0.06
- **WHEN** `compare_to_baseline(...)` is called
- **THEN** the comparison's `detection_rate` verdict is `"below_noise"`
- **AND** the delta is approximately -0.13

### Requirement: peer autoresearch run --n-runs N wires multi-run via CLI

The `peer autoresearch run` CLI SHALL accept `--n-runs N` (default 1, integer >= 1). When N == 1, behavior SHALL be unchanged (single EvalReport, single leaderboard row, single hypothesis file). When N >= 2, the runner SHALL invoke `CrossRunRunner` and write a `MultiRunReport` JSON next to the regular EvalReport. The leaderboard row SHALL carry the median DR/precision/cost/comments values; the `description` field SHALL include the suffix ` (N runs: median)`.

#### Scenario: --n-runs 1 preserves single-run behavior

- **GIVEN** `peer autoresearch run --recipe x.yaml --n-runs 1` is parsed and dispatched
- **WHEN** the runner completes
- **THEN** a single EvalReport JSON is written, single leaderboard row appended, no MultiRunReport file written

#### Scenario: --n-runs 3 writes a MultiRunReport and median leaderboard row

- **GIVEN** `peer autoresearch run --recipe x.yaml --n-runs 3` is parsed and dispatched
- **WHEN** the runner completes
- **THEN** a MultiRunReport JSON is written under `data/eval_runs/multirun_<recipe_hash>_<sha>.json`
- **AND** the appended leaderboard row's `description` ends with `(3 runs: median)`

### Requirement: peer autoresearch run --baseline-cmp emits a ComparisonReport

The CLI SHALL accept `--baseline-cmp` (boolean flag). When set, the command SHALL:

1. Run the recipe N times via CrossRunRunner.
2. Run the `BareClaudeCodeReviewer` N times against the same dataset.
3. Call `compare_to_baseline(recipe_report, baseline_report)`.
4. Write the `ComparisonReport` to disk + print the per-metric verdict table.

`--baseline-cmp` SHALL imply `--n-runs >= 3` (single-run comparisons aren't defensible). When `--n-runs 1` is explicitly set alongside `--baseline-cmp`, the command SHALL exit non-zero with a clear error.

#### Scenario: --baseline-cmp with --n-runs 1 exits non-zero

- **WHEN** `peer autoresearch run --recipe x.yaml --n-runs 1 --baseline-cmp` is parsed and dispatched
- **THEN** the command exits with a non-zero status code
- **AND** stderr contains "requires --n-runs >= 3"
