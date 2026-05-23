## Context

`peer` is at scaffolding stage: package skeleton, `curate.py` for gold-standard PR data, design rationale in `docs/`. No real LLM call exists yet — `Agent.review()` raises `NotImplementedError`. To validate the framework's core abstraction and unblock the eval work, the agent needs to actually produce a structured review from a PR URL.

The scope research (`docs/scope_research.md`) locked in architectural rules this design honors: narrow scope, multi-LLM, Pydantic-typed throughout, pluggable reviewer interface, no over-abstraction.

## Goals / Non-Goals

**Goals:**
- `Agent.review(pr_url) -> Review` works end-to-end for typical public GitHub PRs.
- Two LLM backends day 1: Claude (Anthropic SDK) and OpenAI.
- Output is Pydantic-validated; invalid LLM output is dropped, not crashed.
- The seam for adding more reviewers (local models, commercial adapters) is clean.
- A `python -m peer.review <pr_url>` CLI works for smoke-testing.

**Non-Goals:**
- Eval harness (covered by a separate change).
- GitLab / Bitbucket / Azure DevOps support.
- Auto-fix / auto-rewrite / PR description generation.
- Webhook / GitHub Action / CI integration.
- Chunking for very large PRs (defer to v0.2).
- Caching LLM responses (defer to v0.2).
- Local model support (defer to v0.2 — keep the seam, don't implement).

## Decisions

### 1. Pluggable Reviewer via Protocol

`Reviewer` stays a Python Protocol with `.review(context: Context) -> list[Comment]`. Two initial implementations: `ClaudeReviewer`, `OpenAIReviewer`. `Agent` is a thin dispatcher that picks the right Reviewer based on the configured model string.

**Why:** matches the "pluggable, composable" rule from scope research. Lets v0.3 add `GreptileAdapter` / `CodeRabbitAdapter` for benchmarking without refactoring the Agent.

**Alternative considered:** a single `Agent` class with `if/elif` branches per model. Rejected — would entangle backend specifics in the orchestration layer and make adding adapters painful.

### 2. Structured output via native SDK features

Use Anthropic's tool-calling and OpenAI's structured-outputs feature to enforce the `Comment` schema, not text parsing of free-form output.

**Why:** more reliable; aligns with the "Pydantic-typed surfaces" rule; saves us writing a fragile parser.

**Alternative considered:** ask the LLM for JSON and parse. Rejected — too fragile in practice; both SDKs now offer first-class structured output.

### 3. Context gathering via `gh` CLI subprocess

Reuse the `gh` CLI subprocess pattern already established in `curate.py`. No PyGithub token plumbing required in dev environments.

**Why:** consistency with `curate.py`; `gh` is already authed in most dev setups; one less environment variable to chase down for first-time users.

**Trade-off:** requires `gh` installed. Documented in README. PyGithub fallback noted as a v0.2 task if needed for production deployments.

### 4. Severity taxonomy: `critical` / `important` / `minor` / `nit`

Four levels, fixed for v0.1.

**Why:** matches what most commercial PR reviewers (CodeRabbit, etc.) use; familiar; small enough to evaluate cleanly; large enough to differentiate signal from noise.

**Alternative considered:** binary (issue / not), or finer-grained (bug / suggestion / style / nit / question). Rejected for v0.1 — binary loses too much signal; finer is hard to calibrate. The taxonomy is configurable in v0.2 if practice reveals the wrong split.

### 5. Surrounding code window: ±20 lines per hunk by default

Each diff hunk gets the surrounding ±20 lines of the file's current state, configurable.

**Why:** too little context loses the agent; too much wastes tokens. 20 lines is a working default reviewers often eye; empirical tuning belongs in v0.2.

### 6. Validate LLM-produced comments against the actual diff

Comments whose `path` or `line` don't appear in the PR diff are dropped with a warning, not surfaced to the user.

**Why:** LLMs occasionally hallucinate file paths or line numbers; surfacing those comments destroys user trust in the agent. Better to drop silently with a logged warning so it can be diagnosed in eval.

### 7. Ship an opinionated default system prompt; allow override

`peer` ships a default system prompt for PR review in `src/peer/prompts.py`. Users can override at `Agent` init via `Agent(system_prompt="...")` or `Agent(system_prompt_file=Path(...))`.

**Why:** the default gives users a working agent out of the box (matches the "one-line first use" rule from scope research); the override seam respects teams with strong opinions about review style. Resolved from v0.0 Open Question #1.

### 8. `Review.usage` captures per-call token cost

`Review` includes a `usage` field — a dict with at minimum `input_tokens`, `output_tokens`, and `model`. Each Reviewer implementation populates it from its SDK response.

**Why:** the v0.2 eval needs to report cost-per-review. Adding it now is one line per Reviewer impl and avoids a schema migration later. Per-Comment usage isn't a thing — usage is per LLM call, so it lives on `Review`, not `Comment`. Resolved from v0.0 Open Question #2.

### 9. Discussion history: include all prior PR comments

`Context` includes all prior issue and inline review comments on the PR, not a truncated subset.

**Why:** LLMs are good at filtering relevant from irrelevant; truncating loses audit-trail value. If a PR's discussion makes the assembled `Context` exceed the token budget, the existing `ContextTooLarge` check raises clearly so the user knows to address the specific PR rather than us silently dropping context. Resolved from v0.0 Open Question #3.

## Risks / Trade-offs

- **[Risk]** Structured-output reliability differs by model. **Mitigation:** ship Anthropic tool-calling first (proven), OpenAI structured outputs second; document any failure modes in `docs/`.
- **[Risk]** Context window overflow on large PRs. **Mitigation:** v0.1 raises a clear `ContextTooLarge` error and tells the user to skip; v0.2 will add chunking.
- **[Risk]** `gh` CLI dependency limits production deployability. **Mitigation:** documented; PyGithub fallback in v0.2.
- **[Risk]** LLM hallucinates file paths / line numbers. **Mitigation:** validate comments against the actual diff at parse time; drop invalid ones with a warning.
- **[Risk]** Token cost of running on full repos for eval becomes prohibitive. **Mitigation:** v0.1 caps eval sample size; document expected cost ranges in the eval change proposal (separate).

## Open Questions

None remaining for v0.1 scope — the three v0.0 questions were resolved into Decisions 7–9 above. Future-version questions (chunking strategy for large PRs, response caching, severity taxonomy revision) will live in their own change proposals.
