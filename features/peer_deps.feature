# User-facing behaviors for peer-deps-v01.
# Implementation spec: openspec/changes/peer-deps-v01/specs/{peer-deps,pr-review-agent}/spec.md
# bd issue: peer-cgg

Feature: peer-deps v01 — typed runtime deps + testing primitives + provider:model

  @fast
  Scenario: PeerDeps default construction
    When I construct a PeerDeps with no arguments
    Then the PeerDeps has config equal to None
    And the PeerDeps has classifier equal to None
    And the PeerDeps has linters equal to the empty list
    And the PeerDeps has extra_instructions equal to None

  @fast
  Scenario: PeerDeps populated with fields
    When I construct a PeerDeps with extra_instructions "focus on security"
    Then the PeerDeps's extra_instructions equals "focus on security"

  @fast
  Scenario: RunContext carries typed deps
    Given a PeerDeps instance with extra_instructions "foo"
    When I construct a RunContext with that PeerDeps and pr_url "https://example/pull/1"
    Then the RunContext's deps.extra_instructions equals "foo"
    And the RunContext's attempt equals 0
    And the RunContext does NOT have a "metadata" field

  @fast
  Scenario: ALLOW_LLM_CALLS=False blocks real Reviewers
    Given peer.deps.ALLOW_LLM_CALLS is set to False
    When the real ClaudeReviewer attempts to call its LLM
    Then LLMCallsDisabled is raised
    And the error message references "Agent.override(reviewer=TestReviewer())"

  @fast
  Scenario: ALLOW_LLM_CALLS=False does NOT block TestReviewer
    Given peer.deps.ALLOW_LLM_CALLS is set to False
    When the TestReviewer is invoked
    Then no exception is raised

  @fast
  Scenario: TestReviewer fixed-comments mode
    Given a TestReviewer constructed with one fixed Comment
    When I call review on a Context with a single hunk
    Then the returned comments list equals the fixed list
    And the returned usage has model "test"

  @fast
  Scenario: TestReviewer synthesized-comments mode
    Given a TestReviewer constructed with n_comments 2 and severity "nit"
    When I call review on a Context with three hunks
    Then the returned comments list has length 2
    And each returned comment has severity "nit"

  @fast
  Scenario: Provider:model canonical format
    When I construct an Agent with model "anthropic:claude-sonnet-4-6"
    Then the Agent's model attribute equals "anthropic:claude-sonnet-4-6"
    And no DeprecationWarning is emitted

  @fast
  Scenario: Legacy bare model name triggers DeprecationWarning
    When I construct an Agent with model "claude-sonnet-4-6"
    Then a DeprecationWarning is emitted referencing "anthropic:claude-sonnet-4-6"
    And the Agent's model attribute equals "anthropic:claude-sonnet-4-6"

  @fast
  Scenario: Unknown provider raises UnknownModelError
    When I attempt to construct an Agent with model "unknown:xyz"
    Then UnknownModelError is raised

  @fast
  Scenario: Agent.override swaps reviewer for the block
    Given an Agent constructed with model "anthropic:claude-sonnet-4-6"
    When I enter Agent.override with a TestReviewer and exit cleanly
    Then during the block the Agent's reviewer is a TestReviewer
    And after the block the Agent's reviewer is the original ClaudeReviewer

  @fast
  Scenario: Agent.override restores reviewer on exception
    Given an Agent constructed with model "anthropic:claude-sonnet-4-6"
    When I enter Agent.override with a TestReviewer and raise RuntimeError inside
    Then the RuntimeError propagates out of the block
    And the Agent's reviewer after the block is the original ClaudeReviewer

  @fast
  Scenario: Nested overrides stack and restore in reverse order
    Given an Agent constructed with model "anthropic:claude-sonnet-4-6"
    When I nest two Agent.override blocks with two distinct TestReviewers
    Then during the inner block the Agent's reviewer is the inner TestReviewer
    And after the inner block exits the Agent's reviewer is the outer TestReviewer
    And after the outer block exits the Agent's reviewer is the original ClaudeReviewer

  @fast
  Scenario: Agent.run(pr_url, deps) is the new canonical entry
    Given an Agent constructed with model "anthropic:claude-sonnet-4-6"
    And a TestReviewer that returns one fixed Comment
    When I override the Agent's reviewer with the TestReviewer
    And I call Agent.run with pr_url "https://github.com/test/test/pull/1" and a PeerDeps
    Then the returned Review's comments list has length 1
