## 1. Types + module setup

- [ ] 1.1 Create `src/peer/deps.py` with `@dataclass PeerDeps` containing all Optional fields (config, classifier, taxonomy, enrichment, linters, extra_instructions). Module-level `ALLOW_LLM_CALLS: bool = True`.
- [ ] 1.2 Add `RunContext` Pydantic generic model to `src/peer/context.py` (or new `src/peer/runtime.py`). Carries `deps`, `pr_url`, `attempt`, `metadata`.
- [ ] 1.3 Add `LLMCallsDisabled` to `src/peer/exceptions.py`; default message references the override-fix.
- [ ] 1.4 Add `CapturedMessage` Pydantic model to the same module as `RunContext`: `system_prompt`, `user_prompt`, `raw_response` (dict for round-trip), `usage`, `latency_ms`.

## 2. capture_run_messages

- [ ] 2.1 Implement `capture_run_messages()` context manager in `src/peer/context.py`. Uses contextvars to maintain a per-thread/task list. `Agent.run` checks the contextvar before each Reviewer call; on hit, appends a CapturedMessage post-call.
- [ ] 2.2 Add `Agent.last_messages: list[CapturedMessage]` instance attr; populated when `capture_messages=True` was set in `__init__`.

## 3. TestReviewer

- [ ] 3.1 Implement `TestReviewer` in `src/peer/reviewers.py` per design.md Decision 7. Two modes: fixed list (passed at init) and synthesized (derived from context.hunks).
- [ ] 3.2 Add `name = "test"` attribute so Reviewer dispatch logic can identify it.
- [ ] 3.3 Export `TestReviewer` from `src/peer/__init__.py` AND `src/peer/reviewers.py`.

## 4. Provider:model parsing

- [ ] 4.1 Add `_parse_model_id(s: str) -> tuple[str, str]` helper in `src/peer/agent.py`. Splits on `:`. Bare names → infer provider (claude* → anthropic, gpt*/o[1-9]* → openai) + emit DeprecationWarning.
- [ ] 4.2 Update `_select_reviewer` to take `(provider, model_id)` instead of single string. Map: anthropic → ClaudeReviewer, openai → OpenAIReviewer (still NotImplementedError per agent-v01 task 3.3).
- [ ] 4.3 Update existing Reviewer class signatures: `ClaudeReviewer(model: str, ...)` where `model` is the model_id (no provider prefix).

## 5. Agent constructor refactor

- [ ] 5.1 Update `Agent.__init__` to new signature per design.md Decision 3.
- [ ] 5.2 Add `deps_type: Type[T] = PeerDeps` for type checkers.
- [ ] 5.3 Add `retries: dict = field(default_factory=lambda: {"output": 1})`.
- [ ] 5.4 Add `capture_messages: bool = False`.
- [ ] 5.5 Keep legacy kwargs (`system_prompt_file`, `team_conventions`, `team_conventions_file`, `config`, `config_file`) but route them into an internal `self._default_deps: PeerDeps`. Emit `DeprecationWarning` on each.
- [ ] 5.6 Reject mutually-exclusive combinations as currently done (`system_prompt` + `system_prompt_file`, etc.).

## 6. Agent.run + back-compat Agent.review

- [ ] 6.1 Implement `Agent.run(pr_url: str, deps: T) -> Review`. Flow: gather context → gather codebase context → build RunContext → call Reviewer with ctx → validate → retry loop (Tasks 8) → return Review.
- [ ] 6.2 Update existing `Agent.review(pr_url)` to be a thin shim: `return self.run(pr_url, deps=self._default_deps)`.
- [ ] 6.3 Pass `ctx: RunContext[T]` to Reviewer when the Reviewer's signature accepts it (use `inspect.signature` to detect; safe for legacy reviewers).

## 7. Agent.override context manager

- [ ] 7.1 Implement `Agent.override(*, model=None, deps=None, reviewer=None)` as a context manager via `contextlib.contextmanager`.
- [ ] 7.2 Maintain a per-agent stack of overrides (instance attr `_override_stack: list[dict]`).
- [ ] 7.3 On `__enter__`: push original values, apply overrides.
- [ ] 7.4 On `__exit__`: pop, restore.
- [ ] 7.5 Verify re-entrance: nested overrides work; exception inside inner block restores both levels.

## 8. Validation retries

- [ ] 8.1 Update `_validate_comments` to ALSO return the list of dropped comments + reasons.
- [ ] 8.2 In `Agent.run`, after first validation pass, if dropped > 0 and `self.retries['output'] > 0`:
  - Construct follow-up user message: include the dropped Comment list + their failure reasons + the diff hunks for grounding
  - Bump `ctx.attempt` (or construct new RunContext with `attempt=current+1`)
  - Re-invoke the Reviewer with the augmented message history
  - Re-validate
  - Decrement budget
- [ ] 8.3 Track `n_retries_used` in `Review.usage`.
- [ ] 8.4 Log INFO on each retry; INFO on retry-budget exhaustion.

## 9. ALLOW_LLM_CALLS enforcement in Reviewers

- [ ] 9.1 At the top of `ClaudeReviewer.review`, check `if not peer.deps.ALLOW_LLM_CALLS: raise LLMCallsDisabled()`.
- [ ] 9.2 Same for OpenAIReviewer when implemented.
- [ ] 9.3 NOT for TestReviewer.

## 10. Tests

- [ ] 10.1 `tests/test_deps.py` — PeerDeps default + populated construction; round-trip via dataclass.
- [ ] 10.2 `tests/test_runcontext.py` — RunContext[PeerDeps] generic; deps + attempt + metadata fields; serialization.
- [ ] 10.3 `tests/test_allow_llm_calls.py` — flag=False raises in ClaudeReviewer; flag=True allows; TestReviewer ignores flag.
- [ ] 10.4 `tests/test_test_reviewer.py` — fixed mode returns supplied list; synthesized mode synthesizes N from hunks; empty hunks → empty.
- [ ] 10.5 `tests/test_capture_messages.py` — capture_run_messages context manager records prompt + response; persistent mode populates `agent.last_messages`; no overhead outside block.
- [ ] 10.6 `tests/test_agent_override.py` — simple override; nested overrides stack and unwind; exception inside block restores.
- [ ] 10.7 `tests/test_validation_retries.py` — mock Reviewer returns bad-line on attempt 0, valid on attempt 1, with retries=1 — final Review has valid Comment + n_retries_used==1; retries=0 — bad Comment dropped, no retry.
- [ ] 10.8 `tests/test_model_format.py` — canonical "anthropic:claude-sonnet-4-6" works; bare "claude-sonnet-4-6" emits DeprecationWarning + works; "unknown:xyz" raises UnknownModelError.
- [ ] 10.9 `tests/test_agent_back_compat.py` — legacy `Agent(model="claude-sonnet-4-6", team_conventions="...").review(pr_url)` still works (with deprecation warnings); the legacy team_conventions value is folded into self._default_deps.extra_instructions.
- [ ] 10.10 Existing test suites stay green: re-run `pytest tests/` post-refactor; fix any regressions.

## 11. Docs

- [ ] 11.1 Update README quickstart to show the new `Agent(model="anthropic:claude-sonnet-4-6", deps_type=PeerDeps).run(pr_url, deps=PeerDeps(...))` pattern. Show migration from old pattern.
- [ ] 11.2 Add a "Testing" section to `docs/framework_overview.md` covering Agent.override, TestReviewer, ALLOW_LLM_CALLS, capture_run_messages. Pytest fixture example.
- [ ] 11.3 Migration note in CHANGELOG (or RELEASE_NOTES.md): legacy kwargs emit DeprecationWarning; replacement pattern; planned removal in v1.0.

## 12. Eval framework integration

- [ ] 12.1 Update `EvalRunner` (already lazy-init Anthropic client per eval-metrics-v01) to use `agent.override(reviewer=TestReviewer())` pattern in its own test fixtures. Document the pattern.
- [ ] 12.2 Add `EvalSampleResult.captured_messages: Optional[list[CapturedMessage]] = None` field. EvalRunner runs each sample inside a `capture_run_messages` block when configured.
- [ ] 12.3 `peer eval` CLI gets `--capture-messages` flag that populates the per-sample captured_messages in the saved report.

## 13. Verification

- [ ] 13.1 Run full test suite; confirm 100% pass.
- [ ] 13.2 Re-run `peer eval --dataset dataset/reference/django_pydantic_v2.jsonl` to confirm no behavior regression. Save to `data/eval_runs/reference_v2_sonnet46_peer_deps_v01.json`. Diff vs the prompt-quality-v01 baseline; expect ~0 metric delta (this is a refactor, not a behavior change).
- [ ] 13.3 Sanity check: re-run with `Agent(retries={"output": 2})` on at least one PR — verify retry path actually exercises (force a bad-line via a TestReviewer wrapper to confirm the retry-then-fix flow works end-to-end).
