@fast
Feature: Multi-objective recipe verdicts (multi-objective-v01)
  The autoresearch loop currently classifies a recipe with a scalar
  utility. That collapses an honest multi-axis comparison to one
  number — and the choice of formula determines the conclusion.
  RecipeVerdict replaces the scalar primitive with a vector test
  (strict Pareto improvement / strict regression / ambiguous).

  Scenario: classify_comparison returns keep on strict Pareto improvement
    Given a ComparisonReport with verdicts [above_noise, in_noise, in_noise]
    When I call classify_comparison
    Then the RecipeVerdict overall is "keep"
    And the RecipeVerdict n_above_noise is 1
    And the RecipeVerdict n_below_noise is 0

  Scenario: classify_comparison returns discard on strict regression
    Given a ComparisonReport with verdicts [below_noise, in_noise, in_noise]
    When I call classify_comparison
    Then the RecipeVerdict overall is "discard"
    And the RecipeVerdict n_above_noise is 0
    And the RecipeVerdict n_below_noise is 1

  Scenario: classify_comparison returns ambiguous on mixed signal
    Given a ComparisonReport with verdicts [above_noise, below_noise, in_noise]
    When I call classify_comparison
    Then the RecipeVerdict overall is "ambiguous"
    And the RecipeVerdict n_above_noise is 1
    And the RecipeVerdict n_below_noise is 1

  Scenario: classify_comparison returns ambiguous when all metrics are in_noise
    Given a ComparisonReport with verdicts [in_noise, in_noise, in_noise]
    When I call classify_comparison
    Then the RecipeVerdict overall is "ambiguous"

  Scenario: compute_pareto_front excludes dominated entries
    Given two ComparisonReports where report-A has detection_rate 0.10 and comments_per_pr 3.0
    And report-B has detection_rate 0.08 and comments_per_pr 4.0
    When I call compute_pareto_front
    Then the front has length 1
    And the dominated has length 1

  Scenario: compute_pareto_front keeps both when neither dominates
    Given two ComparisonReports where report-A has detection_rate 0.10 and comments_per_pr 5.0
    And report-B has detection_rate 0.08 and comments_per_pr 3.0
    When I call compute_pareto_front
    Then the front has length 2
    And the dominated has length 0

  Scenario: peer autoresearch frontier exits 2 when no comparison files found
    Given an empty reports directory
    When I dispatch peer autoresearch frontier
    Then the autoresearch frontier rc is 2
