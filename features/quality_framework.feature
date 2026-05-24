# Smoke feature so `behave --tags=@fast` has something to execute even before
# scripts/extract_features.py is wired up against every openspec change.
# Real scenarios for capabilities live in auto-extracted files (eval-runner.feature,
# dataset-curation.feature, etc.). This file documents the framework itself.

Feature: Quality framework smoke

  @fast
  Scenario: behave is wired and runnable
    Given a freshly constructed quality framework
    When no action is taken
    Then no error is raised
