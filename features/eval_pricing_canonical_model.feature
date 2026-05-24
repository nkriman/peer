# peer-deps-v01 canonicalized model strings to "provider:model_id" (e.g.
# "anthropic:claude-sonnet-4-6"), but the eval pricing table is keyed by
# bare model_id. As a result, cost_usd_total reports n/a for new runs.
# Fix: strip the provider prefix in estimate_cost before lookup.

Feature: pricing table accepts both canonical and legacy model strings

  @fast
  Scenario: estimate_cost works with the canonical provider:model_id form
    When I call estimate_cost with model "anthropic:claude-sonnet-4-6", input_tokens 1000000, output_tokens 0
    Then the returned cost equals 3.0

  @fast
  Scenario: estimate_cost still works with the legacy bare model_id
    When I call estimate_cost with model "claude-sonnet-4-6", input_tokens 1000000, output_tokens 0
    Then the returned cost equals 3.0

  @fast
  Scenario: estimate_cost returns None for an unknown model regardless of provider prefix
    When I call estimate_cost with model "anthropic:claude-mystery-9-0", input_tokens 1000, output_tokens 0
    Then the returned cost is None
