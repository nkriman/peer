## Context

Inspired by Pydantic AI's `deps_type` / `RunContext` pattern (see `docs/pydantic_ai_design_philosophy.md`). Solves the "Agent kwargs are about to explode" problem the in-flight v0.2 changes would otherwise hit. Adopt the patterns without adding the Pydantic AI dependency.

## Goals / Non-Goals

**Goals:**
- One foundational refactor of `Agent.__init__` that the rest of v0.2 slots into cleanly.
- Testing primitives (`override`, `TestReviewer`, `ALLOW_LLM_CALLS`, `capture_run_messages`) that lift unit-test quality across the codebase.
- Validation retries that improve real recall on borderline LLM output.
- Provider:model string format that's unambiguous and extensible.
- Back-compat: every existing `Agent(...)` call site keeps working with a deprecation pathway, not a hard break.

**Non-Goals:**
- Pydantic AI as a dependency (would lock peer into PA's design + version + concept hierarchy).
- Async refactor of Agent.review (separate concern; lives in `eval-v02`).
- Streaming / iter / graph patterns (over-engineered for peer's scope).
- Multi-agent composition.
- Tool decoration (`@agent.tool`) — not needed until peer exposes user-callable tools.

## Decisions

### 1. `PeerDeps` is a `@dataclass`, not a Pydantic model

```python
from dataclasses import dataclass, field

@dataclass
class PeerDeps:
    config: Optional[PeerConfig] = None
    classifier: Optional[CommentClassifier] = None
    taxonomy: Optional[Taxonomy] = None
    enrichment: Optional[EnrichmentStep] = None
    linters: list[Linter] = field(default_factory=list)
    extra_instructions: Optional[str] = None
```

**Why dataclass not BaseModel:** PeerDeps carries function instances + state (classifier, linters) — not data. Pydantic models validate; dataclasses contain. Dataclasses are also lighter and don't pull in validation overhead on every construction.

**Why Optional everything:** existing `Agent()` calls without these fields must keep working. Defaults enable a back-compat path.

### 2. `RunContext` IS Pydantic and carries deps + run metadata

```python
class RunContext(BaseModel, Generic[T]):
    deps: T
    pr_url: str
    attempt: int = 0           # retry attempt (0-indexed)

    model_config = ConfigDict(arbitrary_types_allowed=True)
```

**Dropped from this version:** the `metadata: dict` escape hatch (per adversarial-review item 5.4). A `dict` field defeats the type-safety pitch RunContext exists to deliver. If users need adaptive per-attempt data, they should subclass PeerDeps or carry a typed Pydantic model on their custom deps. Re-introduce as a typed `attempt_metadata: AttemptMetadata` field if a real use case emerges.

Generic over `T` so type checkers see `RunContext[PeerDeps]` correctly.

**Why Pydantic here but not for PeerDeps:** RunContext is short-lived per-run state; carrying it through tools/reviewers benefits from Pydantic's validation + serialization (e.g., for capture). PeerDeps lives across many runs and contains heavy objects.

### 3. `Agent` constructor: model + deps_type + behavior knobs only

```python
class Agent(Generic[T]):
    def __init__(
        self,
        model: str = "anthropic:claude-sonnet-4-6",
        *,
        deps_type: Type[T] = PeerDeps,         # type-only; for type checkers
        system_prompt: Optional[str] = None,    # full prompt override
        retries: dict = field(default_factory=lambda: {"output": 0}),  # opt-in retries
        capture_messages: bool = False,
        # Legacy back-compat kwargs (emit DeprecationWarning, fold into PeerDeps):
        system_prompt_file: Optional[Path] = None,
        team_conventions: Optional[str] = None,
        team_conventions_file: Optional[Path] = None,
        config: Optional[PeerConfig] = None,
        config_file: Optional[Path] = None,
    ): ...
```

**Removed from this version:** the `instructions: Optional[str]` parameter (per adversarial-review item 5.2). peer has no multi-turn message-history concept that would distinguish "static prompt" from "regenerated per-run" — adding two parallel knobs that do the same thing creates confusion. Re-introduce when/if peer adds multi-turn agent flows.

**Default retries=`{"output": 0}` (opt-in)** per adversarial-review item 2.2. The v1 reference diagnosis shows validation drops are not a dominant failure mode; retries would add 30–50% LLM cost for a class of fixes that may not exist on well-calibrated reviewers. Users who see validation drops in their own data set `retries={"output": 1}` explicitly.

The constructor accepts the model + the type of deps it expects. Behavior knobs (retries, capture_messages) are kwargs. Capability-carrying fields (config, linters, conventions, classifier, ...) move into PeerDeps and are passed at run-time.

Legacy kwargs are accepted with `DeprecationWarning` and folded into an internal default PeerDeps so existing code keeps working.

### 4. `Agent.run(pr_url, deps) -> Review` is the new canonical entry

```python
agent = Agent(model="anthropic:claude-sonnet-4-6", deps_type=PeerDeps)
review = agent.run(
    pr_url="https://github.com/.../pull/42",
    deps=PeerDeps(config=cfg, linters=[RuffLinter()]),
)
```

Old `Agent.review(pr_url)` keeps working — it calls `self.run(pr_url, deps=self._default_deps)` where `self._default_deps` is built from any legacy kwargs.

### 5. `Agent.override(*, model=None, deps=None, reviewer=None)` context manager

```python
with agent.override(reviewer=TestReviewer()):
    review = agent.run(pr_url, deps=PeerDeps(...))
# original reviewer restored on exit
```

Inside the `with` block, the supplied overrides replace the agent's defaults. On exit (normal or exception), originals restore. Re-entrant — nested `override()` blocks stack and unwind correctly.

**Why context manager + not function args:** the override pattern lets callers swap deps/reviewer without modifying their application code. The eval framework benefits enormously: a single `EvalRunner` can run `agent.run(...)` per sample, and tests can `with agent.override(reviewer=TestReviewer()):` to swap out the LLM call.

### 6. `ALLOW_LLM_CALLS = True` module-level flag

```python
import peer.deps
peer.deps.ALLOW_LLM_CALLS = False  # CI: panic if anything tries to call an LLM

# elsewhere, inside ClaudeReviewer.review:
if not peer.deps.ALLOW_LLM_CALLS:
    raise LLMCallsDisabled(
        "LLM calls disabled by ALLOW_LLM_CALLS=False. "
        "Use Agent.override(reviewer=TestReviewer()) for tests."
    )
```

Checked inside each Reviewer's `review()` before any SDK invocation. New `LLMCallsDisabled` exception in `exceptions.py`.

**Why module-level not instance-level:** the flag's purpose is CI-wide safety. Per-instance would let one rogue test forget to disable. Module-level is one `pytest.fixture(autouse=True)` away from total CI coverage.

### 7. `TestReviewer` generates plausible Comments from input shape

```python
class TestReviewer:
    def __init__(self, comments: Optional[list[Comment]] = None,
                 n_comments: int = 1, severity: Severity = "minor"):
        self.comments = comments
        self.n_comments = n_comments
        self.severity = severity

    def review(self, context: Context,
               codebase_context: Optional[CodebaseContext] = None,
               ctx: Optional[RunContext] = None) -> tuple[list[Comment], dict]:
        if self.comments is not None:
            return list(self.comments), {"input_tokens": 0, "output_tokens": 0, "model": "test"}
        # Synthesize: pick first N valid (path, line) pairs from context.hunks
        out = []
        for h in context.hunks[: self.n_comments]:
            out.append(Comment(
                path=h.path, line=h.new_start,
                severity=self.severity,
                body="synthetic test comment",
                rationale="synthetic test rationale",
            ))
        return out, {"input_tokens": 0, "output_tokens": 0, "model": "test"}
```

Two modes:
- **Fixed comments** (passed in constructor) — for assertion-based tests
- **Synthesized comments** (default, derived from context.hunks) — for happy-path coverage tests

Always emits zero-cost usage. Schema-validates the same way real Reviewers do.

### 8. `capture_run_messages()` returns a list-shaped recorder

```python
with capture_run_messages() as msgs:
    review = agent.run(pr_url, deps=...)

# msgs is list[CapturedMessage]; can assert on prompt content + raw response
assert "modified_symbols" in msgs[0].system_prompt
```

`CapturedMessage` carries: `system_prompt`, `user_prompt`, `raw_response` (LLM provider's full response), `usage`, `latency_ms`.

Capture is opt-in via the context manager OR `Agent(capture_messages=True)` for persistent capture. Captured messages are NOT included in `Review` by default (would bloat report sizes); they're accessible via the context manager OR via `agent.last_messages` (set after each `run`).

For `EvalReport`, the optional `EvalSampleResult.captured_messages: Optional[list[CapturedMessage]] = None` field can hold per-sample message capture when the eval runs under a `capture_run_messages()` block.

### 9. Validation retries via `retries={'output': N}`

```python
agent = Agent(retries={"output": 2})  # 2 retries on validation failure
```

`Agent.run` flow:
1. Call reviewer → get raw comments
2. Validate via `_validate_comments` (existing logic — drops bad paths / out-of-hunk lines)
3. If any comments were dropped AND `retries['output'] > 0`:
   - Construct a follow-up user message: "Your previous response had N invalid comments: [list]. Please fix them."
   - Call reviewer again with the augmented message history
   - Re-validate
   - Decrement retry budget
4. Return final Review

**Why bounded retries:** unbounded could spin on a stubborn LLM. Default `1` means one chance to self-correct, matching Pydantic AI's default.

**What counts as a retryable failure:** path not in diff, line outside hunk. NOT: schema validation (the SDK tool-call should already enforce that).

### 10. Provider:model string format

```python
# Canonical
Agent(model="anthropic:claude-sonnet-4-6")
Agent(model="openai:gpt-5.2")
Agent(model="anthropic:claude-haiku-4-5-20251001")

# Legacy (DeprecationWarning, still works):
Agent(model="claude-sonnet-4-6")   # warns: use 'anthropic:claude-sonnet-4-6'
Agent(model="gpt-4o")              # warns: use 'openai:gpt-4o'
```

`_parse_model_id(s) -> tuple[str, str]` returns `(provider, model_id)`. Bare names get the legacy shim — looks at the prefix and infers (`claude*` → anthropic, `gpt*`/`o[1-9]` → openai). `UnknownModelError` for anything that doesn't match.

**Dispatch:** `_select_reviewer(provider, model_id, ...)` replaces the current `if model.startswith("claude"): ...` chain.

**Canonical `Reviewer.model` form:** Reviewer instances SHALL store the FULL `provider:model_id` string as their `.model` attribute (e.g., `self.model = "anthropic:claude-sonnet-4-6"`, not bare `"claude-sonnet-4-6"`). `_infer_agent_config(reviewer)` in `eval/runner.py` reads this as-is and writes it into `EvalReport.agent_config.model` — every saved report carries the canonical provider:model string. Pre-v01 reports with bare model names load via `from_json` with a one-time deprecation log; A/B diffs across the boundary normalize both sides to canonical via `_canonicalize_model(s)` before comparison.

### 11. Reviewer Protocol gains an optional `ctx: RunContext` parameter

```python
class Reviewer(Protocol):
    def review(
        self,
        context: Context,
        codebase_context: Optional[CodebaseContext] = None,
        ctx: Optional[RunContext[Any]] = None,
    ) -> tuple[list[Comment], dict]: ...
```

`ctx` is optional and back-compat (existing implementations that don't accept it via `**kwargs` still work). When provided, Reviewers can use `ctx.deps` to access custom dependencies (e.g., a `RuffLinter` instance for inline linting integration) and `ctx.attempt` to adapt prompts on retry.

### 12. Back-compat: legacy `Agent(...)` kwargs absorbed into a default PeerDeps

Existing code paths like `Agent(model="...", team_conventions=...)` continue to work by:
1. Constructor sees `team_conventions=` is set
2. Issues `DeprecationWarning` pointing to `PeerDeps(extra_instructions=...)` or `PeerConfig` once it lands
3. Builds an internal `_default_deps = PeerDeps(extra_instructions=...)` (or similar)
4. `Agent.review(pr_url)` calls `self.run(pr_url, deps=self._default_deps)`

This is the only "magic" in the change. Everything else is explicit. Documentation makes the migration path clear: new code uses `Agent(model=..., deps_type=PeerDeps)` + `agent.run(pr_url, deps=PeerDeps(...))`.

## Risks / Trade-offs

- **[Risk]** The deprecation path is non-trivial; users on legacy kwargs see warnings on every Agent construction. **Mitigation:** README's migration section + a `python -W default::DeprecationWarning` recipe. Plan to remove legacy kwargs in v1.0 (~6 months after public release).
- **[Risk]** `ALLOW_LLM_CALLS` is module-state — surprising to find when debugging. **Mitigation:** clear docstring + raises a specific exception type with the exact fix in the message; `pytest` fixtures section in docs explains the pattern.
- **[Risk]** `TestReviewer`'s synthesized comments may not match real LLM behavior closely enough for integration tests. **Mitigation:** `TestReviewer(comments=[...])` lets tests inject exact comment fixtures; mode-1 covers all the contract-shape tests, mode-2 covers the "doesn't crash" tests.
- **[Risk]** Validation retries materially increase cost (worst case: N+1 LLM calls per review). **Mitigation:** retry budget defaults to 1; metric to surface in EvalReport (`n_retries_used`); cost guardrails apply equally to retries.
- **[Risk]** Provider:model format change is back-compat but every doc + example needs updating. **Mitigation:** scoped to one PR; pre-commit grep for bare model names in examples; warning prompts users to migrate.
- **[Risk]** `RunContext` Generic typing may stress mypy/pyright on older Python versions. **Mitigation:** test against Python 3.10 (peer's minimum) explicitly in CI; fall back to `RunContext[Any]` aliases if needed.
- **[Risk]** `override()` re-entrance: if user nests overrides incorrectly, restoration could leak. **Mitigation:** implement with `contextlib.contextmanager` + explicit stack so each `__exit__` undoes its own override; covered by tests.
- **[Risk]** PeerDeps fields will keep growing as v0.2 lands (config, linters, enrichment, custom rules ...). **Mitigation:** that's the point — all are Optional defaults; constructor stays simple regardless. If it ever becomes a problem, switch to a `BaseDeps` protocol so users supply their own subclass.

## Open Questions

None blocking. Deferred:
- Should `Agent.run` be async-first (Pydantic AI pattern) with `run_sync` wrapper? Could be a follow-on; for v0.1 the sync API is fine.
- Should validation retries be configurable per error type (e.g., 2 retries for "wrong line", 0 for "wrong path")? Probably yes long-term; for v0.1 single budget is enough.
- Should `capture_run_messages` automatically redact secrets in the prompt (e.g., API keys leaked into context)? Worth thinking about but defer; explicit responsibility on the user for now.
