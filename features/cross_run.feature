# cross-run-v01 (peer-x5w):
#   - CrossRunRunner reruns reviewer N times
#   - MultiRunReport per_run + metric_bands
#   - compute_run_bands aggregates
#   - --n-runs CLI flag
#   - --baseline-cmp conflicts with --n-runs 1

Feature: cross-run multi-run averaging

  @fast
  Scenario: CrossRunRunner invokes the reviewer N times across samples
    Given a counting PR-Reviewer and a 2-sample dataset
    When I call CrossRunRunner.run with n_runs 3
    Then the counting reviewer was invoked exactly 6 times

  @fast
  Scenario: MultiRunReport carries N per_run EvalReports
    Given a counting PR-Reviewer and a 1-sample dataset
    When I call CrossRunRunner.run with n_runs 4
    Then the MultiRunReport's per_run has length 4

  @fast
  Scenario: n_runs <= 0 raises ValueError at construction
    Given a counting PR-Reviewer and a 1-sample dataset
    When I attempt to construct a CrossRunRunner with n_runs 0
    Then ValueError is raised

  @fast
  Scenario: compute_run_bands aggregates per-metric values across reruns
    When I call compute_run_bands on per-run detection_rate values [0.04, 0.10, 0.07]
    Then the band's min equals 0.04
    And the band's max equals 0.10
    And the band's median equals 0.07
    And the band's range equals approximately 0.06

  @fast
  Scenario: CLI --baseline-cmp + --n-runs 1 conflict exits non-zero
    When I parse "peer autoresearch run --recipe x.yaml --n-runs 1 --baseline-cmp"
    Then dispatching raises SystemExit with code 2
