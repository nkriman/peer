## ADDED Requirements

### Requirement: EvalRunner composes Reviewer + Dataset + Metrics into a single run

The framework SHALL provide an `EvalRunner` class that accepts a configured `Reviewer`, a dataset (list or iterable of `GoldSample`), and a list of `EvalMetric` instances, runs the reviewer against every sample, applies every metric, and returns an `EvalReport`.

#### Scenario: Run with all defaults

- **WHEN** `EvalRunner(reviewer=Agent(), dataset=load_jsonl("dataset/reference/django_pydantic_v1.jsonl")).run()` is called
- **THEN** the runner uses the default metric set (`DefectRecall`, `NoveltyRate`, `SeverityCalibration`), runs the reviewer on every sample in the dataset, and returns an `EvalReport` with summary metrics + per-sample results

#### Scenario: Run with custom metrics

- **WHEN** an `EvalRunner` is constructed with a custom `metrics=[MyCustomMetric(), DefectRecall()]` list
- **THEN** the runner uses exactly the supplied metric list (no implicit defaults added)

#### Scenario: Run aborts cleanly on per-sample failure

- **WHEN** the reviewer raises on one sample mid-run
- **THEN** the runner logs the failure, marks that sample with an `error` field in the per-sample results, and continues with remaining samples; the final `EvalReport.summary` reflects only the samples that succeeded

### Requirement: EvalRunner records cost and latency per sample

For every sample, the runner SHALL record (a) the LLM cost in USD computed from `Review.usage` × per-token pricing for the reviewer's model, and (b) the wall-clock latency in seconds. Aggregates SHALL be reported in the `EvalReport` summary.

#### Scenario: Cost reported in summary

- **WHEN** `EvalRunner.run()` completes
- **THEN** `report.summary.cost_usd_total` is the sum of per-sample costs and `report.summary.cost_usd_p50` / `cost_usd_p95` are the per-sample percentiles

#### Scenario: Latency reported in summary

- **WHEN** `EvalRunner.run()` completes
- **THEN** `report.summary.latency_seconds_p50` and `latency_seconds_p95` are reported alongside the cost stats

#### Scenario: Per-token pricing not configured

- **WHEN** the reviewer's model is not in the built-in pricing table
- **THEN** cost is reported as `None` for that sample, the summary cost fields are reported as `None` with a `cost_unavailable_reason` explaining the gap, and the run does not fail

### Requirement: EvalMetric is a Protocol with three default implementations

The framework SHALL define an `EvalMetric` Protocol with a single method `score(sample: GoldSample, review: Review) -> MetricResult`, plus three default implementations: `DefectRecall`, `NoveltyRate`, and `SeverityCalibration`.

#### Scenario: User defines a custom metric

- **WHEN** a user defines `class MyMetric: def score(self, sample, review): return MetricResult(name="my_metric", value=0.5, per_sample_detail={...})`
- **THEN** that class satisfies the `EvalMetric` Protocol without inheritance and can be passed to `EvalRunner(metrics=[MyMetric()])`

#### Scenario: DefectRecall computes per-severity breakdown

- **WHEN** `DefectRecall.score(sample, review)` is called on a sample with N gold defects across severities `{critical: 1, important: 2, minor: 3}` where the reviewer flagged 1 critical, 1 important, and 1 minor matching the gold
- **THEN** the `MetricResult.value` is the overall recall (3/6 = 0.5) and `per_sample_detail` includes per-severity hit/miss counts

#### Scenario: NoveltyRate counts unmatched reviewer comments

- **WHEN** the reviewer produced 5 comments on a sample, 2 of which matched gold defects
- **THEN** `NoveltyRate.score(...)` returns `value=0.6` (3 novel / 5 total) with `per_sample_detail` listing the unmatched comments

#### Scenario: SeverityCalibration reports mean signed delta

- **WHEN** `SeverityCalibration.score(sample, review)` is called and the matched comments show the reviewer chose severity 1 step *higher* than gold three times and matched gold severity twice
- **THEN** the `value` is the mean signed delta (`(+1*3 + 0*2) / 5 = +0.6`) and `per_sample_detail` includes the per-match severity pair

### Requirement: EvalReport is JSON-serializable with a stable schema

The framework SHALL produce an `EvalReport` object that is JSON-serializable with a versioned schema. Each report SHALL include `report_schema_version`, `run_id` (UUID), `timestamp`, `agent_config`, `dataset_path` (or `dataset_id`), `summary` (aggregate metrics + cost + latency), and `per_sample` (list of per-sample results with each metric's `per_sample_detail`).

#### Scenario: Serialize and round-trip

- **WHEN** a report is produced and `report.to_json()` is written to disk and `EvalReport.from_json(path)` reads it back
- **THEN** the loaded report has identical content to the original

#### Scenario: Schema-version-mismatch on load

- **WHEN** an `EvalReport.from_json(path)` is called on a file whose `report_schema_version` differs from the loader's supported version
- **THEN** the loader raises `EvalReportSchemaMismatch` with a clear migration hint, rather than silently producing a malformed object

### Requirement: A/B diff renderer compares two reports

The framework SHALL provide a renderer that takes two `EvalReport` instances and produces a column-wise diff showing metric deltas, cost/latency deltas, and per-sample regressions/improvements.

#### Scenario: CLI A/B diff via flag

- **WHEN** `peer eval --dataset ... --baseline path/to/baseline_report.json` is executed
- **THEN** the run produces a new report and prints a diff against the baseline showing per-metric delta (e.g., `DefectRecall: 0.42 → 0.51 (+0.09)`), cost delta, and a count of per-sample regressions/improvements

#### Scenario: Programmatic A/B diff

- **WHEN** `from peer.eval import render_diff; render_diff(report_a, report_b)` is called
- **THEN** the function returns a string (or writes to a passed `io.TextIO`) with the same shape as the CLI diff
