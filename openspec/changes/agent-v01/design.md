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

### 10. Tree-sitter as the AST substrate (Python only in v0.1)

`peer` uses `tree-sitter` via the `py-tree-sitter` bindings, shipped with the `tree-sitter-python` grammar in v0.1. A `LanguageGrammar` registry exposes a single-line registration seam so future changes add TypeScript / Go / Rust / etc. without touching the extraction pipeline.

**Why:** tree-sitter is the de facto standard for AST extraction across leading AI coding tools (Aider, Codebase-Memory at 900+ stars in 4 weeks per arXiv 2603.27277, CodeRabbit). It covers 66+ languages. Python first because (a) `peer` is itself Python so dogfooding works immediately and (b) Python is the dominant language in our gold-standard dataset (Django + Pydantic).

**Alternative considered:** ast-grep (semgrep-style AST queries). Rejected because tree-sitter ecosystem (grammars + bindings) is materially larger and the integration pattern is better-trodden for our use case.

### 11. Call-site lookup via ripgrep + tree-sitter false-positive filter

Call sites for modified symbols are found in two stages: (a) `ripgrep` (or Python fallback) for fast text-level candidate lines, (b) re-parse each candidate file with tree-sitter and confirm the match is an actual call expression referencing the symbol (not a string literal, comment, or unrelated identifier with the same name).

**Why:** matches the 2026 academic consensus (Amazon Science arXiv 2605.15184: grep + structural validation outperforms pure vector retrieval). Two-stage filter gives high precision without building a full code graph. Significantly cheaper than persistent indexing while delivering most of the value per the Amazon paper.

**Alternative considered:** build a persistent symbol-graph index (à la Sourcegraph). Rejected for v0.1 — too much infrastructure for the expected v0.1 use cases (single-PR ad-hoc reviews), and the index staleness problem (when does it re-index?) is a substantial design problem in its own right.

### 12. Test-file discovery via configurable path conventions

Related test files are discovered by mapping source paths to test paths via configurable conventions. Defaults cover Python pytest patterns (`tests/test_X.py`, `src/test_X.py`, `tests/X_test.py`, `test_X.py`).

**Why:** convention-based discovery is fast, deterministic, and easy to reason about. Per CodeRabbit's published architecture, test inclusion is a Tier 1 context component. Default conventions cover ~95% of Python projects; the configurable hook covers the rest.

**Alternative considered:** test-discovery via test runner integration (e.g., `pytest --collect-only`). Rejected for v0.1 — adds runtime dependencies and complexity disproportionate to value at v0.1.

### 13. The default system prompt MUST explicitly direct use of codebase context

The default system prompt (`src/peer/prompts.py`) explicitly names `modified_symbols`, `call_sites`, `related_tests`, `untested_files` and instructs the LLM to consult them when formulating each comment.

**Why:** this is the most important single implementation lesson from CodeCompass (arXiv 2602.20048, Feb 2026). The paper measured that, with structural codebase context available via MCP tools, **58% of trials made zero tool calls** — the agent simply ignored the context. The fix the paper validates is explicit prompt-level instruction. Skipping this would silently erode most of the value of the codebase-context capability.

**User override (Decision 7) still applies:** users can pass `system_prompt=` or `system_prompt_file=` to override. The framework does not splice or merge — overrides are the user's full responsibility, including any context-use directives.

### 14. Graceful degradation, not hard failure

The codebase-context capability degrades when optional dependencies are missing rather than blocking the whole review:

- Missing `tree-sitter` / `tree-sitter-python` → log `ERROR`, return empty `CodebaseContext`, agent proceeds with PR context only
- Missing `ripgrep` → fall back to Python file scanning with one-time `WARNING`
- Tree-sitter parse failure on a specific file → skip that file, record under `parse_failures`, continue

**Why:** if v0.1 makes any one dependency fatal, adoption stalls. The framework's primary contract is "produce a Review" — it should always do that, with the best context it can assemble. Diagnostics live in the `CodebaseContext` fields (`unsupported_files`, `parse_failures`, `truncations`) for the eval to surface.

## Risks / Trade-offs

- **[Risk]** Structured-output reliability differs by model. **Mitigation:** ship Anthropic tool-calling first (proven), OpenAI structured outputs second; document any failure modes in `docs/`.
- **[Risk]** Context window overflow on large PRs. **Mitigation:** v0.1 raises a clear `ContextTooLarge` error and tells the user to skip; v0.2 will add chunking.
- **[Risk]** `gh` CLI dependency limits production deployability. **Mitigation:** documented; PyGithub fallback in v0.2.
- **[Risk]** LLM hallucinates file paths / line numbers. **Mitigation:** validate comments against the actual diff at parse time; drop invalid ones with a warning.
- **[Risk]** Token cost of running on full repos for eval becomes prohibitive. **Mitigation:** v0.1 caps eval sample size; document expected cost ranges in the eval change proposal (separate).
- **[Risk]** Agent ignores codebase context (CodeCompass adoption gap: 58% zero tool calls without explicit prompting). **Mitigation:** Decision 13 — default system prompt explicitly names every codebase-context field and instructs the LLM to consult them. Tracked in eval: if comments don't reference codebase-context items meaningfully, the prompt needs sharpening.
- **[Risk]** tree-sitter grammar version drift or install issues block context extraction. **Mitigation:** pin `tree-sitter` and `tree-sitter-python` in `pyproject.toml`; graceful degradation per Decision 14 (review still completes with PR context only).
- **[Risk]** Call-site lookup misses dynamic dispatch / monkey-patching / metaprogramming usages. **Mitigation:** documented limit. v0.1 catches static call sites only. The eval will surface where this matters; an upgrade path (LSP-style references, ast-grep patterns) lives in a v0.2+ change.
- **[Risk]** False-positive call sites despite the tree-sitter filter stage (e.g., shadowed names, same-name unrelated functions in other modules). **Mitigation:** cap call sites per symbol (default 5); log the truncation; acceptable v0.1 limit.
- **[Risk]** Multi-language repos get partial coverage in v0.1 (Python tree-sitter only). **Mitigation:** documented; non-Python files in PRs still see the diff in the LLM prompt — the `CodebaseContext` is empty for those files, recorded in `unsupported_files`. Language grammars are an additive-only extension per the `LanguageGrammar` registry.
- **[Risk]** `CodebaseContext` token cost compounds with `Context` token cost on the same PR. **Mitigation:** separate, additive budget for codebase context (default `30_000` tokens vs `100_000` for PR context); prioritized drop order (modified_symbols > call_sites > related_tests) so the most important context is always kept.

## Open Questions

None remaining for v0.1 scope — the three v0.0 questions were resolved into Decisions 7–9 above. Future-version questions (chunking strategy for large PRs, response caching, severity taxonomy revision) will live in their own change proposals.
