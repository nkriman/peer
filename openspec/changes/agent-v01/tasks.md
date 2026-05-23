## 1. Type schemas (foundation)

- [ ] 1.1 Create `src/peer/types.py` with Pydantic models: `Severity` literal (`critical`/`important`/`minor`/`nit`), `Comment` (with optional `references: list[str]`), `Review` (with `usage: dict` field for token tracking), `ContextHunk`, `Context`
- [ ] 1.2 Add codebase-context Pydantic models to `src/peer/types.py`: `Symbol`, `CallSite`, `TestFile`, `CodebaseContext` (with fields per spec: `modified_symbols`, `call_sites`, `related_tests`, `untested_files`, `unsupported_files`, `parse_failures`, `token_estimate`, `truncations`)
- [ ] 1.3 Define exceptions module: `UnknownModelError`, `InvalidPRURL`, `PRNotAccessible`, `GHCLINotAvailable`, `GHCLINotAuthenticated`, `ContextTooLarge`, `CodebaseContextTooLarge` in `src/peer/exceptions.py`
- [ ] 1.4 Update `src/peer/__init__.py` to export the public schema names

## 2. Context module (`src/peer/context.py`)

- [ ] 2.1 Add a `gh` CLI helper wrapper (shared with `curate.py` if possible) that runs commands, parses JSON, and raises `GHCLINotAvailable` / `GHCLINotAuthenticated` cleanly
- [ ] 2.2 Implement PR URL parsing: extract `owner`, `repo`, `number` from a GitHub PR URL or raise `InvalidPRURL`
- [ ] 2.3 Fetch PR metadata (title, body, head SHA) and the unified diff via `gh` CLI; raise `PRNotAccessible` on 403/404
- [ ] 2.4 Implement diff hunk parser: produce per-file hunks with their original/new line ranges
- [ ] 2.5 Implement surrounding-code extractor: for each hunk, fetch the file at the head SHA and include ±N lines (default 20, configurable)
- [ ] 2.6 Fetch prior issue + inline review comments via `gh api`
- [ ] 2.7 Implement token-budget check: estimate assembled `Context` size; raise `ContextTooLarge` if it exceeds `max_tokens` (default 100,000)
- [ ] 2.8 Implement top-level `gather(pr_url, context_lines=20, max_tokens=100_000) -> Context`

## 3. Reviewer implementations (`src/peer/reviewers.py`)

- [ ] 3.1 Replace stub `Reviewer` Protocol with real one: `review(context: Context) -> list[Comment]`
- [ ] 3.2 Implement `ClaudeReviewer` using Anthropic SDK tool-calling with a tool schema derived from the `Comment` Pydantic model
- [ ] 3.3 Implement `OpenAIReviewer` using OpenAI SDK structured outputs (`response_format=Comment`)
- [ ] 3.4 Author the default system prompt for PR review and put it in `src/peer/prompts.py`. **MUST explicitly name `modified_symbols`, `call_sites`, `related_tests`, `untested_files` and direct the model to consult them** (per CodeCompass adoption-gap finding, Decision 13). Configurable override at `Agent` init via `system_prompt=` or `system_prompt_file=` (custom prompts used verbatim, no splicing).
- [ ] 3.5 Each Reviewer implementation extracts usage info (`input_tokens`, `output_tokens`, `model`) from its SDK response and returns it alongside the comments
- [ ] 3.6 Define a prompt-formatting helper in `src/peer/prompts.py` that takes `(Context, CodebaseContext)` and produces a labeled, sectioned string for the LLM (e.g., distinct `## PR DIFF`, `## MODIFIED SYMBOLS`, `## CALL SITES`, `## RELATED TESTS`, `## UNTESTED FILES` blocks)

## 4. Agent dispatch + validation (`src/peer/agent.py`)

- [ ] 4.1 Implement model-to-Reviewer dispatch (anthropic prefix → ClaudeReviewer; gpt prefix → OpenAIReviewer; else `UnknownModelError`)
- [ ] 4.2 Implement `Agent.__init__(model, system_prompt=None)` storing the chosen Reviewer
- [ ] 4.3 Implement `Agent.review(pr_url) -> Review`: gather `Context` (pr-context) → gather `CodebaseContext` (codebase-context) → format combined prompt input → call Reviewer → validate comments → attach `usage` from the Reviewer → return `Review`. On `CodebaseContext` failure (e.g., tree-sitter unavailable), proceed with PR context only and log a `WARNING`.
- [ ] 4.4 Implement comment-against-diff validation: drop any `Comment` whose `path` isn't in the diff or whose `line` falls outside any hunk; log warning per drop
- [ ] 4.5 If the LLM produces no comments, return `Review(comments=[], reason="no issues found")`

## 5. CLI smoke test (`src/peer/review.py`)

- [ ] 5.1 Implement `python -m peer.review <pr_url>` entry with `argparse` (`--model`, `--system-prompt-file` flags)
- [ ] 5.2 Implement human-readable output: severity counts header + comments grouped by severity, with `path:line` prefix

## 6. Tests (`tests/`)

- [ ] 6.1 Unit tests for diff hunk parser (multiple files, multi-hunk per file, additions only, deletions only)
- [ ] 6.2 Unit tests for surrounding-code extractor (boundary at file start/end, custom N)
- [ ] 6.3 Unit tests for comment-against-diff validation (valid, invalid path, invalid line, edge of hunk)
- [ ] 6.4 Mock-based test for `Agent.review` end-to-end (mock Reviewer returns fixture comments; assert validation + Review shape)
- [ ] 6.5 Smoke integration test against one small real public PR, gated by `gh auth status` (skip if not authed)

## 7. Docs + repo polish

- [ ] 7.1 Update README quickstart with real `python -m peer.review` usage
- [ ] 7.2 Add a "Requirements" section to README noting `gh` CLI, `rg` (ripgrep) recommended, and `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`
- [ ] 7.3 Add a short `examples/single_pr.py` showing programmatic use
- [ ] 7.4 Note known limits in README: Python-only tree-sitter coverage in v0.1; no chunking for large PRs (v0.2); GitHub only (v0.2); no caching (v0.2); no team-standards file or repo-map yet (v0.2 `codebase-context` extension); no vectors/embeddings (deferred indefinitely per Amazon Science 2026)

## 8. Codebase context (`src/peer/codebase_context.py`)

- [ ] 8.1 Add `tree-sitter` and `tree-sitter-python` to `pyproject.toml` dependencies; pin versions
- [ ] 8.2 Define a `LanguageGrammar` registry pattern: maps file extension → tree-sitter `Language` + symbol-extraction queries; Python grammar registered for v0.1
- [ ] 8.3 Implement modified-symbol extraction: for each modified file in the PR diff, parse with tree-sitter, walk the AST, extract `Symbol`s for any function/method/class whose source span overlaps any diff hunk; capture `kind`, `signature`, `enclosing_qualifier`, `start_line`, `end_line`
- [ ] 8.4 Handle deleted-symbol case: when a function/class is removed in the PR, source the `Symbol` from the parent commit (via `git show HEAD~1:path` or `gh api`) and mark `deleted=True`
- [ ] 8.5 Implement call-site lookup stage 1 (candidate generation): shell out to `ripgrep` with a `\b<symbol>\b` regex across the repo; collect file:line candidates
- [ ] 8.6 Implement call-site lookup stage 2 (false-positive filter): re-parse each candidate file with tree-sitter, confirm the matched location is an actual call expression referencing the symbol (not a string literal, comment, or unrelated identifier)
- [ ] 8.7 Implement ripgrep-missing fallback: when `rg` not on `PATH`, walk repo with Python (`pathlib.Path.rglob`) and per-file scan with `re`; one-time `WARNING` log
- [ ] 8.8 Implement test-file discovery: configurable `test_path_conventions` list with `{stem}`, `{name}`, `{path}` substitutions; defaults `["tests/test_{stem}.py", "src/test_{stem}.py", "tests/{stem}_test.py", "test_{stem}.py"]`; first existing match wins
- [ ] 8.9 Implement test-file content inclusion with `max_test_file_chars` cap (default 5000), trailing `... (truncated, N chars)` marker, `truncated=True` flag
- [ ] 8.10 Implement token-budget enforcement: estimate `CodebaseContext` size (approx via char-count / 4 heuristic OR `tiktoken` if available); apply priority-order trimming (`modified_symbols` always kept; `call_sites` trimmed by `max_call_sites_per_symbol` default 5; `related_tests` truncated then dropped); raise `CodebaseContextTooLarge` if even `modified_symbols` alone exceed budget
- [ ] 8.11 Implement graceful degradation: missing `tree-sitter-python` → log `ERROR`, return empty `CodebaseContext` with `parse_failures` populated; per-file parse failure → log `WARNING`, add to `parse_failures`, continue
- [ ] 8.12 Implement top-level `gather_codebase_context(pr_context: Context, max_tokens: int = 30_000, max_call_sites_per_symbol: int = 5, max_test_file_chars: int = 5000, test_path_conventions: list[str] | None = None) -> CodebaseContext`
- [ ] 8.13 Unit tests: symbol extraction (function/method/class, added/deleted, multi-hunk file); call-site lookup (true positive across files, false-positive filtered out, capped at max); test-discovery (default convention hits, custom convention, no match); budget enforcement (under-budget no drops, over-budget priority order, modified-symbols-alone overflow raises)
- [ ] 8.14 Integration test: end-to-end on a small fixture repo with a known PR diff; assert returned `CodebaseContext` matches expected `modified_symbols` + `call_sites` + `related_tests`
