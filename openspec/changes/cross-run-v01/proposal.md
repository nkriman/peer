## Why

The noise-floor finding (`data/autoresearch/may24/noise_floor_finding.md`) showed that the dominant variance source on the hard subset is *reviewer-side run-to-run noise* — same recipe, temperature=0, produces 2.5× different DR across runs. Cross-judge variance, by contrast, is ~0. Every single-run autoresearch "win" we recorded is suspect.

The fix is multi-run averaging as a first-class primitive. `CrossRunRunner` reruns the reviewer N times against the same dataset, aggregates per-metric medians + ranges + per-run values, and reports them in a `MultiRunReport`. It's a sibling to `CrossJudgeRunner` (which loops the judge); this one loops the reviewer.

Once this lands, every leaderboard row, every keep/discard decision, every "peer beats X" claim should be expressed as `median ± range` over N runs, not a point estimate. Per the next-moves list in the noise-floor finding, this is item #1.

## What Changes

- New `peer.eval.cross_run` module:
  - `CrossRunRunner(reviewer, dataset, n_runs: int = 3, concurrency: int = 5)` — runs `EvalRunner` N times sequentially against the same dataset. Returns a `MultiRunReport`.
  - `MultiRunReport` Pydantic model: `per_run: list[EvalReport]`, `metric_bands: dict[str, MetricBand]` (same shape as the cross-judge bands), `n_runs: int`.
  - `compute_run_bands(reports: list[EvalReport]) -> dict[str, MetricBand]` — pure function; identical structure to `compute_variance_bands` but the inputs are reruns of the same recipe rather than per-judge reruns. Re-uses the existing `MetricBand` model.
  - `render_multirun_summary(report: MultiRunReport) -> str` — markdown summary with per-metric bands + per-run values.
- New `peer.eval.compare.compare_to_baseline(recipe_report, baseline_report, noise_floor: float = 0.06) -> ComparisonReport` — pure function over two `MultiRunReport`s. Computes per-metric `median_delta` (recipe - baseline), flags "real improvement" when `median_delta > noise_floor`.
- New `ComparisonReport` model: per-metric `recipe_median`, `baseline_median`, `delta`, `verdict: Literal["above_noise", "in_noise", "below_noise"]`.
- New `peer autoresearch run` flags:
  - `--n-runs N` (default 1, preserves back-compat). When >1, runs the recipe N times and writes a `MultiRunReport` to disk + adds a median row to the leaderboard.
  - `--baseline-cmp` — when set, also runs the bare baseline N times and writes a `ComparisonReport`. Output prints the verdict.

## Capabilities

### New Capabilities

- `cross-run`: `CrossRunRunner` + `MultiRunReport` + `compute_run_bands` + `render_multirun_summary` + `compare_to_baseline` + `ComparisonReport` + CLI flags.

### Modified Capabilities

- `autoresearch-recipe` (from autoresearch-recipe-v01): `peer autoresearch run` gains `--n-runs` + `--baseline-cmp` flags. Single-run behavior unchanged when flags are absent.

## Impact

- **Code**: new `src/peer/eval/cross_run.py`, new `src/peer/eval/compare.py`. Modifications: `src/peer/eval/__init__.py` (exports), `src/peer/cli.py` (flags + dispatch), `src/peer/autoresearch/runner.py` (multi-run dispatch).
- **Dependencies**: none new.
- **Tests**: BDD in `features/cross_run.feature` + `features/compare_to_baseline.feature`. Step defs use synthetic EvalReports — no live LLM calls in BDD.
- **Schema**: `MultiRunReport` + `ComparisonReport` are new top-level Pydantic models. `EvalReport` unchanged.
- **Back-compat**: defaults preserved. `peer autoresearch run` without flags behaves identically to today.
- **Out of scope**: parallel multi-run execution (sequential is fine and simpler); judge-variance × reviewer-variance joint sweeps (orthogonal axes; can compose `CrossRunRunner` around `CrossJudgeRunner` later if needed).
- **Performance**: each multi-run iter takes N × single-run wall-clock. CLI subscription cost = $0; wall-clock is the constraint.
