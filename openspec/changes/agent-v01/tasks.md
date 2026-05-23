## 1. Type schemas (foundation)

- [x] 1.1 Create `src/peer/types.py` with Pydantic models: `Severity` literal (`critical`/`important`/`minor`/`nit`), `Comment` (with optional `references: list[str]`), `Review` (with `usage: dict` field for token tracking), `ContextHunk`, `Context`
- [x] 1.2 Add codebase-context Pydantic models to `src/peer/types.py`: `Symbol`, `CallSite`, `TestFile`, `CodebaseContext` (with fields per spec: `modified_symbols`, `call_sites`, `related_tests`, `untested_files`, `unsupported_files`, `parse_failures`, `token_estimate`, `truncations`)
- [x] 1.3 Define exceptions module: `UnknownModelError`, `InvalidPRURL`, `PRNotAccessible`, `GHCLINotAvailable`, `GHCLINotAuthenticated`, `ContextTooLarge`, `CodebaseContextTooLarge` in `src/peer/exceptions.py`
- [x] 1.4 Update `src/peer/__init__.py` to export the public schema names

## 2. Context module (`src/peer/context.py`)

- [x] 2.1 Add a `gh` CLI helper wrapper (shared with `curate.py` if possible) that runs commands, parses JSON, and raises `GHCLINotAvailable` / `GHCLINotAuthenticated` cleanly
- [x] 2.2 Implement PR URL parsing: extract `owner`, `repo`, `number` from a GitHub PR URL or raise `InvalidPRURL`
- [x] 2.3 Fetch PR metadata (title, body, head SHA) and the unified diff via `gh` CLI; raise `PRNotAccessible` on 403/404
- [x] 2.4 Implement diff hunk parser using `unidiff`: parse the raw unified-diff string into `PatchSet` → `PatchedFile` → `Hunk`, then project into our per-file `ContextHunk` records with original/new line ranges (Decision 15)
- [x] 2.5 Implement surrounding-code extractor: for each hunk, fetch the file at the head SHA and include ±N lines (default 20, configurable)
- [x] 2.6 Fetch prior issue + inline review comments via `gh api`
- [x] 2.7 Implement token-budget check using `tiktoken` (Decision 16): estimate assembled `Context` size via `tiktoken.get_encoding("cl100k_base").encode()` length; raise `ContextTooLarge` if it exceeds `max_tokens` (default 100,000)
- [x] 2.8 Implement top-level `gather(pr_url, context_lines=20, max_tokens=100_000) -> Context`

## 3. Reviewer implementations (`src/peer/reviewers.py`)

- [x] 3.1 Replace stub `Reviewer` Protocol with real one: `review(context: Context) -> list[Comment]`
- [x] 3.2 Implement `ClaudeReviewer` using Anthropic SDK tool-calling with a tool schema derived from the `Comment` Pydantic model
- [ ] 3.3 Implement `OpenAIReviewer` using OpenAI SDK structured outputs (`response_format=Comment`)
- [x] 3.4 Author the default system prompt for PR review and put it in `src/peer/prompts.py`. **MUST explicitly name `modified_symbols`, `call_sites`, `related_tests`, `untested_files` and direct the model to consult them** (per CodeCompass adoption-gap finding, Decision 13). Configurable override at `Agent` init via `system_prompt=` or `system_prompt_file=` (custom prompts used verbatim, no splicing).
- [x] 3.5 Each Reviewer implementation extracts usage info (`input_tokens`, `output_tokens`, `model`) from its SDK response and returns it alongside the comments
- [x] 3.6 Define a prompt-formatting helper in `src/peer/prompts.py` that takes `(Context, CodebaseContext)` and produces a labeled, sectioned string for the LLM (e.g., distinct `## PR DIFF`, `## MODIFIED SYMBOLS`, `## CALL SITES`, `## RELATED TESTS`, `## UNTESTED FILES` blocks)

## 4. Agent dispatch + validation (`src/peer/agent.py`)

- [x] 4.1 Implement model-to-Reviewer dispatch (anthropic prefix → ClaudeReviewer; gpt prefix → OpenAIReviewer; else `UnknownModelError`)
- [x] 4.2 Implement `Agent.__init__(model, system_prompt=None)` storing the chosen Reviewer
- [x] 4.3 Implement `Agent.review(pr_url) -> Review`: gather `Context` (pr-context) → gather `CodebaseContext` (codebase-context) → format combined prompt input → call Reviewer → validate comments → attach `usage` from the Reviewer → return `Review`. On `CodebaseContext` failure (e.g., tree-sitter unavailable), proceed with PR context only and log a `WARNING`.
- [x] 4.4 Implement comment-against-diff validation: drop any `Comment` whose `path` isn't in the diff or whose `line` falls outside any hunk; log warning per drop
- [x] 4.5 If the LLM produces no comments, return `Review(comments=[], reason="no issues found")`

## 5. CLI smoke test (`src/peer/review.py`)

- [x] 5.1 Implement `python -m peer.review <pr_url>` entry with `argparse` (`--model`, `--system-prompt-file` flags)
- [x] 5.2 Implement human-readable output: severity counts header + comments grouped by severity, with `path:line` prefix

## 6. Tests (`tests/`)

- [ ] 6.1 Unit tests for diff hunk parser (multiple files, multi-hunk per file, additions only, deletions only)
- [ ] 6.2 Unit tests for surrounding-code extractor (boundary at file start/end, custom N)
- [ ] 6.3 Unit tests for comment-against-diff validation (valid, invalid path, invalid line, edge of hunk)
- [ ] 6.4 Mock-based test for `Agent.review` end-to-end (mock Reviewer returns fixture comments; assert validation + Review shape)
- [ ] 6.5 Smoke integration test against one small real public PR, gated by `gh auth status` (skip if not authed)

## 7. Docs + repo polish

- [ ] 7.1 Update README quickstart with real `python -m peer.review` usage
- [ ] 7.2 Add a "Requirements" section to README: `gh` CLI (required for PR fetch); Python deps installed via `pip install peer` cover `ast-grep-py`, `tree-sitter`, `tree-sitter-python`, `unidiff`, `tiktoken`; `ripgrep` is an optional fallback (used only if `ast-grep` is unavailable); `ANTHROPIC_API_KEY` and/or `OPENAI_API_KEY` for the chosen backend
- [ ] 7.3 Add a short `examples/single_pr.py` showing programmatic use
- [ ] 7.4 Note known limits in README: Python-only tree-sitter coverage in v0.1; no chunking for large PRs (v0.2); GitHub only (v0.2); no caching (v0.2); no team-standards file or repo-map yet (v0.2 `codebase-context` extension); no vectors/embeddings (deferred indefinitely per Amazon Science 2026)

## 8. Codebase context (`src/peer/codebase_context.py`)

- [x] 8.1 Add to `pyproject.toml` dependencies (pin versions): `tree-sitter`, `tree-sitter-python`, `ast-grep-py`, `unidiff`, `tiktoken`. `ripgrep` documented as optional fallback in README "Requirements" (task 7.2)
- [x] 8.2 Define a `LanguageGrammar` registry pattern: maps file extension → tree-sitter `Language` + symbol-extraction queries; Python grammar registered for v0.1
- [x] 8.3 Implement modified-symbol extraction: for each modified file in the PR diff, parse with tree-sitter, walk the AST, extract `Symbol`s for any function/method/class whose source span overlaps any diff hunk; capture `kind`, `signature`, `enclosing_qualifier`, `start_line`, `end_line`
- [ ] 8.4 Handle deleted-symbol case: when a function/class is removed in the PR, source the `Symbol` from the parent commit (via `git show HEAD~1:path` or `gh api`) and mark `deleted=True`
- [x] 8.5 Implement call-site lookup via `ast-grep` (Decision 11, primary path): use the `ast-grep-py` Python API with structural patterns per kind (e.g., `Symbol` of kind `function` → `$NAME($$$ARGS)`; `method` → `$RECV.$NAME($$$ARGS)`; `class` → `$NAME($$$ARGS)` or `class $X($NAME)`); pattern selection lives in the `LanguageGrammar` registry alongside symbol-extraction queries. Subprocess fallback to `ast-grep` CLI if `ast-grep-py` import fails
- [ ] 8.6 Implement fallback chain when `ast-grep` is unavailable (Decision 14): (a) `ripgrep` candidate generation + tree-sitter post-filter to confirm call expressions; (b) pure-Python `pathlib.Path.rglob` + `re` candidate generation + tree-sitter post-filter. One-time `WARNING` log per fallback rung
- [ ] 8.7 _(consolidated into 8.5/8.6 above)_
- [x] 8.8 Implement test-file discovery: configurable `test_path_conventions` list with `{stem}`, `{name}`, `{path}` substitutions; defaults `["tests/test_{stem}.py", "src/test_{stem}.py", "tests/{stem}_test.py", "test_{stem}.py"]`; first existing match wins
- [x] 8.9 Implement test-file content inclusion with `max_test_file_chars` cap (default 5000), trailing `... (truncated, N chars)` marker, `truncated=True` flag
- [x] 8.10 Implement token-budget enforcement using `tiktoken` (Decision 16): estimate `CodebaseContext` size via `tiktoken.get_encoding("cl100k_base").encode()` length; apply priority-order trimming (`modified_symbols` always kept; `call_sites` trimmed by `max_call_sites_per_symbol` default 5; `related_tests` truncated then dropped); raise `CodebaseContextTooLarge` if even `modified_symbols` alone exceed budget
- [x] 8.11 Implement graceful degradation: missing `tree-sitter-python` → log `ERROR`, return empty `CodebaseContext` with `parse_failures` populated; per-file parse failure → log `WARNING`, add to `parse_failures`, continue
- [x] 8.12 Implement top-level `gather_codebase_context(pr_context: Context, max_tokens: int = 30_000, max_call_sites_per_symbol: int = 5, max_test_file_chars: int = 5000, test_path_conventions: list[str] | None = None) -> CodebaseContext`
- [ ] 8.13 Unit tests: symbol extraction (function/method/class, added/deleted, multi-hunk file); call-site lookup via `ast-grep` (true positive across files, no false positive on string-literal match, capped at max); fallback-chain unit test (ast-grep unavailable → ripgrep path produces same results; ripgrep also unavailable → Python-scan path produces same results); test-discovery (default convention hits, custom convention, no match); budget enforcement using `tiktoken` (under-budget no drops, over-budget priority order, modified-symbols-alone overflow raises)
- [ ] 8.14 Integration test: end-to-end on a small fixture repo with a known PR diff; assert returned `CodebaseContext` matches expected `modified_symbols` + `call_sites` + `related_tests`
