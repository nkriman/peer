## Why

`Agent.__init__` already accepts a flat kwarg list: `model`, `system_prompt`, `system_prompt_file`, `team_conventions`, `team_conventions_file`. The 5 in-flight changes (`peer-config-v01`, `linter-context-v01`, `patch-suggestions-v01`, plus the PR-Agent-inspired `extra_instructions`) each propose adding more kwargs. Without a structural change, the Agent constructor becomes an unreviewable mass.

Pydantic AI (`docs/pydantic_ai_design_philosophy.md`) solves this with the `deps_type` / `RunContext` pattern: agent construction declares the dependency *type*; dependency *instances* are passed at run time. Tools access via typed `RunContext[T]`. The pattern unlocks:

1. **Cleaner Agent constructor.** One `deps_type=` parameter regardless of how many capabilities exist.
2. **Materially better testability.** `Agent.override(deps=...)` swaps deps for tests without touching application code; `TestReviewer` replaces real LLM calls; `ALLOW_LLM_CALLS=False` is a CI panic switch.
3. **Validation retries.** When the LLM produces a Comment with wrong path/line, the framework feeds the error back to the model and retries — instead of peer's current "silently drop" behavior.
4. **Message capture for forensics.** Eval and benchmark runs need the exact prompt + response, not just token counts. Pydantic AI's `capture_run_messages()` pattern provides this.
5. **Provider:model string format.** `'anthropic:claude-sonnet-4-6'` is unambiguous; peer's current `startswith('claude')` is brittle.

Landing this change *before* `peer-config-v01`, `linter-context-v01`, etc. means those changes slot config / linters / enrichment as `PeerDeps` fields instead of more Agent kwargs. Cleaner long-term API; small detour now.

## What Changes

- New `peer.deps` module: `PeerDeps` dataclass holding all per-run dependencies (config, linters, enrichment, classifier, taxonomy, conventions, extra_instructions). Slot-able by all downstream changes.
- New `peer.context.RunContext` Pydantic model: typed wrapper around `deps + sample metadata` passed to Reviewer + Evaluator + tool functions.
- New `Agent.run(pr_url, deps) -> Review` method that takes deps at run time (alongside existing `Agent.review(pr_url)` for back-compat).
- New `Agent.override(*, model=None, deps=None, reviewer=None)` context manager. Inside the `with` block, the agent uses overridden values; reverts on exit.
- New `peer.deps.ALLOW_LLM_CALLS` module-level flag. When `False`, any Reviewer that attempts an LLM call raises `LLMCallsDisabled`. Defaults to `True`.
- New `peer.reviewers.TestReviewer`: deterministic synthetic Reviewer for tests. Honors `output_type`/expected shape; returns synthesized Comments without LLM calls.
- New `peer.context.capture_run_messages()` context manager: captures the full prompt + raw response for each `Agent.run` call inside the `with` block.
- Validation retries: `Agent` constructor gains `retries: dict = {'output': 1}`. On Comment validation failure (unknown path / out-of-hunk line), the framework feeds the validation error back to the LLM and retries; bounded by the retry budget.
- Provider:model string format: parse `'<provider>:<model_id>'`; back-compat shim for bare model names (`claude-...` and `gpt-...`) emits `DeprecationWarning`.

## Capabilities

### New Capabilities

- `peer-deps`: `PeerDeps` dataclass + `RunContext` type + `Agent.override` + `ALLOW_LLM_CALLS` + `TestReviewer` + `capture_run_messages` + validation retries + provider:model parsing.

### Modified Capabilities

- `pr-review-agent` (from `agent-v01`): `Agent.__init__` signature changes (additive kwargs + `deps_type=`). `Agent.review(pr_url)` continues to work (back-compat shim that builds an empty `PeerDeps`). `Agent.run(pr_url, deps)` is the new canonical entry. `Reviewer` Protocol gains an optional `ctx: RunContext` parameter.

## Impact

- **Code**: new `src/peer/deps.py`, `src/peer/context.py` gets `RunContext` + `capture_run_messages`, `src/peer/reviewers.py` gains `TestReviewer` + accepts `RunContext`, `src/peer/agent.py` rewrites `__init__` + adds `run` + adds `override`, `src/peer/exceptions.py` adds `LLMCallsDisabled`, `src/peer/__init__.py` exports.
- **Tests**: significant additions — new `tests/test_deps.py`, new `tests/test_agent_override.py`, new `tests/test_test_reviewer.py`, new `tests/test_validation_retries.py`. Existing tests stay green via back-compat shims.
- **Dependencies**: none new. Pure-Python implementation.
- **Schema**: no JSONL / report schema changes. `EvalReport` gains optional `captured_messages` field for runs that opted into capture (defaults None).
- **Documentation**: README + `docs/framework_overview.md` updates with the deps pattern + override + testing examples.
- **Out of scope**: Pydantic AI integration (separate `peer-pydantic-ai-v01` change); streaming; multi-agent composition.
- **Back-compat:** `Agent(model="claude-sonnet-4-6", system_prompt=..., team_conventions=...)` keeps working — internally constructs an empty `PeerDeps` and wraps the legacy kwargs into the new shape. `DeprecationWarning` emitted on bare-model-name usage.
