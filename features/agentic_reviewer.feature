# agentic-reviewer-v01 (peer-4vn):
#   - AgenticReviewer routes through claude CLI with tools ENABLED
#   - argv contains --allowedTools + --max-turns, NO --disallowedTools
#   - parses structured_output then prose fallback
#   - registry resolves "agentic" short name
#   - Recipe wiring

Feature: AgenticReviewer — claude with its own tools enabled

  @fast
  Scenario: argv contains --allowedTools and --max-turns and no --disallowedTools
    Given a fake claude binary that records its argv and returns empty comments
    When I invoke AgenticReviewer with allowed_tools "Read,Grep" and max_turns 8
    Then the recorded argv contains "--allowedTools=Read,Grep"
    And the recorded argv contains "--max-turns"
    And the recorded argv contains "8"
    And the recorded argv does NOT contain "--disallowedTools"

  @fast
  Scenario: structured_output parses to Comments
    Given a fake claude binary returning structured_output with one comment on "src/foo.py"
    When I invoke AgenticReviewer with default tools
    Then the returned agentic comments list has length 1
    And the first agentic comment's path equals "src/foo.py"

  @fast
  Scenario: prose fallback parses fenced JSON when structured_output is empty
    Given a fake claude binary returning the comments JSON wrapped in a fenced json block
    When I invoke AgenticReviewer with default tools
    Then the returned agentic comments list has length 1

  @fast
  Scenario: ALLOW_LLM_CALLS=False blocks the AgenticReviewer call
    Given peer.deps.ALLOW_LLM_CALLS is set to False
    When the AgenticReviewer attempts to call its CLI
    Then LLMCallsDisabled is raised

  @fast
  Scenario: registry resolves "agentic" to AgenticReviewer
    When I call resolve_strategy with "agentic"
    Then the returned class is AgenticReviewer

  @fast
  Scenario: Recipe with reviewer_dotted_path "agentic" yields an AgenticReviewer
    Given a Recipe with reviewer_dotted_path "agentic" and reviewer_kwargs max_turns 5
    When I apply the recipe to a fresh Agent
    Then the Agent's reviewer is an AgenticReviewer
    And the Agent's reviewer's max_turns equals 5
