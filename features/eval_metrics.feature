# User-facing behaviors for eval-metrics-v01.
# Implementation spec: openspec/changes/eval-metrics-v01/specs/eval-runner/spec.md
# bd issue: peer-efm

Feature: Eval-metrics v01 — industry-aligned headline metrics

  Background:
    Given a synthetic dataset of three GoldSamples covering varied gold-defect counts
    And a stub Reviewer that returns deterministic Comments per sample

  @fast
  Scenario: Default EvalRunner includes the new headline metrics
    When the EvalRunner runs against the synthetic dataset with default metrics
    Then the resulting EvalReport's summary metric_values includes "detection_rate"
    And the summary metric_values includes "comments_per_pr"
    And the summary metric_values includes "precision_per_severity"
    And the summary metric_values includes "mean_per_pr_recall"

  @fast
  Scenario: DetectionRate uses sum-of-sums aggregation
    Given a dataset where samples have matched_count [2, 0, 1] and total_gold [10, 0, 5]
    When the EvalRunner runs with only DetectionRate
    Then the aggregate detection_rate value equals 0.2

  @fast
  Scenario: CommentsPerPR reports mean comments per sample
    Given a dataset where the stub Reviewer emits [1, 3, 5, 2, 0] comments across five samples
    When the EvalRunner runs with only CommentsPerPR
    Then the aggregate comments_per_pr value equals 2.2

  @fast
  Scenario: DefectRecall is a deprecated alias for MeanPerPRRecall
    When I instantiate DefectRecall directly
    Then a DeprecationWarning is emitted referencing MeanPerPRRecall
    And the instantiated metric reports under the name "defect_recall"

  @fast
  Scenario: render_summary leads with the Headline section
    Given an EvalReport produced from the default metric set
    When I render the summary as a string
    Then the output contains a "Headline:" section before any "Secondary:" section
    And the "Secondary:" section's "mean_per_pr_recall" line includes a Simpson's-paradox caveat

  @fast
  Scenario: Agent's team_conventions wrapper does not prescribe a global severity
    When I construct an Agent with team_conventions="Some convention text"
    Then the agent's system_prompt contains "Some convention text"
    And the agent's system_prompt does NOT contain the phrase "nit or minor"
