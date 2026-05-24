# autoresearch-eval-as-mutator-v01 (peer-l6l):
#   - diagnose module: pure extractors over EvalReport
#   - render_markdown produces deterministic hypothesis document
#   - `peer autoresearch diagnose` CLI writes hypothesis to disk

Feature: autoresearch diagnose — extract failure modes from EvalReports

  @fast
  Scenario: extract_failure_modes aggregates unmatched_gold by severity
    Given a synthetic EvalReport with 3 samples and unmatched_gold severity counts [important=5; critical=1, minor=2; important=1, nit=3]
    When I call extract_failure_modes
    Then the returned FailureSummary's per-severity totals equal {critical: 1, important: 6, minor: 2, nit: 3}
    And the FailureSummary's n_samples_with_misses equals 3

  @fast
  Scenario: extract_topic_drift surfaces samples where peer commented but matched nothing
    Given a synthetic EvalReport with 1 sample where peer emitted 3 comments and matched 0 gold defects
    When I call extract_topic_drift
    Then the TopicDriftSummary has 1 sample in drift_samples

  @fast
  Scenario: extract_cost_outliers ranks by cost descending
    Given a synthetic EvalReport whose per-sample costs are [0.02, 0.05, 0.10, 0.03]
    When I call extract_cost_outliers with n_top 2
    Then the CostOutlierSummary's top has cost 0.10 first
    And the CostOutlierSummary's top has cost 0.05 second

  @fast
  Scenario: extract_precision_misses returns unmatched peer comments
    Given a synthetic EvalReport with 1 sample where peer emitted 4 comments and matched 1 gold
    When I call extract_precision_misses
    Then the returned list has length 3

  @fast
  Scenario: render_markdown emits the expected section headers
    Given populated diagnose inputs
    When I call render_markdown
    Then the rendered output contains "# Hypothesis"
    And the rendered output contains "## Headline"
    And the rendered output contains "## Failure modes by severity"
    And the rendered output contains "## Topic drift"
    And the rendered output contains "## Cost outliers"
    And the rendered output contains "## Precision concerns"
    And the rendered output contains "## Suggested mutation axes"

  @fast
  Scenario: render_markdown is deterministic
    Given populated diagnose inputs
    When I call render_markdown twice
    Then the two outputs are byte-equal
