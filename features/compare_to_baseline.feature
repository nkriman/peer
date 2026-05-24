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
