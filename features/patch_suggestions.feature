# User-facing behaviors for patch-suggestions-v01.
# Implementation spec: openspec/changes/patch-suggestions-v01/specs/patch-suggestions/spec.md
# bd issue: peer-1rm

Feature: patch-suggestions v01 — Comment.suggestion + issue_header + end_line + SuggestionRate

  @fast
  Scenario: Comment without suggestion validates with suggestion=None
    When I construct a Comment without a suggestion
    Then the Comment's suggestion is None
    And the Comment's issue_header is None
    And the Comment's end_line is None

  @fast
  Scenario: Comment with all three new fields validates
    When I construct a Comment with suggestion "x = y", issue_header "Possible Bug", end_line 15
    Then the Comment's suggestion equals "x = y"
    And the Comment's issue_header equals "Possible Bug"
    And the Comment's end_line equals 15

  @fast
  Scenario: Comment serialization round-trips suggestion / issue_header / end_line
    When I construct a Comment with suggestion "z = w", issue_header "Style Nit", end_line 22
    Then the Comment round-trips through model_dump_json + model_validate_json

  @fast
  Scenario: end_line less than line is rejected
    When I attempt to construct a Comment with line 10 and end_line 5
    Then a ValidationError is raised

  @fast
  Scenario: SuggestionRate reports per-sample fraction of comments with a suggestion
    Given a Review with 4 comments — 2 with suggestion, 2 without
    When I score with SuggestionRate
    Then the per-sample value equals 0.5

  @fast
  Scenario: SuggestionRate with zero comments returns None
    Given a Review with 0 comments
    When I score with SuggestionRate
    Then the per-sample value is None
