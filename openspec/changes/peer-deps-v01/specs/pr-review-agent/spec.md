## MODIFIED Requirements

### Requirement: Agent supports the deps-based runtime model

`Agent.__init__` SHALL accept (in addition to existing kwargs which are kept for back-compat with `DeprecationWarning`): `model` (str, provider:model format), `deps_type` (Type, defaults to `PeerDeps`), `system_prompt` (str, persistent), `instructions` (str, regenerated per-run), `retries` (dict, defaults to `{"output": 1}`), `capture_messages` (bool, defaults to False).

A new method `Agent.run(pr_url: str, deps: T) -> Review` SHALL be the canonical entry point.

The existing `Agent.review(pr_url)` SHALL continue to work as a back-compat shim that internally calls `self.run(pr_url, deps=self._default_deps)`, where `_default_deps` is constructed from any legacy kwargs.

#### Scenario: New canonical entry point

- **WHEN** `Agent(model="anthropic:claude-sonnet-4-6", deps_type=PeerDeps).run("https://github.com/.../pull/42", deps=PeerDeps(config=cfg))` is called
- **THEN** the agent uses `cfg` from `deps` during the review and returns a Review

#### Scenario: Back-compat shim for existing callers

- **WHEN** `Agent(model="claude-sonnet-4-6", team_conventions="...").review(pr_url)` is called (legacy pattern)
- **THEN** the call succeeds; a `DeprecationWarning` is emitted naming the new pattern; the legacy `team_conventions` value is wrapped into an internal `_default_deps.extra_instructions`

#### Scenario: deps_type generic for type checking

- **WHEN** `Agent[PeerDeps](model="anthropic:claude-sonnet-4-6", deps_type=PeerDeps)` is constructed and `agent.run(pr_url, deps=PeerDeps(...))` is called
- **THEN** a static type checker (mypy / pyright) verifies that `deps` matches `PeerDeps` and surfaces errors if a different type is passed

### Requirement: Agent.override context manager for runtime swaps

The framework SHALL provide `Agent.override(*, model=None, deps=None, reviewer=None)` as a context manager. Inside the `with` block, the supplied values replace the agent's defaults; on `__exit__` (whether normal or exception), originals restore. Nested `override` blocks SHALL stack and unwind correctly.

#### Scenario: Override swaps reviewer for the block

- **WHEN** `with agent.override(reviewer=TestReviewer()): agent.run(pr_url, deps=...)` runs
- **THEN** the run uses TestReviewer; after exit, `agent.reviewer` is the original (e.g., ClaudeReviewer)

#### Scenario: Override restores on exception

- **GIVEN** `original_reviewer = agent.reviewer`
- **WHEN** `with agent.override(reviewer=TestReviewer()): raise RuntimeError("boom")` is executed
- **THEN** the RuntimeError propagates AND `agent.reviewer is original_reviewer` after the block

#### Scenario: Nested overrides stack and restore in reverse order

- **GIVEN** an agent with reviewer R0, model M0
- **WHEN** `with agent.override(reviewer=R1): with agent.override(model=M1, reviewer=R2): ...; print(agent.reviewer)` executes
- **THEN** during the inner block `agent.reviewer is R2`; after the inner block exits, `agent.reviewer is R1`; after the outer block, `agent.reviewer is R0` and `agent.model == M0`

### Requirement: Validation retries via retries['output']

`Agent.run` SHALL respect the `retries` budget configured at `__init__`. When `_validate_comments` drops one or more Comments AND `retries['output'] > 0`, the framework SHALL feed the validation error back to the Reviewer (as a follow-up user message including the dropped comments + reason), retry, re-validate, and decrement the budget. The retry SHALL bump `ctx.attempt` so Reviewers may adapt.

#### Scenario: One retry on dropped comment

- **GIVEN** an Agent with `retries={"output": 1}` and a Reviewer (mocked) that returns Comment with out-of-hunk line on attempt 0 and a valid Comment on attempt 1
- **WHEN** `agent.run(pr_url, deps=...)` is called
- **THEN** the returned Review contains the valid Comment from attempt 1; the dropped Comment is logged at WARNING and counted in `Review.usage.n_retries`

#### Scenario: Retry budget exhausted

- **GIVEN** an Agent with `retries={"output": 0}`
- **WHEN** the Reviewer returns a Comment with out-of-hunk line
- **THEN** the dropped Comment is NOT retried; final Review reflects the validated output minus the dropped Comment

#### Scenario: Retries skipped when all comments validate

- **GIVEN** an Agent with `retries={"output": 2}`
- **WHEN** the Reviewer returns Comments that all validate
- **THEN** no retry occurs; `Review.usage.n_retries == 0`

### Requirement: Provider:model string format with legacy back-compat

`Agent.__init__` SHALL parse `model` strings as `<provider>:<model_id>` (e.g., `"anthropic:claude-sonnet-4-6"`). Bare model names SHALL be accepted via legacy inference (`claude*` → anthropic, `gpt*`/`o[1-9]*` → openai) with `DeprecationWarning` emitted.

#### Scenario: Canonical provider:model format

- **WHEN** `Agent(model="anthropic:claude-sonnet-4-6")` is constructed
- **THEN** the agent dispatches to `ClaudeReviewer(model_id="claude-sonnet-4-6")` with no warning

#### Scenario: Legacy bare name with warning

- **WHEN** `Agent(model="claude-sonnet-4-6")` is constructed
- **THEN** a `DeprecationWarning` is emitted naming the canonical format (`"anthropic:claude-sonnet-4-6"`) and the dispatch proceeds identically

#### Scenario: Unknown provider raises

- **WHEN** `Agent(model="unknown:xyz")` is constructed
- **THEN** `UnknownModelError` is raised with the supported provider list (`anthropic`, `openai`, ...)

### Requirement: Reviewer Protocol accepts optional RunContext

The `Reviewer` Protocol SHALL accept an optional third parameter `ctx: Optional[RunContext[Any]] = None` on the `review` method. Existing Reviewers that don't declare `ctx` (e.g., via `**kwargs`) SHALL continue to satisfy the Protocol.

#### Scenario: New Reviewer accepts ctx

- **WHEN** `MyReviewer.review(context, codebase_context, ctx=run_ctx)` is called where `MyReviewer` declares `ctx` in its signature
- **THEN** the reviewer receives the RunContext and can access `ctx.deps`, `ctx.attempt`, etc.

#### Scenario: Legacy Reviewer without ctx still works

- **GIVEN** a `LegacyReviewer.review(self, context, codebase_context=None)` (no `ctx` parameter)
- **WHEN** the Agent calls `reviewer.review(context, cc)` without passing `ctx`
- **THEN** the LegacyReviewer runs normally

#### Scenario: Reviewer can adapt prompt based on ctx.attempt

- **GIVEN** a custom Reviewer that uses `ctx.attempt > 0` to add "previous attempt had invalid comments — please verify line numbers" to its prompt
- **WHEN** Agent.run retries (so `ctx.attempt == 1` on the second call)
- **THEN** the Reviewer's prompt includes the adaptive instruction on the retry call
