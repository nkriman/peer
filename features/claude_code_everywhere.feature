# claude-code-everywhere-v01 (peer-0jy):
#   - ClaudeCodeShimClient with SDK-shaped .messages.create()
#   - make_client() factory: env var / explicit override / SDK fallback
#   - Wiring: ClaudeReviewer + EvalRunner + Recipe pick up the switch
#   - CLI flag --use-claude-code on eval / autoresearch run / autoresearch loop / benchmark run

Feature: claude-code-everywhere — route every model call through the CLI

  @fast
  Scenario: shim returns a text content block when no tools are passed
    Given a fake claude binary returning result text "hello world" with input_tokens 5 and output_tokens 2
    When I call ClaudeCodeShimClient.messages.create with no tools
    Then the response's first content block type equals "text"
    And the response's first content block text equals "hello world"
    And the response's usage input_tokens equals 5
    And the response's usage output_tokens equals 2

  @fast
  Scenario: shim synthesizes a tool_use content block when tools are passed
    Given a fake claude binary returning a fenced JSON with one comment for the post_review_comments tool
    When I call ClaudeCodeShimClient.messages.create with the _COMMENT_TOOL and tool_choice
    Then the response has at least one tool_use content block
    And the tool_use block's name equals "post_review_comments"
    And the tool_use block's input has comments list of length 1
    And the first comment's path equals "src/foo.py"

  @fast
  Scenario: shim builds the expected argv
    Given a fake claude binary that records its argv
    When I call ClaudeCodeShimClient.messages.create with system "be brief" and model "sonnet"
    Then the recorded argv contains "--print"
    And the recorded argv contains "--output-format"
    And the recorded argv contains "json"
    And the recorded argv contains "--model"
    And the recorded argv contains "sonnet"
    And the recorded argv contains "--system-prompt"
    And the recorded argv contains "be brief"
    And the recorded argv contains "--disable-slash-commands"

  @fast
  Scenario: shim sums cached + uncached input tokens
    Given a fake claude binary returning input_tokens 3 cache_read 100 cache_creation 50 and output_tokens 7
    When I call ClaudeCodeShimClient.messages.create with no tools
    Then the response's usage input_tokens equals 153
    And the response's usage output_tokens equals 7

  @fast
  Scenario: make_client env var "1" routes to the shim
    Given PEER_USE_CLAUDE_CODE is set to "1"
    When I call make_client with no override
    Then the returned client is a ClaudeCodeShimClient

  @fast
  Scenario: make_client explicit override False wins over env var
    Given PEER_USE_CLAUDE_CODE is set to "1"
    When I call make_client with use_claude_code False
    Then the returned client is NOT a ClaudeCodeShimClient

  @fast
  Scenario: make_client default when env is unset
    Given PEER_USE_CLAUDE_CODE is unset
    When I call make_client with no override
    Then the returned client is NOT a ClaudeCodeShimClient

  @fast
  Scenario: ClaudeReviewer routes through the shim when env var is set
    Given PEER_USE_CLAUDE_CODE is set to "1"
    When I construct a ClaudeReviewer
    Then the reviewer's client is a ClaudeCodeShimClient

  @fast
  Scenario: EvalRunner._get_client honors the env var
    Given PEER_USE_CLAUDE_CODE is set to "1"
    When I call EvalRunner._get_client
    Then the returned client is a ClaudeCodeShimClient

  @fast
  Scenario: Recipe.use_claude_code=True yields a CLI reviewer and sets the env var
    Given a Recipe with use_claude_code True
    When I apply the recipe to a fresh Agent
    Then the Agent's reviewer is a ClaudeCodeCLIReviewer
    And PEER_USE_CLAUDE_CODE equals "1"
