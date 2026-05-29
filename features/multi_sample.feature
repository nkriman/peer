@fast
Feature: MultiSampleReviewer (multi-sample-v01)
  Calls the inner reviewer K times at non-zero temperature and returns
  the deduplicated union of all comments. Implements the SWR-Bench /
  Codex-Verify result that independent multi-sampling lifts recall by
  surfacing complementary defects across samples.

  Scenario: K=5 invokes the inner reviewer exactly 5 times
    Given a MultiSampleReviewer with a counting inner reviewer and k=5
    When I invoke MultiSampleReviewer.review
    Then the counting reviewer was invoked exactly 5 times

  Scenario: K=1 short-circuits to a single inner call
    Given a MultiSampleReviewer with a counting inner reviewer and k=1
    When I invoke MultiSampleReviewer.review
    Then the counting reviewer was invoked exactly 1 times

  Scenario: Identical comments across samples are deduplicated to one
    Given a MultiSampleReviewer with an inner returning the same comment every time and k=3
    When I invoke MultiSampleReviewer.review
    Then the returned multi-sample comments list has length 1

  Scenario: Distinct comments by line or body are all kept
    Given a MultiSampleReviewer with an inner returning 3 distinct comments across 3 calls and k=3
    When I invoke MultiSampleReviewer.review
    Then the returned multi-sample comments list has length 3

  Scenario: Usage sums across K calls
    Given a MultiSampleReviewer with an inner returning usage 100/20/0.01 and k=3
    When I invoke MultiSampleReviewer.review
    Then the returned multi-sample usage input_tokens is 300
    And the returned multi-sample usage output_tokens is 60
    And the returned multi-sample usage total_cost_usd is 0.030

  Scenario: Constructing with k=0 raises ValueError
    When I attempt to construct a MultiSampleReviewer with k=0
    Then ValueError is raised

  Scenario: Registry resolves "multi_sample" to MultiSampleReviewer
    When I call resolve_strategy with "multi_sample"
    Then the returned class is MultiSampleReviewer
