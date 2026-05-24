## ADDED Requirements

### Requirement: PeerDeps is a dataclass carrying per-run dependencies

The framework SHALL define a `PeerDeps` dataclass in `peer.deps` with the following fields, all Optional with sensible defaults: `config` (PeerConfig or None), `classifier` (CommentClassifier or None), `taxonomy` (Taxonomy or None), `enrichment` (EnrichmentStep or None), `linters` (list of Linter, defaults to empty), `extra_instructions` (str or None). Additional fields MAY be added in future changes as new capabilities land.

#### Scenario: PeerDeps default construction

- **WHEN** `PeerDeps()` is constructed with no arguments
- **THEN** all fields take their defaults (`None` for Optional, empty list for `linters`)

#### Scenario: PeerDeps holds a configured pipeline

- **WHEN** `PeerDeps(config=cfg, linters=[RuffLinter()], extra_instructions="Focus on security.")` is constructed
- **THEN** all three fields are set on the dataclass and accessible as `deps.config`, `deps.linters`, `deps.extra_instructions`

### Requirement: RunContext is a typed Pydantic model carrying deps + run metadata

The framework SHALL define `RunContext[T]` as a generic Pydantic model with fields: `deps: T`, `pr_url: str`, `attempt: int = 0`, `metadata: dict = {}`. The model SHALL allow arbitrary types in `deps` so non-Pydantic dependencies (functions, callables, stateful objects) round-trip.

#### Scenario: RunContext carries typed deps

- **WHEN** `RunContext[PeerDeps](deps=PeerDeps(...), pr_url="https://...")` is constructed
- **THEN** the resulting object has `ctx.deps` of type `PeerDeps` and `ctx.pr_url` as a string

#### Scenario: Retry attempts visible in ctx

- **WHEN** `RunContext` is constructed inside an Agent retry loop
- **THEN** `ctx.attempt` is `0` for the first call, `1` for the first retry, etc., available to Reviewers + Evaluators for adaptive behavior

### Requirement: ALLOW_LLM_CALLS module-level flag prevents accidental LLM calls

The framework SHALL define `ALLOW_LLM_CALLS: bool = True` as a module-level attribute on `peer.deps`. Reviewers SHALL check this flag before any LLM SDK invocation and raise `LLMCallsDisabled` (new exception) when set to `False`.

#### Scenario: Flag set to False raises in real Reviewer

- **GIVEN** `peer.deps.ALLOW_LLM_CALLS = False`
- **WHEN** `ClaudeReviewer().review(context)` is called
- **THEN** `LLMCallsDisabled` is raised before any Anthropic SDK call is made

#### Scenario: Flag set to True allows real Reviewer

- **GIVEN** `peer.deps.ALLOW_LLM_CALLS = True` (default)
- **WHEN** `ClaudeReviewer().review(context)` is called
- **THEN** the LLM call proceeds normally

#### Scenario: TestReviewer ignores flag

- **GIVEN** `peer.deps.ALLOW_LLM_CALLS = False`
- **WHEN** `TestReviewer().review(context)` is called
- **THEN** the call proceeds normally — TestReviewer does not invoke LLMs

### Requirement: TestReviewer generates deterministic Comments without LLM calls

The framework SHALL provide `peer.reviewers.TestReviewer` that satisfies the `Reviewer` Protocol but produces Comments without invoking any LLM. Two modes: explicit comments (passed at construction) and synthesized comments (derived from `context.hunks`).

#### Scenario: Fixed-comments mode

- **WHEN** `TestReviewer(comments=[Comment(path="a.py", line=1, severity="minor", body="X", rationale="Y")]).review(context)` is called
- **THEN** the returned `(comments, usage)` is exactly the supplied list of one Comment + a usage dict with `input_tokens=0, output_tokens=0, model="test"`

#### Scenario: Synthesized-comments mode

- **WHEN** `TestReviewer(n_comments=2, severity="nit").review(context)` is called on a context with 3+ hunks
- **THEN** the returned list contains 2 Comments, each with `path/line` derived from the first two hunks, severity `"nit"`, and synthetic body+rationale

#### Scenario: Synthesized handles empty hunks

- **WHEN** `TestReviewer(n_comments=1).review(context)` is called on a context with zero hunks
- **THEN** the returned list is empty (no Comments to synthesize)

### Requirement: capture_run_messages context manager records prompts + responses

The framework SHALL provide `peer.context.capture_run_messages()` as a context manager that returns a list-shaped recorder accumulating `CapturedMessage` records for each `Agent.run` call inside the `with` block. Each `CapturedMessage` SHALL contain: `system_prompt`, `user_prompt`, `raw_response` (the LLM provider's full response object, serializable), `usage` (dict), `latency_ms` (float).

#### Scenario: Capture within block

- **WHEN** `with capture_run_messages() as msgs: agent.run(pr_url, deps=...)` executes
- **THEN** on context exit, `msgs` is a list with one `CapturedMessage` containing the full prompt + response from that run

#### Scenario: No capture outside block

- **WHEN** `agent.run(pr_url, deps=...)` is called outside any `capture_run_messages` block
- **THEN** no capture is performed (no overhead)

#### Scenario: Persistent capture via Agent flag

- **WHEN** `Agent(capture_messages=True)` is constructed and a subsequent `run` is made
- **THEN** `agent.last_messages` contains the captured messages from the most recent run (overwritten by subsequent runs)

### Requirement: LLMCallsDisabled exception

The framework SHALL add `LLMCallsDisabled` to `peer.exceptions`. The exception's `__init__` SHALL accept an optional message; the default message SHALL include the specific override-pattern fix ("Use Agent.override(reviewer=TestReviewer()) for tests.").

#### Scenario: Default message includes fix

- **WHEN** `LLMCallsDisabled()` is raised with no message
- **THEN** `str(exc)` includes the string "Agent.override(reviewer=TestReviewer())"
