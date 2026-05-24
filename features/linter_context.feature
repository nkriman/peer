# User-facing behaviors for linter-context-v01.
# Implementation spec: openspec/changes/linter-context-v01/specs/linter-context/spec.md
# bd issue: peer-yty

Feature: linter-context v01 — Linter Protocol + RuffLinter + CodebaseContext.linter_findings

  @fast
  Scenario: LinterFinding round-trips through Pydantic
    When I construct a LinterFinding with all required fields
    Then the LinterFinding round-trips through model_dump_json + model_validate_json

  @fast
  Scenario: CodebaseContext gains linter_findings field defaulting to empty list
    When I construct an empty CodebaseContext
    Then the CodebaseContext's linter_findings is the empty list

  @fast
  Scenario: A custom Linter satisfies the Protocol
    Given a custom Linter class returning two fixed findings
    When I call lint on a fake repo with a single target file
    Then the returned list has length 2
    And each finding has linter equal to "custom"

  @fast
  Scenario: RuffLinter gracefully degrades when ruff is missing from PATH
    Given the ruff CLI is unavailable on PATH
    When I call RuffLinter().lint on a repo with one Python file
    Then the returned list is empty
    And a one-time WARNING log mentions ruff installation

  @fast
  Scenario: RuffLinter parses ruff JSON output into LinterFindings
    Given a stub subprocess.run that returns ruff JSON output with one E501 finding
    When I call RuffLinter().lint on a repo with one Python file
    Then the returned list has length 1
    And the first finding has rule_id "E501"
    And the first finding has linter "ruff"
    And the first finding has severity "nit"

  @fast
  Scenario: RuffLinter severity_map override
    Given a stub subprocess.run that returns ruff JSON output with one S101 finding
    When I call RuffLinter(severity_map={"S": "critical"}).lint on a repo
    Then the first finding has severity "critical"
