# peer-40y: eval-v02 follow-ups —
#   - case-specific evaluators on GoldSample
#   - EvalRunner.run_async with bounded concurrency
#   - --with-rationale-grounding / --no-rationale-grounding CLI flag

Feature: eval-v02 follow-ups — case-specific evaluators, async runner, rationale CLI

  @fast
  Scenario: GoldSample accepts case-specific evaluators
    When I construct a GoldSample with two case-specific evaluators
    Then the GoldSample's evaluators list has length 2
    And the first case-specific evaluator's name equals "test_a"
    And the second case-specific evaluator's name equals "test_b"

  @fast
  Scenario: GoldSample default evaluators list is empty
    When I construct a minimal GoldSample
    Then the GoldSample's evaluators list is the empty list

  @fast
  Scenario: EvalRunner runs case-specific evaluators alongside dataset-wide ones
    Given a TestReviewer that returns one Comment on "src/foo.py"
    And a GoldSample with one case-specific recording evaluator
    And an EvalRunner constructed with the TestReviewer + that GoldSample + one dataset-wide recording evaluator
    When I call EvalRunner.run
    Then the dataset-wide recording evaluator was invoked exactly 1 time
    And the case-specific recording evaluator was invoked exactly 1 time

  @fast
  Scenario: EvalRunner.run_async exists and returns the same EvalReport shape as run
    Given a TestReviewer that returns one Comment on "src/foo.py"
    And an EvalRunner constructed with the TestReviewer + one GoldSample
    When I call EvalRunner.run_async with concurrency 1
    Then the returned EvalReport has 1 per_sample result
    And the EvalReport's run_id is non-empty

  @fast
  Scenario: EvalRunner.run_async with concurrency >1 runs reviewer calls in parallel
    Given a SlowTestReviewer that sleeps 50ms before returning one Comment on "src/foo.py"
    And an EvalRunner constructed with that SlowTestReviewer + 4 GoldSamples
    When I call EvalRunner.run_async with concurrency 4
    Then the wall-clock duration was below 0.15 seconds

  @fast
  Scenario: peer eval CLI exposes a --with-rationale-grounding flag
    When I parse "peer eval --dataset x.jsonl --with-rationale-grounding"
    Then the parsed args has with_rationale_grounding equal to True

  @fast
  Scenario: peer eval CLI exposes a --no-rationale-grounding flag (default off)
    When I parse "peer eval --dataset x.jsonl --no-rationale-grounding"
    Then the parsed args has with_rationale_grounding equal to False

  @fast
  Scenario: peer eval CLI defaults --with-rationale-grounding to off (opt-in)
    When I parse "peer eval --dataset x.jsonl"
    Then the parsed args has with_rationale_grounding equal to False

  @fast
  Scenario: peer eval CLI exposes a --concurrency flag with default 5
    When I parse "peer eval --dataset x.jsonl"
    Then the parsed args has concurrency equal to 5
