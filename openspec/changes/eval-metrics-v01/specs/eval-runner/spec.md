## ADDED Requirements

### Requirement: DetectionRate metric computes sum-of-sums recall

The framework SHALL ship a `DetectionRate` implementation of `EvalMetric` that computes `(sum of matched_count across samples) / (sum of total_gold across samples)` and returns it as the metric value.

#### Scenario: Single-value output

- **WHEN** `DetectionRate.score(sample, review)` is called on a single sample with `matched_count=2` and `total_gold=10`
- **THEN** the per-sample `MetricResult.value` is `0.2` and `per_sample_detail` contains `matched_count=2`, `total_gold=10`

#### Scenario: Aggregate computed correctly across samples

- **WHEN** `EvalRunner.run()` completes a run over 3 samples with `matched_count` of `[1, 0, 2]` and `total_gold` of `[10, 0, 5]`
- **THEN** the aggregate `metric_values["detection_rate"]` is `3 / 15 = 0.2`
- **AND** the `metric_details["detection_rate"]` includes `total_matches=3`, `total_gold=15`, `n_samples_with_gold=2`

#### Scenario: Zero gold across all samples

- **WHEN** the dataset contains no gold defects at all
- **THEN** the aggregate `metric_values["detection_rate"]` is `None` with a `notes` field explaining no gold defects exist

### Requirement: CommentsPerPR metric reports peer comment volume

The framework SHALL ship a `CommentsPerPR` implementation that records the number of peer comments per sample and reports mean + median aggregates.

#### Scenario: Mean and median reported

- **WHEN** `EvalRunner.run()` completes a run over samples with peer comment counts `[1, 3, 5, 2, 0]`
- **THEN** the aggregate `metric_values["comments_per_pr"]` is the mean `2.2`
- **AND** `metric_details["comments_per_pr"]` includes `median=2.0`, `min=0`, `max=5`

### Requirement: PrecisionPerSeverity metric quantifies severity calibration

The framework SHALL ship a `PrecisionPerSeverity` implementation that, for each severity tier, computes `(peer comments at that severity that matched a gold defect) / (peer comments at that severity, total)` and returns the per-tier dictionary in `per_sample_detail`.

#### Scenario: Per-tier precision reported

- **WHEN** peer produced 4 comments across one sample: 1 critical (matched gold), 2 important (1 matched), 1 minor (not matched)
- **THEN** the per-sample `per_sample_detail` includes `{"critical": {"precision": 1.0, "n": 1}, "important": {"precision": 0.5, "n": 2}, "minor": {"precision": 0.0, "n": 1}}`

#### Scenario: Aggregate across samples uses sum-of-sums

- **WHEN** `EvalRunner.run()` completes and across all samples the totals are `critical: 1 matched / 1 total`, `important: 2 matched / 7 total`, `minor: 3 matched / 12 total`, `nit: 0 matched / 0 total`
- **THEN** the aggregate `metric_values["precision_per_severity"]` is `None` (not a single number — peek at `metric_details`)
- **AND** `metric_details["precision_per_severity"]` includes the per-tier `{precision, n}` aggregates and omits `nit` (n=0)

### Requirement: MeanPerPRRecall is the canonical name for the legacy mean-of-rates metric

The metric formerly named `DefectRecall` SHALL be renamed `MeanPerPRRecall`. The `DefectRecall` name SHALL remain available as a deprecated alias for one minor version. The new name's docstring SHALL explicitly warn about Simpson's paradox when gold counts vary across samples.

#### Scenario: New name works

- **WHEN** a user instantiates `MeanPerPRRecall()` and passes it to `EvalRunner(metrics=[MeanPerPRRecall()])`
- **THEN** the metric runs identically to the prior `DefectRecall` and reports under the name `mean_per_pr_recall`

#### Scenario: Deprecated alias works with warning

- **WHEN** a user instantiates `DefectRecall()`
- **THEN** the metric runs identically (under name `defect_recall` for back-compat) and a `DeprecationWarning` is emitted pointing at `MeanPerPRRecall`

### Requirement: Default metric set updated

`EvalRunner` with no explicit `metrics=` argument SHALL use the following default metric list in this order: `[DetectionRate(), CommentsPerPR(), PrecisionPerSeverity(), MeanPerPRRecall(), NoveltyRate(), SeverityCalibration()]`.

#### Scenario: Default run produces all six metrics

- **WHEN** `EvalRunner(reviewer, dataset).run()` is called with default metrics
- **THEN** the returned `EvalReport.summary.metric_values` contains keys `detection_rate`, `comments_per_pr`, `precision_per_severity`, `mean_per_pr_recall`, `novelty_rate`, `severity_calibration`

### Requirement: render_summary leads with the industry-aligned trio

`render_summary(report)` SHALL render `detection_rate`, `comments_per_pr`, and `precision_per_severity` in a "Headline" section at the top of the output, and SHALL render `mean_per_pr_recall`, `novelty_rate`, and `severity_calibration` in a "Secondary" section with an explicit caveat note on `mean_per_pr_recall`.

#### Scenario: Headline section appears first

- **WHEN** `render_summary(report)` is called on a report with all six default metrics
- **THEN** the output contains a `Headline:` section before any `Secondary:` section
- **AND** the `mean_per_pr_recall` line includes a caveat string mentioning "Simpson's paradox" (or equivalent) so users don't read it as the headline number

### Requirement: A/B diff handles missing metrics from old reports

`render_diff(baseline, current)` SHALL render `<missing> → <value>` (or similar) for metrics present in the current report but absent from the baseline report, without raising.

#### Scenario: Old baseline without new metrics

- **WHEN** `render_diff(baseline_report_without_detection_rate, current_report_with_detection_rate)` is called
- **THEN** the output shows `detection_rate: (not in baseline) → 0.079` rather than crashing

## MODIFIED Requirements

### Requirement: Default reviewer-prompt wrapper for team_conventions

The current `Agent.__init__` wraps the supplied `team_conventions` text with an instruction that includes severity guidance: *"Treat departures from these conventions as defects (at appropriate severity — usually nit or minor for pure style)."* This SHALL be replaced with a softer wrapping that omits the severity prescription.

#### Scenario: Softer wrapping removes severity directive

- **WHEN** `Agent(team_conventions="...")` is instantiated
- **THEN** the resulting `self.system_prompt` includes the conventions text under a labeled section
- **AND** the wrapping text does NOT contain the phrase "nit or minor" or any other severity prescription
- **AND** the wrapping text directs the model to "flag departures from these conventions as defects" and "infer severity from the convention's framing"
