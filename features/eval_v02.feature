# User-facing behaviors for eval-v02.
# Implementation spec: openspec/changes/eval-v02/specs/eval-runner/spec.md
# bd issue: peer-aro

Feature: eval-v02 — flexible MetricResult + LLMJudge + RationaleGrounding (opt-in)

  @fast
  Scenario: MetricResult.value accepts bool
    When I construct a MetricResult with value True
    Then the MetricResult's value is the bool True

  @fast
  Scenario: MetricResult.value accepts a dict
    When I construct a MetricResult with value {"a": 0.5, "b": "good"}
    Then the MetricResult's value is the dict {"a": 0.5, "b": "good"}

  @fast
  Scenario: AggregateKind enum is importable and has the expected members
    When I import AggregateKind
    Then AggregateKind has members MEAN SUM_OF_SUMS PASS_RATE PER_TIER LATENCY_PERCENTILE

  @fast
  Scenario: Custom metric with explicit aggregate_kind
    Given a custom metric class with name "x" and aggregate_kind PASS_RATE
    Then the metric's aggregate_kind equals AggregateKind.PASS_RATE

  @fast
  Scenario: LLMJudge is a configurable Evaluator dataclass
    When I construct an LLMJudge with rubric "test rubric"
    Then the LLMJudge's rubric equals "test rubric"
    And the LLMJudge's include_input is False
    And the LLMJudge's include_expected_output is True
    And the LLMJudge's include_reason is True

  @fast
  Scenario: judge_match still works as a back-compat wrapper
    When I import judge_match from peer.eval
    Then judge_match is callable

  @fast
  Scenario: RationaleGrounding is NOT in the default metric set
    When I construct an EvalRunner with default metrics
    Then the default metrics list does NOT contain RationaleGrounding
