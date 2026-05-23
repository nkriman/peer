## 1. Type schemas (foundation)

- [ ] 1.1 Create `src/peer/types.py` with Pydantic models: `Severity` literal (`critical`/`important`/`minor`/`nit`), `Comment`, `Review`, `ContextHunk`, `Context`
- [ ] 1.2 Define exceptions module: `UnknownModelError`, `InvalidPRURL`, `PRNotAccessible`, `GHCLINotAvailable`, `GHCLINotAuthenticated`, `ContextTooLarge` in `src/peer/exceptions.py`
- [ ] 1.3 Update `src/peer/__init__.py` to export the public schema names

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
- [ ] 3.4 Author the default system prompt for PR review and put it in `src/peer/prompts.py` (configurable override at `Agent` init time)

## 4. Agent dispatch + validation (`src/peer/agent.py`)

- [ ] 4.1 Implement model-to-Reviewer dispatch (anthropic prefix → ClaudeReviewer; gpt prefix → OpenAIReviewer; else `UnknownModelError`)
- [ ] 4.2 Implement `Agent.__init__(model, system_prompt=None)` storing the chosen Reviewer
- [ ] 4.3 Implement `Agent.review(pr_url) -> Review`: gather context → call Reviewer → validate comments → return Review
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
- [ ] 7.2 Add a "Requirements" section to README noting `gh` CLI dependency + `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`
- [ ] 7.3 Add a short `examples/single_pr.py` showing programmatic use
- [ ] 7.4 Note known limits in README: no chunking for large PRs (v0.2), GitHub only (v0.2), no caching (v0.2)
