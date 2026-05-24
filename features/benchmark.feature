# User-facing behaviors for benchmark-v01 (core schemas only).
# Implementation spec: openspec/changes/benchmark-v01/specs/bug-benchmark/spec.md
# bd issue: peer-61x
# Note: full runner / Macroscope vendoring deferred to follow-up; this commit
# lands the schemas + published-baselines reference table.

Feature: benchmark v01 — BugSample / BugLocation / BenchmarkReport + published_baselines

  @fast
  Scenario: BugLocation Pydantic model validates required fields
    When I construct a BugLocation with path "src/foo.py", start_line 10, end_line 12
    Then the BugLocation's path equals "src/foo.py"
    And the BugLocation's start_line equals 10
    And the BugLocation's end_line equals 12

  @fast
  Scenario: BugSample with two BugLocations validates
    When I construct a BugSample with bug_id "macroscope-001", language "python", and two BugLocations
    Then the BugSample's bug_id equals "macroscope-001"
    And the BugSample has 2 bug_paths
    And the BugSample's line_coordinate_system equals "bug_commit"

  @fast
  Scenario: BugSample with invalid line_coordinate_system raises ValidationError
    When I attempt to construct a BugSample with line_coordinate_system "invalid_value"
    Then a ValidationError is raised

  @fast
  Scenario: PUBLISHED_BASELINES contains Macroscope and CodeRabbit entries
    When I import PUBLISHED_BASELINES from peer.benchmark
    Then PUBLISHED_BASELINES contains a key "macroscope"
    And PUBLISHED_BASELINES contains a key "coderabbit"
    And each baseline entry has a "detection_rate" field

  @fast
  Scenario: BenchmarkReport round-trips through model_dump_json
    When I construct a minimal BenchmarkReport
    Then the BenchmarkReport round-trips through model_dump_json + model_validate_json
    And the BenchmarkReport's dataset_id equals "test-dataset-v0"

  @fast
  Scenario: InvalidBugSample exception is importable
    When I import InvalidBugSample from peer.exceptions
    Then InvalidBugSample is a subclass of PeerError
