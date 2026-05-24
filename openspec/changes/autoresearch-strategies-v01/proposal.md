## Why

`autoresearch-recipe-v01` lets the agent mutate config — model, temperature, prompt text, context budgets. That covers a lot but not the *orchestrational* dimensions: multi-pass review, two-model pipelines, self-filtering, hunk-at-a-time vs whole-PR. These are the moves where the framework-self-improvement promise actually delivers value, because each new strategy is a primitive that any peer user can opt into via recipe — not a one-off prompt tweak.

This change adds a `peer.strategies` subpackage and the Reviewer Protocol's natural extension: composable wrappers. Ships three example strategies as proof points, plus the loading machinery so the recipe can wire `reviewer: peer.strategies.DraftCritiqueReviewer` by dotted-path. The agent is then free (in the next autoresearch loop) to author new strategies in `src/peer/strategies/` and have them measured by the same eval harness.

## What Changes

- New `peer.strategies` subpackage. Inherits the existing `Reviewer` Protocol from `peer.reviewers` — strategies ARE reviewers, composed.
- New `peer.strategies.DraftCritiqueReviewer` — wraps an inner Reviewer in a draft → critique → revise loop. Inner reviewer produces a draft Review; a critique pass (same or smaller model) flags weak comments; a revision pass either drops or rewrites them. Configurable depth (`n_critique_rounds: int = 1`).
- New `peer.strategies.TwoModelPipelineReviewer` — uses one model for a "screen" pass (cheap, e.g. haiku) and another for the "detail" pass (expensive, e.g. sonnet) on whatever the screen flagged. Lets recipes trade cost for quality at known granularity.
- New `peer.strategies.SelfFilterReviewer` — wraps an inner Reviewer with a per-comment confidence judge. Asks the model "would you stake your reputation on this comment?" and drops anything below threshold.
- New `peer.recipe.Recipe.reviewer_dotted_path: str | None` — when set, the recipe resolves the dotted path (`peer.strategies.DraftCritiqueReviewer`) instead of constructing a bare `ClaudeReviewer`. Constructor kwargs come from `recipe.reviewer_kwargs: dict`.
- New `peer.strategies.registry` — `register_strategy(name, cls)` + `resolve_strategy(name_or_dotted_path)`. Built-in strategies pre-register at import time. User-introduced strategies in `src/peer/strategies/` auto-register via the subpackage's `__init__.py` re-exports.
- New `docs/strategies.md` — short guide for an agent (or human) introducing a new strategy: "subclass nothing, satisfy the Reviewer Protocol, drop a file in `src/peer/strategies/`, re-export from `__init__.py`, the recipe can now reference it." Tied to `program.md`'s instructions for autoresearch agents extending the surface.

## Capabilities

### New Capabilities

- `autoresearch-strategies`: `peer.strategies` subpackage, three built-in strategies, dotted-path registry, recipe wiring.

### Modified Capabilities

- `autoresearch-recipe` (from `autoresearch-recipe-v01`): `Recipe` gains `reviewer_dotted_path` + `reviewer_kwargs` fields. When set, the Recipe applies via the registry instead of the default `ClaudeReviewer`. Recipe round-trip + apply behavior covers the new fields.

## Impact

- **Code**: new `src/peer/strategies/__init__.py`, `draft_critique.py`, `two_model_pipeline.py`, `self_filter.py`, `registry.py`. Modify `src/peer/recipe.py` to honor `reviewer_dotted_path`.
- **Tests**: BDD in `features/autoresearch_strategies.feature`. Each strategy gets at least one scenario with a `TestReviewer` (or a stubbed inner) — no live LLM calls in the BDD layer.
- **Dependencies**: none new.
- **Docs**: `docs/strategies.md`; a paragraph in `program.md` pointing the autoresearch agent at it.
- **Out of scope**: strategies that depend on tool-use beyond what ClaudeReviewer already supports; strategies that introduce new datasets or persist state.
- **Back-compat**: default `Recipe` still uses a bare `ClaudeReviewer`; existing code paths unchanged.
