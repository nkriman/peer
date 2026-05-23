## Why

We shipped `curate.py` (the data-collection script for gold-standard PR review data) but the framework has no actual review agent yet — `Agent.review()` is a `NotImplementedError` stub. To validate any of the eval methodology, we need a working agent that takes a PR and produces structured review comments — and per academic evidence (CodeCompass arXiv 2602.20048: +23pp task completion with structural codebase context; Amazon Science arXiv 2605.15184: grep + AST beats vectors), the agent needs more than just the diff to be more than a toy. This change ships the agent with enough codebase context to be empirically defensible at v0.1, while explicitly deferring the heavier context layers (Aider-style repo-map, team-standards file, embeddings) to later changes.

## What Changes

- Implement `Agent.review(pr_url)` end-to-end: gathers PR context, gathers codebase context, calls the chosen LLM, parses structured review output, returns a `Review`.
- Implement PR context gathering: fetch the diff, surrounding code snippets, PR description, and prior discussion from a GitHub PR URL.
- Implement **codebase context gathering**: tree-sitter–extracted definitions of modified symbols, call sites of modified symbols across the repo, and related test files by path convention.
- Define canonical Pydantic schemas: `Review`, `Comment`, `Context`, `CodebaseContext`, `Symbol`, `CallSite`, `TestFile`, severity taxonomy (`critical`, `important`, `minor`, `nit`).
- Multi-LLM dispatch from day 1: Claude (Anthropic SDK) and OpenAI as initial backends, with the seam clean for adding local models.
- Default system prompt that **explicitly directs the agent to consult the codebase context** (per CodeCompass adoption-gap finding: 58% of agents with structural context access made zero tool calls without explicit prompt instruction). Override seam via `Agent(system_prompt=)` / `system_prompt_file=`.
- Optional CLI entry point: `python -m peer.review <pr_url>` to run a single review for smoke-testing.

## Capabilities

### New Capabilities
- `pr-review-agent`: the orchestrating agent that reads PR + codebase context, calls an LLM, and returns a structured `Review` with severity-tagged inline comments.
- `pr-context`: context-gathering layer that pulls diff, surrounding code, PR description, and prior discussion for any GitHub PR URL.
- `codebase-context`: tree-sitter-driven extraction of modified-symbol definitions, cross-file call sites, and related test files; assembled into a token-budgeted `CodebaseContext` that flows into the agent's prompt.

### Modified Capabilities
<!-- None — `specs/` is empty at this point; this proposal seeds the first specs. -->

## Impact

- **Code**: `src/peer/agent.py`, `src/peer/context.py` (currently stubs) get real implementations. New `src/peer/codebase_context.py`. New `src/peer/types.py` for shared Pydantic schemas. New `src/peer/prompts.py` for the default system prompt. New `src/peer/review.py` for the CLI entry.
- **Dependencies**: `anthropic`, `openai` (already declared in `pyproject.toml`); add `tree-sitter` + `tree-sitter-python` (Python grammar only for v0.1), `ast-grep-py` (AST-native call-site lookup), `unidiff` (diff hunk parsing), `tiktoken` (token-budget estimation). `ripgrep` is a recommended runtime dependency used only as a fallback if `ast-grep` is unavailable; pure-Python scanning is the final fallback. Per `docs/oss_leverage_research.md`.
- **No changes** to `curate.py` yet. README gains a "Requirements" section noting `gh`, `rg`, and API keys.
- **Language scope for v0.1**: Python only for tree-sitter extraction. PRs containing non-Python files still review (the LLM sees the diff), but `CodebaseContext` for non-Python files is empty. Other languages land via the language-grammar seam in subsequent changes.
- **Out of scope for this change**: eval implementation (separate proposal), team-standards file (v0.2 `codebase-context` extension), Aider-style repo-map (v0.2), embeddings/vectors (deferred indefinitely per Amazon Science evidence), GitHub Action / webhook deployment, GitLab/Bitbucket support, observability integration, multi-language tree-sitter coverage.
