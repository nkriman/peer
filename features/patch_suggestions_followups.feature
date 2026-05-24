# peer-5is: patch-suggestions-v01 follow-ups.
# Covers tool-schema, default prompt language, CLI rendering, and
# SuggestionRate joining the default metric set.

Feature: patch-suggestions v01 follow-ups — tool schema, prompt guidance, CLI rendering, defaults

  @fast
  Scenario: Anthropic tool schema accepts suggestion / issue_header / end_line as optional fields
    When I import _COMMENT_TOOL from peer.reviewers
    Then the tool schema's input properties include "suggestion"
    And the tool schema's input properties include "issue_header"
    And the tool schema's input properties include "end_line"
    And the "suggestion" property is described as nullable
    And the required fields list does NOT include "suggestion"
    And the required fields list does NOT include "issue_header"
    And the required fields list does NOT include "end_line"

  @fast
  Scenario: ClaudeReviewer parses suggestion + issue_header + end_line from tool output
    Given a ClaudeReviewer whose client returns one tool-use comment with suggestion "if x:\\n    pass" and issue_header "Possible Bug" and end_line 12
    When I invoke the Reviewer on a synthetic Context
    Then the returned Comment list has length 1
    And the first Comment's suggestion equals "if x:\n    pass"
    And the first Comment's issue_header equals "Possible Bug"
    And the first Comment's end_line equals 12

  @fast
  Scenario: DEFAULT_SYSTEM_PROMPT instructs the agent when to include a suggestion
    When I import DEFAULT_SYSTEM_PROMPT from peer.prompts
    Then the prompt mentions the word "suggestion"
    And the prompt mentions "issue_header"
    And the prompt describes when NOT to include a suggestion (e.g. "consider refactoring" / large rewrites)

  @fast
  Scenario: CLI review output renders a suggestion as a delimited block
    Given a Review with one Comment carrying a suggestion "if x:\\n    return None"
    When I render the Review via _format_review_output
    Then the rendered output contains "--- suggested change ---"
    And the rendered output contains "if x:"
    And the rendered output contains "return None"

  @fast
  Scenario: CLI review output omits the suggestion block when none is present
    Given a Review with one Comment that has no suggestion
    When I render the Review via _format_review_output
    Then the rendered output does NOT contain "--- suggested change ---"

  @fast
  Scenario: CLI review output prepends issue_header when present
    Given a Review with one Comment with issue_header "Possible Bug"
    When I render the Review via _format_review_output
    Then the rendered output contains "Possible Bug"

  @fast
  Scenario: EvalRunner default metrics now include SuggestionRate
    Given a minimal EvalRunner constructed with a TestReviewer and an empty dataset
    Then the runner's default metrics list contains a metric named "suggestion_rate"
