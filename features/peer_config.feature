# User-facing behaviors for peer-config-v01.
# Implementation spec: openspec/changes/peer-config-v01/specs/peer-config/spec.md
# bd issue: peer-85c

Feature: peer-config v01 — .peer.yaml with per-path conventions + severity bounds + ignore

  @fast
  Scenario: Empty PeerConfig is valid + has no rules
    When I construct a PeerConfig with no arguments
    Then the PeerConfig's rules list is empty
    And the PeerConfig's ignore.glob is the empty list

  @fast
  Scenario: PeerConfig.for_path returns empty ResolvedRule for unmatched paths
    Given a PeerConfig with no rules
    When I call for_path on "src/foo.py"
    Then the resolved rule has no conventions_text
    And the resolved rule has no severity_floor
    And the resolved rule has no severity_cap

  @fast
  Scenario: PeerConfig.for_path collects ALL matching rules' conventions
    Given a PeerConfig with rule A matching "src/**" with conventions "rule-a-text"
    And rule B matching "src/auth/**" with conventions "rule-b-text"
    When I call for_path on "src/auth/login.py"
    Then the resolved rule's conventions_texts equals ["rule-a-text", "rule-b-text"]

  @fast
  Scenario: severity_cap caps the agent's severity at the most-restrictive matching rule
    Given a PeerConfig with rule "tests/**" severity_cap minor and rule "**" severity_cap critical
    When I apply severity bounds to a Comment with path "tests/test_foo.py" and severity "important"
    Then the resulting Comment's severity equals "minor"

  @fast
  Scenario: severity_floor raises the severity at the most-restrictive matching rule
    Given a PeerConfig with rule "src/auth/**" severity_floor important
    When I apply severity bounds to a Comment with path "src/auth/login.py" and severity "minor"
    Then the resulting Comment's severity equals "important"

  @fast
  Scenario: ignore.glob excludes matching files from Context
    Given a PeerConfig with ignore.glob ["vendor/**", "build/**"]
    And a Context with hunks for "vendor/lib.py" and "src/foo.py"
    When I apply ignore filters
    Then the filtered Context has 1 hunk
    And the remaining hunk's path equals "src/foo.py"

  @fast
  Scenario: load_config finds .peer.yaml in the given directory
    Given a temp directory containing a .peer.yaml with content "version: 1\nagent:\n  extra_instructions: \"focus on security\"\n"
    When I call load_config on that directory
    Then the loaded PeerConfig's agent.extra_instructions equals "focus on security"

  @fast
  Scenario: load_config returns empty PeerConfig when no .peer.yaml exists
    Given a temp directory with no .peer.yaml
    When I call load_config on that directory
    Then the loaded PeerConfig has no rules
