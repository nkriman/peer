# Integration: PeerConfig + Linters flow through Agent.run.
# Covers peer-config-v01 follow-up (peer-4d2) + linter-context-v01 follow-up (peer-9su).

Feature: Agent.run consumes PeerDeps.config + PeerDeps.linters end-to-end

  @fast
  Scenario: Agent.run with PeerDeps.config caps comment severity per-path
    Given an Agent with model "anthropic:claude-sonnet-4-6"
    And a PeerDeps with a PeerConfig that caps "src/foo.py" severity at "minor"
    And a TestReviewer that returns one Comment on "src/foo.py" with severity "important"
    When I override the Agent's reviewer with the TestReviewer
    And I call Agent.run with a synthetic PR
    Then the returned Review has 1 comment
    And the returned Review's first comment has severity "minor"

  @fast
  Scenario: Agent.run with PeerDeps.config filters ignored hunks before review
    Given an Agent with model "anthropic:claude-sonnet-4-6"
    And a PeerDeps with a PeerConfig that ignores "vendor/**"
    And a TestReviewer that synthesizes one Comment per hunk
    When I override the Agent's reviewer with the TestReviewer
    And I call Agent.run with a synthetic PR containing hunks for "vendor/lib.py" and "src/app.py"
    Then the returned Review has 1 comment
    And the returned Review's first comment's path equals "src/app.py"

  @fast
  Scenario: gather_codebase_context populates linter_findings from PeerDeps.linters
    Given a fake repo with one Python file
    And a stub Linter returning one fixed LinterFinding
    When I call gather_codebase_context with linters set to the stub Linter
    Then the returned CodebaseContext's linter_findings has length 1
    And the first finding has rule_id "X001"

  @fast
  Scenario: format_prompt renders a LINTER FINDINGS section when present
    Given a Context with one hunk
    And a CodebaseContext with one LinterFinding for that hunk
    When I call format_prompt with both
    Then the rendered prompt contains the literal "## LINTER FINDINGS"
    And the rendered prompt contains the finding's rule_id and message

  @fast
  Scenario: format_prompt omits LINTER FINDINGS section when empty
    Given a Context with one hunk
    And a CodebaseContext with no LinterFindings
    When I call format_prompt with both
    Then the rendered prompt does NOT contain the literal "## LINTER FINDINGS"
