# autoresearch-recipe-v01 (peer-o4v):
#   - Recipe Pydantic model (full reviewer mutation surface)
#   - Externalized DEFAULT_SYSTEM_PROMPT at prompts/default_system_prompt.md
#   - ClaudeReviewer honors temperature (default 0.0)
#   - `peer autoresearch run` CLI: one iteration, one TSV row
#   - `peer autoresearch loop` CLI: autonomous mutate-eval-keep-or-revert
#   - program.md utility-formula parsing

Feature: autoresearch recipe — single-file mutation surface + leaderboard loop

  @fast
  Scenario: Default Recipe construction matches today's Agent
    When I construct a Recipe with no arguments
    Then the Recipe's model equals "anthropic:claude-sonnet-4-6"
    And the Recipe's temperature equals 0.0
    And the Recipe's max_tokens equals 8192
    And the Recipe's retries equal {"output": 1}

  @fast
  Scenario: Recipe round-trips through YAML
    Given a populated Recipe with model "anthropic:claude-opus-4-7" and temperature 0.3
    When I dump it via to_yaml and parse it back via from_yaml
    Then the parsed Recipe equals the original

  @fast
  Scenario: Recipe rejects unknown fields
    When I parse a YAML string with a top-level "unknown_field: 42"
    Then a Pydantic ValidationError is raised

  @fast
  Scenario: ClaudeReviewer default temperature is 0.0
    Given a ClaudeReviewer constructed with default temperature
    When I inspect the kwargs it would pass to messages.create
    Then the kwargs include "temperature" equal to 0.0

  @fast
  Scenario: ClaudeReviewer honors a non-default temperature
    Given a ClaudeReviewer constructed with temperature 0.7
    When I inspect the kwargs it would pass to messages.create
    Then the kwargs include "temperature" equal to 0.7

  @fast
  Scenario: Recipe.apply_to_agent rebuilds the reviewer with the recipe's settings
    Given a fresh Agent and a Recipe with model "anthropic:claude-sonnet-4-6" and temperature 0.5
    When I call recipe.apply_to_agent
    Then the Agent's reviewer's temperature equals 0.5
    And the Agent's model equals "anthropic:claude-sonnet-4-6"

  @fast
  Scenario: Agent constructor accepts a recipe; recipe wins over kwargs
    When I construct an Agent with model "anthropic:claude-opus-4-7" and recipe model "anthropic:claude-sonnet-4-6"
    Then the Agent's model equals "anthropic:claude-sonnet-4-6"

  @fast
  Scenario: DEFAULT_SYSTEM_PROMPT loads from prompts/default_system_prompt.md
    Given the file prompts/default_system_prompt.md exists with a known marker
    When I freshly import peer.prompts
    Then peer.prompts.DEFAULT_SYSTEM_PROMPT contains the marker

  @fast
  Scenario: parse_utility_formula handles a simple formula
    When I parse the program.md utility block "score = detection_rate"
    Then evaluating the formula on metrics {detection_rate: 0.05} returns 0.05

  @fast
  Scenario: parse_utility_formula handles a composite formula with max
    When I parse the program.md utility block "score = detection_rate - 0.05 * max(0, n_comments_total - 5)"
    Then evaluating the formula on metrics {detection_rate: 0.1, n_comments_total: 10} returns 0.0
    And evaluating the formula on metrics {detection_rate: 0.1, n_comments_total: 3} returns 0.1

  @fast
  Scenario: parse_utility_formula rejects unsafe constructs
    When I parse the program.md utility block "score = __import__('os').system('ls')"
    Then UnsafeUtilityFormula is raised

  @fast
  Scenario: parse_utility_formula falls back when no program.md
    When I parse a None program.md
    Then evaluating the resulting formula on metrics {detection_rate: 0.07} returns 0.07

  @fast
  Scenario: append_row writes the leaderboard header on first call
    Given a fresh empty temp file path for the leaderboard
    When I call append_row with utility 0.05 and status "ok"
    Then the file's first line equals the canonical TSV header
    And the file has exactly 2 lines total

  @fast
  Scenario: append_row appends without rewriting the header on subsequent calls
    Given a leaderboard file with one prior row
    When I call append_row twice more with utility 0.06 and utility 0.07
    Then the file has exactly 4 lines (1 header + 3 data rows)

  @fast
  Scenario: append_row records the supplied status verbatim
    Given a fresh empty temp file path for the leaderboard
    When I call append_row with status "crash" and description "OOM during gather"
    Then the file's last row's status column is "crash"
    And the file's last row's description column is "OOM during gather"
