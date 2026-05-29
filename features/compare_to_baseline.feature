# cross-run-v01 (peer-x5w):
#   - compare_to_baseline classifies recipe vs baseline as above/in/below noise

Feature: compare_to_baseline verdict

  @fast
  Scenario: recipe beats baseline beyond the noise floor
    When I call compare_to_baseline with recipe detection_rate median 0.15 and baseline median 0.04 and noise_floor 0.06
    Then the comparison's detection_rate verdict equals "above_noise"
    And the comparison's detection_rate delta equals approximately 0.11

  @fast
  Scenario: recipe is in the noise band
    When I call compare_to_baseline with recipe detection_rate median 0.08 and baseline median 0.05 and noise_floor 0.06
    Then the comparison's detection_rate verdict equals "in_noise"
    And the comparison's detection_rate delta equals approximately 0.03

  @fast
  Scenario: recipe regresses beyond the noise floor
    When I call compare_to_baseline with recipe detection_rate median 0.02 and baseline median 0.15 and noise_floor 0.06
    Then the comparison's detection_rate verdict equals "below_noise"
    And the comparison's detection_rate delta equals approximately -0.13

  @fast
  Scenario: lower-is-better metric (comments_per_pr) — recipe REGRESSES when median rises
    When I call compare_to_baseline with recipe comments_per_pr median 10.0 and baseline median 4.0 and noise_floor 0.5
    Then the comparison's comments_per_pr verdict equals "below_noise"
    And the comparison's comments_per_pr delta equals approximately 6.0

  @fast
  Scenario: lower-is-better metric (comments_per_pr) — recipe WINS when median falls
    When I call compare_to_baseline with recipe comments_per_pr median 1.5 and baseline median 4.0 and noise_floor 0.5
    Then the comparison's comments_per_pr verdict equals "above_noise"
    And the comparison's comments_per_pr delta equals approximately -2.5

  @fast
  Scenario: bootstrap CI gate returns in_noise when CI straddles zero
    Given recipe detection_rate per-run values [0.10, 0.11, 0.09] and baseline per-run values [0.08, 0.09, 0.10]
    When I call compare_to_baseline_ci
    Then the comparison's detection_rate verdict equals "in_noise"
    And the comparison's detection_rate has a CI populated

  @fast
  Scenario: bootstrap CI gate returns above_noise when CI excludes zero
    Given recipe detection_rate per-run values [0.30, 0.32, 0.31] and baseline per-run values [0.05, 0.06, 0.07]
    When I call compare_to_baseline_ci
    Then the comparison's detection_rate verdict equals "above_noise"
    And the comparison's detection_rate has a CI populated

  @fast
  Scenario: paired bootstrap returns above_noise on per-PR detection_rate when lift is large and consistent
    Given recipe and baseline each have one run with per-PR detection_rate pairs:
      | pr_url | recipe | baseline |
      | pr-1   | 0.40   | 0.10     |
      | pr-2   | 0.45   | 0.05     |
      | pr-3   | 0.50   | 0.15     |
      | pr-4   | 0.55   | 0.10     |
      | pr-5   | 0.60   | 0.20     |
      | pr-6   | 0.50   | 0.10     |
    When I call compare_to_baseline_paired_bootstrap
    Then the comparison's detection_rate verdict equals "above_noise"
    And the comparison's detection_rate has a CI populated

  @fast
  Scenario: paired bootstrap with BCa+permutation requires BOTH tests to pass
    Given recipe and baseline each have one run with per-PR detection_rate pairs:
      | pr_url | recipe | baseline |
      | pr-1   | 0.40   | 0.10     |
      | pr-2   | 0.45   | 0.05     |
      | pr-3   | 0.50   | 0.15     |
      | pr-4   | 0.55   | 0.10     |
      | pr-5   | 0.60   | 0.20     |
      | pr-6   | 0.50   | 0.10     |
      | pr-7   | 0.40   | 0.15     |
      | pr-8   | 0.55   | 0.05     |
    When I call compare_to_baseline_paired_bootstrap with BCa and permutation
    Then the comparison's detection_rate verdict equals "above_noise"
    And the comparison's detection_rate has a CI populated
    And the comparison's detection_rate has a permutation pvalue below 0.05

  @fast
  Scenario: paired bootstrap with BCa+permutation returns in_noise when permutation fails to reach significance
    Given recipe and baseline each have one run with per-PR detection_rate pairs:
      | pr_url | recipe | baseline |
      | pr-1   | 0.20   | 0.18     |
      | pr-2   | 0.15   | 0.22     |
      | pr-3   | 0.30   | 0.10     |
      | pr-4   | 0.10   | 0.25     |
    When I call compare_to_baseline_paired_bootstrap with BCa and permutation
    Then the comparison's detection_rate verdict equals "in_noise"

  @fast
  Scenario: paired bootstrap returns in_noise when paired diffs straddle zero
    Given recipe and baseline each have one run with per-PR detection_rate pairs:
      | pr_url | recipe | baseline |
      | pr-1   | 0.20   | 0.18     |
      | pr-2   | 0.15   | 0.22     |
      | pr-3   | 0.30   | 0.10     |
      | pr-4   | 0.10   | 0.25     |
      | pr-5   | 0.25   | 0.15     |
      | pr-6   | 0.18   | 0.20     |
    When I call compare_to_baseline_paired_bootstrap
    Then the comparison's detection_rate verdict equals "in_noise"
    And the comparison's detection_rate has a CI populated
