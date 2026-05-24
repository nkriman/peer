## 1. Registry + module layout

- [ ] 1.1 Create `src/peer/strategies/__init__.py` re-exporting all built-in strategies.
- [ ] 1.2 Create `src/peer/strategies/registry.py` with `register_strategy`, `resolve_strategy`, `UnknownStrategy` exception.
- [ ] 1.3 Built-ins pre-register at strategy-module import.

## 2. DraftCritiqueReviewer

- [ ] 2.1 Implement `src/peer/strategies/draft_critique.py` per spec.
- [ ] 2.2 Critique prompt template: short, "here are draft comments — return one per line: KEEP / DROP / REWRITE <new body>".
- [ ] 2.3 Parse critique response; apply KEEP/DROP/REWRITE to draft list.
- [ ] 2.4 Aggregate usage across passes.

## 3. TwoModelPipelineReviewer

- [ ] 3.1 Implement `src/peer/strategies/two_model_pipeline.py` per spec.
- [ ] 3.2 Context-narrowing: for each screen candidate, build a Context containing only hunks for the matching path.

## 4. SelfFilterReviewer

- [ ] 4.1 Implement `src/peer/strategies/self_filter.py` per spec.
- [ ] 4.2 Per-comment judge: pass Comment body + ctx-hunk text; parse 0–1 confidence from response.
- [ ] 4.3 INFO log on drop.

## 5. Recipe wiring

- [ ] 5.1 Add `reviewer_dotted_path: str | None` and `reviewer_kwargs: dict` to `Recipe`.
- [ ] 5.2 Extend `recipe.apply_to_agent` to use the registry when `reviewer_dotted_path` is set.
- [ ] 5.3 Recursive resolution of nested-Reviewer kwargs: if a `reviewer_kwargs` value is a string that starts with a known package prefix and resolves to a Reviewer class, instantiate it (single-level recursion only — avoid infinite loops).

## 6. Exports

- [ ] 6.1 Export `DraftCritiqueReviewer`, `TwoModelPipelineReviewer`, `SelfFilterReviewer` from `peer.strategies`.
- [ ] 6.2 Export `resolve_strategy`, `register_strategy`, `UnknownStrategy` from `peer.strategies`.

## 7. BDD

- [ ] 7.1 `features/autoresearch_strategies.feature` covering all scenarios. Use `TestReviewer` or stub-Reviewer fixtures.
- [ ] 7.2 Step defs in `features/steps/autoresearch_strategies_steps.py`.

## 8. Docs

- [ ] 8.1 `docs/strategies.md`: how to author a new strategy (one file, satisfy Reviewer Protocol, drop in `src/peer/strategies/`, re-export, recipe references via short name).

## 9. Quality gates

- [ ] 9.1 ruff / format / mypy / pytest / behave all clean.
