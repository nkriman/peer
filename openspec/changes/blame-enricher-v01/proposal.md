## Why

Senior reviewers rely heavily on file history when reasoning about a PR. "When was this last touched? By whom? For what reason?" answers questions the diff alone can't: is this old battle-tested code being changed, or recent code still in flux? Did the same author write the surrounding code (likely consistent style) or not (likely needs convention-check)?

peer's `gather_codebase_context` produces `modified_symbols`, `call_sites`, `related_tests`, `untested_files`, `linter_findings`. It doesn't surface git history at all. The model sees the code as if it sprang into existence — no authorship, no recency, no "this file is owned by team X."

Adding git-blame as a context section is cheap (we already clone the repo for tree-sitter parsing), high signal (every senior reviewer uses it), and orthogonal to existing levers (works regardless of model, recipe, or strategy). It also unblocks the per-context-source study in our research arc — "does authorship signal lift recall?"

This change adds git-blame context concretely. NOT behind an `Enricher` Protocol — we have one enricher today (RuffLinter) which works fine without abstraction. We'll extract a `peer.enrichers` Protocol later when we have a 2nd or 3rd concrete implementation and the patterns are visible.

## What Changes

- New `peer.context_git.gather_git_history(repo_path: Path, hunks: list[ContextHunk], n_recent_commits: int = 3) -> str` — pure function that returns formatted markdown blame text for inclusion in the prompt. Per modified path: lists the last N commits that touched the file (short hash + author + subject line + date) plus a `git blame` of the modified-line ranges (short hash + author per line).
- Extend `CodebaseContext` Pydantic model with `git_history: str = ""` field (defaults empty; opt-in via Recipe).
- Extend `gather_codebase_context()` signature with `include_git_history: bool = False` parameter. When True AND a repo_path was successfully checked out, populate `cc.git_history` via `gather_git_history`. Failures (no git, no repo, malformed output) log a WARNING and leave `git_history=""` — graceful degradation matches the linter pattern.
- Extend `format_prompt(ctx, cc)` to render a `## GIT HISTORY` section when `cc.git_history` is non-empty. Section format: per-path bullet list of recent commits + per-hunk blame lines, each labeled with `@@ -line,+span @@ in <path>:`.
- Extend `Recipe` with `include_git_history: bool = False` field. `Recipe.apply_to_agent` SHALL NOT directly enable this — wiring happens via `deps.include_git_history` consumed by `Agent.run` when calling `gather_codebase_context`. (Mirrors how `peer-config-v01` + `linter-context-v01` plumb deps into the gather.)

## Capabilities

### New Capabilities

- `blame-enricher`: git-blame context section (pure function + CodebaseContext field + prompt rendering + Recipe toggle).

### Modified Capabilities

- `codebase-context` (from agent-v01): `CodebaseContext` gains `git_history: str = ""`; `gather_codebase_context` gains `include_git_history: bool = False`.
- `pr-review-agent`: `Agent.run` propagates `recipe.include_git_history` (when set) into `gather_codebase_context`.
- `prompt-quality-v01`: `format_prompt` renders the new section when present.

## Impact

- **Code**: new `src/peer/context_git.py`. Modifications: `src/peer/types.py` (CodebaseContext field), `src/peer/codebase_context.py` (gather signature + call site), `src/peer/prompts.py` (format_prompt rendering), `src/peer/recipe.py` (Recipe field), `src/peer/agent.py` (deps plumbing).
- **Dependencies**: none new. Uses `git` via subprocess (same pattern as `_ensure_repo_checkout`).
- **Tests**: BDD in `features/blame_enricher.feature` covering pure-function behavior + format_prompt rendering + Recipe toggle. No live `git` subprocess in BDD; patch `subprocess.run` to return canned output.
- **Schema**: `CodebaseContext.git_history` is an additive optional field; back-compat preserved.
- **Back-compat**: default off. `Recipe()` with no overrides produces today's behavior.
- **Out of scope**: NO `Enricher` Protocol abstraction yet (premature). NO per-author / per-team routing logic. NO blame-driven auto-mentions. Just: get the history into the prompt, then measure.
- **Performance**: when enabled, adds 1-3 `git log` + 1 `git blame` subprocess invocations per modified file. On a 7-file PR that's ~30 subprocess calls; each is fast (≤100ms). Adds ~3K-10K tokens to the prompt depending on PR size — relevant for the context-budget interaction we just learned about.
