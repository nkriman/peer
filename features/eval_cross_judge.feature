# eval-cross-judge-v01 (peer-iaj):
#   - CrossJudgeRunner re-judges cached reviews against N judge models
#   - CrossJudgeReport computes variance bands per metric
#   - `peer eval --cross-judge` CLI flag wires it
#   - render_cross_judge_summary flags high variance

Feature: cross-judge variance — re-judge once, measure noise

  @fast
  Scenario: reviewer runs once across N judges
    Given a counting PR-Reviewer and a 2-sample dataset
    When I call CrossJudgeRunner.run with judge_models ["sonnet","haiku","opus"]
    Then the counting reviewer was invoked exactly 2 times

  @fast
  Scenario: each judge's metrics are computed independently
    Given a counting PR-Reviewer and a 1-sample dataset
    And a recording per-judge stub that scores differently for sonnet vs haiku
    When I call CrossJudgeRunner.run with judge_models ["sonnet","haiku"]
    Then the report's per_judge has length 2
    And the per_judge["sonnet"] detection_rate differs from per_judge["haiku"] detection_rate

  @fast
  Scenario: variance bands computed across 3 judges
    When I call compute_variance_bands on per-judge detection_rate values [0.10, 0.04, 0.07]
    Then the band's min equals 0.04
    And the band's max equals 0.10
    And the band's median equals 0.07
    And the band's range equals approximately 0.06
    And the band's n_judges_included equals 3

  @fast
  Scenario: None values are excluded from the band
    When I call compute_variance_bands on per-judge detection_rate values [0.10, None, 0.07]
    Then the band's min equals 0.07
    And the band's max equals 0.10
    And the band's n_judges_included equals 2

  @fast
  Scenario: render_cross_judge_summary flags high variance
    Given a CrossJudgeReport with detection_rate band min 0.02 and max 0.10
    When I call render_cross_judge_summary
    Then the rendered output contains "HIGH VARIANCE"

  @fast
  Scenario: render_cross_judge_summary does NOT flag low variance
    Given a CrossJudgeReport with detection_rate band min 0.08 and max 0.10
    When I call render_cross_judge_summary
    Then the rendered output does NOT contain "HIGH VARIANCE"

  @fast
  Scenario: CLI refuses --cross-judge combined with --baseline
    When I parse "peer eval --dataset x.jsonl --cross-judge sonnet,haiku --baseline old.json"
    Then parsing raises SystemExit
