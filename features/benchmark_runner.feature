# peer-10s: benchmark-v01 runtime — MacroscopeLoader, BugBenchmarkRunner,
# and the `peer benchmark` CLI subcommand.

Feature: bug-benchmark runtime — loader, judge, runner, and CLI

  @fast
  Scenario: MacroscopeLoader loads BugSamples from a JSONL file
    Given a temp JSONL with two valid Macroscope-shaped bug rows
    When I construct a MacroscopeLoader pointing at that file
    And I call MacroscopeLoader.load
    Then the returned list has length 2
    And the first BugSample's language equals "python"

  @fast
  Scenario: MacroscopeLoader.load(language="python") filters by language
    Given a temp JSONL with one python bug row and one go bug row
    When I construct a MacroscopeLoader pointing at that file
    And I call MacroscopeLoader.load with language "python"
    Then the returned list has length 1
    And the first BugSample's language equals "python"

  @fast
  Scenario: judge_bug_caught returns True when the LLM responds CAUGHT
    Given a fake judge client that always returns "CAUGHT — overlaps reported line"
    And a BugSample at "src/foo.py":10-12 with root_cause "off-by-one"
    And a peer Comment at "src/foo.py":11
    When I call judge_bug_caught
    Then the returned boolean is True

  @fast
  Scenario: judge_bug_caught short-circuits to False on path mismatch (no judge call)
    Given a fake judge client that records call count
    And a BugSample at "src/foo.py":10-12 with root_cause "off-by-one"
    And a peer Comment at "src/bar.py":11
    When I call judge_bug_caught
    Then the returned boolean is False
    And the judge client was called 0 times

  @fast
  Scenario: judge_bug_caught short-circuits to False on out-of-proximity line (no judge call)
    Given a fake judge client that records call count
    And a BugSample at "src/foo.py":10-12 with root_cause "off-by-one"
    And a peer Comment at "src/foo.py":900
    When I call judge_bug_caught
    Then the returned boolean is False
    And the judge client was called 0 times

  @fast
  Scenario: BugBenchmarkRunner aggregates detection_rate across a 2-bug dataset
    Given a fake bug-judge that catches bug "bug-1" and misses bug "bug-2"
    And a stub PRReviewer that returns one Comment in proximity for both bugs
    And a 2-bug BugDataset with ids "bug-1" and "bug-2"
    When I run BugBenchmarkRunner.run
    Then the BenchmarkReport's n_bugs_total equals 2
    And the BenchmarkReport's n_bugs_caught equals 1
    And the BenchmarkReport's detection_rate equals 0.5
    And the BenchmarkReport's per_bug entries have length 2

  @fast
  Scenario: BugBenchmarkRunner records the reason on a miss
    Given a fake bug-judge that catches bug "bug-1" and misses bug "bug-2"
    And a stub PRReviewer that returns one Comment in proximity for both bugs
    And a 2-bug BugDataset with ids "bug-1" and "bug-2"
    When I run BugBenchmarkRunner.run
    Then the per_bug result for "bug-2" has reason non-empty
    And the per_bug result for "bug-1" has caught equal to True

  @fast
  Scenario: peer benchmark CLI exposes the run subcommand with --dataset / --model / --yes
    When I parse "peer benchmark run --dataset macroscope --model anthropic:claude-sonnet-4-6 --yes"
    Then the parsed args has ds_cmd equal to "run"
    And the parsed args has yes equal to True

  @fast
  Scenario: peer benchmark CLI defaults the dataset to "macroscope"
    When I parse "peer benchmark run --yes"
    Then the parsed args has dataset equal to "macroscope"
