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

The framework SHALL define `RunContext[T]` as a generic Pydantic model with fields: `deps: T`, `pr_url: str`, `attempt: int = 0`. The model SHALL allow arbitrary types in `deps` so non-Pydantic dependencies (functions, callables, stateful objects) round-trip. NO untyped `metadata` field is included (per adversarial review 5.4 — typed escape hatches go on user-supplied PeerDeps subclasses).

#### Scenario: RunContext carries typed deps

- **WHEN** `RunContext[PeerDeps](deps=PeerDeps(...), pr_url="https://...")` is constructed
- **THEN** the resulting object has `ctx.deps` of type `PeerDeps` and `ctx.pr_url` as a string

#### Scenario: Retry attempts visible in ctx

- **WHEN** `RunContext` is constructed inside an Agent retry loop
- **THEN** `ctx.attempt` is `0` for the first call, `1` for the first retry, etc., available to Reviewers + Evaluators for adaptive behavior

#### Scenario: No metadata escape hatch

- **WHEN** a user attempts `RunContext(deps=..., pr_url=..., metadata={"x": 1})`
- **THEN** validation rejects `metadata` (no such field); typed extension lives on user-supplied `PeerDeps` subclasses, not on `RunContext`

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

**Implementation note (concurrency-safe):** The recorder is held in a `contextvars.ContextVar` that EvalRunner SHALL set INSIDE each per-sample task (in `_eval_sample`, not at the outer `run_async` boundary). Each concurrent task gets its OWN list-shaped recorder; on task completion, its list is attached to that sample's `EvalSampleResult.captured_messages`. Under `peer eval --capture-messages --concurrency N`, samples do NOT interleave — each sample's capture is isolated.

#### Scenario: Capture within block

- **WHEN** `with capture_run_messages() as msgs: agent.run(pr_url, deps=...)` executes
- **THEN** on context exit, `msgs` is a list with one `CapturedMessage` containing the full prompt + response from that run

#### Scenario: No capture outside block

- **WHEN** `agent.run(pr_url, deps=...)` is called outside any `capture_run_messages` block
- **THEN** no capture is performed (no overhead)

#### Scenario: Persistent capture via Agent flag

- **WHEN** `Agent(capture_messages=True)` is constructed and a subsequent `run` is made
- **THEN** `agent.last_messages` contains the captured messages from the most recent run (overwritten by subsequent runs)

#### Scenario: Async per-task capture isolation

- **WHEN** `EvalRunner(reviewer, dataset, concurrency=5).run_async()` is invoked inside a `with capture_run_messages() as msgs:` block AND the dataset has 5+ samples
- **THEN** each `EvalSampleResult.captured_messages` contains exactly that sample's prompt + response — captures do NOT cross-leak across concurrent tasks

### Requirement: EvalReport.from_json is forward-compatible (additive fields)

Per adversarial review 3.7 — multiple in-flight changes touch the `EvalReport` schema additively (peer-deps-v01 adds `captured_messages`; eval-metrics-v01 adds new metrics; patch-suggestions-v01 extends Comment). `EvalReport.from_json` SHALL accept unknown fields when the major schema version matches (e.g., loading a v1.5 report with v1.2 loader). Pydantic's `model_config = ConfigDict(extra="ignore")` on EvalReport + EvalSampleResult + EvalSummary applied. Only on MAJOR-version mismatch (e.g., 1.x → 2.x) does the loader raise.

#### Scenario: Newer minor-version report loads under older loader

- **GIVEN** a v1.5 report file containing fields the v1.2 loader doesn't recognize (e.g., `captured_messages`)
- **WHEN** `EvalReport.from_json(path)` is called by the v1.2 loader
- **THEN** the report loads successfully; unknown fields are silently dropped from the in-memory model

#### Scenario: Major-version mismatch raises

- **GIVEN** a v2.0 report file
- **WHEN** `EvalReport.from_json(path)` is called by the v1.x loader
- **THEN** `EvalReportSchemaMismatch` is raised with migration guidance

### Requirement: Reviewers handle rate-limit (429) responses with backoff

Per adversarial review 4.1 — at concurrency=5 + benchmark-v01 (118 reviews back-to-back), Anthropic per-minute rate limits become the most common failure mode. Each shipped Reviewer SHALL detect HTTP 429 / Anthropic rate-limit errors and retry with exponential backoff (1s, 2s, 4s, 8s, max 4 retries). On final failure after retries, the Reviewer raises `ReviewerRateLimited` (new exception in `peer.exceptions`); EvalRunner catches and marks the sample as `error="rate_limited"` rather than abort the entire run.

#### Scenario: 429 triggers backoff retry

- **GIVEN** ClaudeReviewer receiving HTTP 429 on the first attempt and HTTP 200 on the second
- **WHEN** `review()` is called
- **THEN** the reviewer waits ~1s, retries, succeeds, and the returned Review's usage records `n_rate_limit_retries=1`

#### Scenario: 4 retries exhausted

- **GIVEN** ClaudeReviewer receiving HTTP 429 on 5 consecutive attempts
- **WHEN** `review()` is called
- **THEN** `ReviewerRateLimited` is raised after the 4th retry; the exception carries the cumulative wait time + the underlying error

### Requirement: LLMCallsDisabled exception

The framework SHALL add `LLMCallsDisabled` to `peer.exceptions`. The exception's `__init__` SHALL accept an optional message; the default message SHALL include the specific override-pattern fix ("Use Agent.override(reviewer=TestReviewer()) for tests.").

#### Scenario: Default message includes fix

- **WHEN** `LLMCallsDisabled()` is raised with no message
- **THEN** `str(exc)` includes the string "Agent.override(reviewer=TestReviewer())"
