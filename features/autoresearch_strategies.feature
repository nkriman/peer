# autoresearch-strategies-v01 (peer-oaq):
#   - peer.strategies registry (short names + dotted paths)
#   - DraftCritiqueReviewer, TwoModelPipelineReviewer, SelfFilterReviewer
#   - Recipe.reviewer_dotted_path + reviewer_kwargs wiring

Feature: peer.strategies — composable Reviewer-Protocol primitives

  @fast
  Scenario: registry resolves a short name
    When I call resolve_strategy with "draft_critique"
    Then the returned class is DraftCritiqueReviewer

  @fast
  Scenario: registry resolves a dotted path
    When I call resolve_strategy with "peer.strategies.SelfFilterReviewer"
    Then the returned class is SelfFilterReviewer

  @fast
  Scenario: unknown name raises UnknownStrategy
    When I call resolve_strategy with "not_a_real_strategy"
    Then UnknownStrategy is raised

  @fast
  Scenario: DraftCritiqueReviewer drops comments the critique rejects
    Given an inner TestReviewer returning 3 fixed Comments and a critique returning DROP for the first
    When I invoke DraftCritiqueReviewer.review
    Then the returned comments list has length 2

  @fast
  Scenario: DraftCritiqueReviewer keeps all comments when critique passes all
    Given an inner TestReviewer returning 2 fixed Comments and a critique returning KEEP for all
    When I invoke DraftCritiqueReviewer.review
    Then the returned comments list has length 2

  @fast
  Scenario: DraftCritiqueReviewer aggregates usage across passes
    Given an inner TestReviewer returning 1 Comment with usage {input_tokens 100, output_tokens 50} and a critique with usage {input_tokens 200, output_tokens 30}
    When I invoke DraftCritiqueReviewer.review
    Then the returned usage's input_tokens equals 300
    And the returned usage's output_tokens equals 80

  @fast
  Scenario: TwoModelPipelineReviewer skips detail when screen returns nothing
    Given a screen TestReviewer returning 0 Comments and a detail TestReviewer that should not be called
    When I invoke TwoModelPipelineReviewer.review
    Then the returned comments list has length 0
    And the detail reviewer was invoked 0 times

  @fast
  Scenario: TwoModelPipelineReviewer invokes detail once per screen candidate
    Given a screen TestReviewer returning 2 Comments and a recording detail TestReviewer
    When I invoke TwoModelPipelineReviewer.review
    Then the detail reviewer was invoked 2 times

  @fast
  Scenario: SelfFilterReviewer drops Comments below the confidence threshold
    Given an inner TestReviewer returning 2 fixed Comments and a stub judge returning scores 0.9 and 0.3
    When I invoke SelfFilterReviewer with min_confidence 0.5
    Then the returned comments list has length 1

  @fast
  Scenario: Recipe applies a strategy via short name
    Given a Recipe with reviewer_dotted_path "draft_critique" and reviewer_kwargs containing an inner TestReviewer
    When I apply the recipe to a fresh Agent
    Then the Agent's reviewer is a DraftCritiqueReviewer
