# ClaudeCodeCLIReviewer: shells out to the `claude` CLI instead of using
# the Anthropic SDK directly. Lets `peer` run via the user's Claude Code
# subscription auth (OAuth/keychain) without an ANTHROPIC_API_KEY in env.

Feature: ClaudeCodeCLIReviewer — peer driven by the claude CLI

  @fast
  Scenario: Reviewer parses a clean JSON response from the CLI
    Given a fake claude binary returning result text "{\"comments\":[{\"path\":\"src/foo.py\",\"line\":10,\"severity\":\"minor\",\"body\":\"b\",\"rationale\":\"r\"}]}" with cost 0.012
    When I invoke the ClaudeCodeCLIReviewer on a synthetic Context with one hunk on "src/foo.py"
    Then the returned comments list has length 1
    And the first parsed comment's path equals "src/foo.py"
    And the returned usage's "total_cost_usd" equals 0.012

  @fast
  Scenario: Reviewer extracts JSON from a fenced ```json block
    Given a fake claude binary returning result text wrapped in a fenced json block with one comment
    When I invoke the ClaudeCodeCLIReviewer on a synthetic Context with one hunk on "src/foo.py"
    Then the returned comments list has length 1

  @fast
  Scenario: Reviewer extracts JSON when prose precedes the object
    Given a fake claude binary returning result text "Here is the JSON: {\"comments\":[{\"path\":\"src/foo.py\",\"line\":10,\"severity\":\"nit\",\"body\":\"b\",\"rationale\":\"r\"}]} and that's all." with cost 0
    When I invoke the ClaudeCodeCLIReviewer on a synthetic Context with one hunk on "src/foo.py"
    Then the returned comments list has length 1

  @fast
  Scenario: Reviewer returns an empty list when the CLI yields no parseable JSON
    Given a fake claude binary returning result text "I could not find any issues." with cost 0
    When I invoke the ClaudeCodeCLIReviewer on a synthetic Context with one hunk on "src/foo.py"
    Then the returned comments list has length 0

  @fast
  Scenario: Reviewer invokes claude with the expected flags
    Given a fake claude binary that records its argv
    When I invoke the ClaudeCodeCLIReviewer on a synthetic Context with one hunk on "src/foo.py"
    Then the recorded argv contains "--print"
    And the recorded argv contains "--output-format"
    And the recorded argv contains "json"
    And the recorded argv contains "--system-prompt"
    And the recorded argv contains "--model"
    And the recorded argv contains "--disable-slash-commands"

  @fast
  Scenario: Reviewer respects peer.deps.ALLOW_LLM_CALLS=False
    Given peer.deps.ALLOW_LLM_CALLS is set to False
    When the ClaudeCodeCLIReviewer attempts to call its CLI
    Then LLMCallsDisabled is raised

  @fast
  Scenario: Agent dispatches the claude-code provider to ClaudeCodeCLIReviewer
    When I construct an Agent with model "claude-code:sonnet"
    Then the Agent's reviewer is a ClaudeCodeCLIReviewer
    And the Agent's reviewer's model_id equals "sonnet"
