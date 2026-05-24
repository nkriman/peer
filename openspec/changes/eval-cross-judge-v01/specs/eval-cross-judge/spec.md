## ADDED Requirements

### Requirement: CrossJudgeRunner re-judges cached reviews against N judge models

The framework SHALL define `peer.eval.cross_judge.CrossJudgeRunner(reviewer, dataset, judge_models: list[str], concurrency: int = 5)`. The runner SHALL:

1. Run the reviewer once per dataset sample, caching the resulting `Review` keyed by `pr_url`.
2. For each `judge_model` in `judge_models`, construct an internal `EvalRunner` whose judge client is forced to that model (via `judge_client_override`), and re-run every metric over the cached reviews. The reviewer SHALL NOT be invoked again for that judge.
3. Produce a `CrossJudgeReport` containing the per-judge `EvalReport`s and the computed variance bands.

The runner SHALL expose `run() -> CrossJudgeReport` and `run_async() -> CrossJudgeReport`. Both SHALL share the cached reviews; only the judge-pass differs between sync/async.

#### Scenario: reviewer runs once across N judges

- **GIVEN** a `CrossJudgeRunner` with `judge_models=["sonnet","haiku","opus"]` and a counting reviewer
- **WHEN** `.run()` is called on a 2-sample dataset
- **THEN** the counting reviewer was invoked exactly 2 times (not 6)

#### Scenario: each judge's metrics are computed independently

- **GIVEN** a `CrossJudgeRunner` with `judge_models=["sonnet","haiku"]` and stub judges that return different matches
- **WHEN** `.run()` returns
- **THEN** the report has 2 per-judge `EvalReport`s under `per_judge`
- **AND** the per-judge `detection_rate` values can differ (no averaging during the per-judge phase)

### Requirement: CrossJudgeReport computes variance bands per metric

The framework SHALL define `CrossJudgeReport` Pydantic model with `model_config = ConfigDict(extra="forbid")` and fields:

- `judge_models: list[str]`
- `per_judge: dict[str, EvalReport]` — one EvalReport per judge model
- `metric_bands: dict[str, MetricBand]` — for each metric name, computed min / max / median / range across judges

The `MetricBand` model SHALL have `min: float | None`, `max: float | None`, `median: float | None`, `range: float | None` (range = max - min). When a metric value is None for any judge, that judge is excluded from the band (and `MetricBand.n_judges_included < len(judge_models)` records the dropout).

#### Scenario: variance bands computed across 3 judges

- **GIVEN** per-judge `detection_rate` values `[0.10, 0.04, 0.07]` from 3 judges
- **WHEN** `compute_variance_bands(reports)` is called
- **THEN** the band has `min=0.04`, `max=0.10`, `median=0.07`, `range=0.06`
- **AND** `n_judges_included == 3`

#### Scenario: None values are excluded from the band

- **GIVEN** per-judge `detection_rate` values `[0.10, None, 0.07]` (one judge couldn't compute it)
- **WHEN** `compute_variance_bands(reports)` is called
- **THEN** the band has `min=0.07`, `max=0.10`, `n_judges_included == 2`

### Requirement: `peer eval --cross-judge` CLI flag drives the runner

The `peer eval` CLI SHALL accept `--cross-judge <comma-separated-models>` (e.g. `--cross-judge sonnet,haiku,opus`). When set:

1. The runner constructed SHALL be a `CrossJudgeRunner` instead of `EvalRunner`.
2. The output saved SHALL be a `CrossJudgeReport` JSON (not an `EvalReport`).
3. The console summary SHALL render the variance-bands view, not the single-judge view.
4. The flag SHALL conflict with `--baseline` (cross-judge reports don't A/B against single-judge baselines today) — combining them MUST exit non-zero with a clear error.

#### Scenario: --cross-judge writes a CrossJudgeReport, not an EvalReport

- **GIVEN** `peer eval --dataset x.jsonl --cross-judge sonnet,haiku --out tmp/report.json` is parsed and dispatched
- **WHEN** the command completes
- **THEN** `tmp/report.json` parses cleanly as a `CrossJudgeReport`
- **AND** the file contains 2 `EvalReport`s under `per_judge`

### Requirement: render_cross_judge_summary renders variance bands

The framework SHALL define `render_cross_judge_summary(report: CrossJudgeReport) -> str` producing a deterministic markdown summary with:

- A header section listing the judges
- A "Variance bands" table with columns: metric, min, median, max, range
- For metrics that vary by ≥ 2× across judges (i.e. `max / min >= 2`), a "⚠️ HIGH VARIANCE" annotation

#### Scenario: high variance is flagged

- **GIVEN** a `CrossJudgeReport` with `detection_rate` band `min=0.02, max=0.10` (5× spread)
- **WHEN** `render_cross_judge_summary(report)` is called
- **THEN** the returned string contains `"⚠️ HIGH VARIANCE"` in the `detection_rate` row

### Requirement: peer.dataset.split.load_split implements the dataset-split convention

The framework SHALL define `peer.dataset.split.load_split(base_path: Path, split: str) -> list[GoldSample]`:

- Given `base_path = "data/django_v2.jsonl"` and `split = "dev"`, the function SHALL look for `"data/django_v2.dev.jsonl"`.
- If the split file exists, it is loaded via `JSONLStorage`.
- If the split file does NOT exist, the function falls back to loading `base_path` itself and emits a `logging.info` line indicating no split was found.
- Two recognized splits: `"dev"` and `"test"`. Other names SHALL raise `ValueError`.

The convention is documented: hand-curated datasets SHOULD be split into `*.dev.jsonl` (for autoresearch / hill-climbing) and `*.test.jsonl` (held-out; never autoresearched against). The split happens at curation time; this module is the runtime accessor.

#### Scenario: load_split returns the split file when present

- **GIVEN** `data/foo.jsonl` (10 samples) and `data/foo.dev.jsonl` (7 samples) exist
- **WHEN** `load_split(Path("data/foo.jsonl"), "dev")` is called
- **THEN** the returned list has length 7

#### Scenario: load_split falls back when no split exists

- **GIVEN** `data/foo.jsonl` exists but `data/foo.test.jsonl` does NOT
- **WHEN** `load_split(Path("data/foo.jsonl"), "test")` is called
- **THEN** the returned list has the same length as loading `base_path` directly
- **AND** an INFO log message contains the literal string `"no split file"`

#### Scenario: unknown split name raises ValueError

- **GIVEN** any `base_path`
- **WHEN** `load_split(base_path, "production")` is called
- **THEN** `ValueError` is raised with a message listing the allowed split names
