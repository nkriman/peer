## 1. Pure function

- [ ] 1.1 Create `src/peer/context_git.py` with `gather_git_history(repo_path, hunks, n_recent_commits=3) -> str` per spec.
- [ ] 1.2 Subprocess calls: `git log -n N --format=...` per path, `git blame -L start,+count --porcelain` per hunk.
- [ ] 1.3 Defensive: `check=False`, capture stderr, WARNING on failure, NEVER raise.

## 2. CodebaseContext field

- [ ] 2.1 Add `git_history: str = ""` to `peer.types.CodebaseContext` (Pydantic v2).

## 3. gather_codebase_context wiring

- [ ] 3.1 Add `include_git_history: bool = False` kwarg.
- [ ] 3.2 When True AND `_ensure_repo_checkout` returned a non-None path, call `gather_git_history` and store in `cc.git_history`.
- [ ] 3.3 Independent of `_have_tree_sitter()` — git history runs even if tree-sitter is unavailable.

## 4. format_prompt rendering

- [ ] 4.1 Add `## GIT HISTORY` section rendering when `cc.git_history` is non-empty, BEFORE `## LINTER FINDINGS`.
- [ ] 4.2 Header text per spec ("Recent commits and blame for files touched by this PR...").

## 5. Recipe field + plumbing

- [ ] 5.1 Add `include_git_history: bool = False` to `Recipe` (Pydantic).
- [ ] 5.2 `Recipe.apply_to_agent` SHOULD NOT call gather directly. Plumb via `Agent.run`: when `agent._recipe.include_git_history` is True at run-time, pass `include_git_history=True` to `gather_codebase_context`.
- [ ] 5.3 Store the active recipe on the agent (e.g. `agent._recipe = recipe`) so `run()` can consult it.

## 6. Exports

- [ ] 6.1 Export `gather_git_history` from `peer.context_git`.

## 7. BDD

- [ ] 7.1 `features/blame_enricher.feature` covering: pure-function format (1 scenario), empty hunks (1 scenario), git failure (1 scenario), CodebaseContext default (1 scenario), gather_codebase_context flag on/off (2 scenarios), format_prompt section present/absent (2 scenarios), Recipe field default (1 scenario), Recipe flag propagation (1 scenario).
- [ ] 7.2 Step defs patch `subprocess.run` to return canned `git log` + `git blame` output. No live `git` calls in BDD.

## 8. Quality gates

- [ ] 8.1 ruff / format / mypy / pytest / behave all clean.
