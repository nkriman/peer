## 1. Recipe model + prompt externalization

- [ ] 1.1 Move `DEFAULT_SYSTEM_PROMPT` text from `src/peer/prompts.py` to `prompts/default_system_prompt.md`. `peer.prompts` loads the file at import time (raise `FileNotFoundError` with clear path if missing).
- [ ] 1.2 Create `src/peer/recipe.py` with `Recipe` Pydantic model per spec. Add `to_yaml() / from_yaml()` methods.
- [ ] 1.3 Add `pyyaml` dep to `pyproject.toml`.
- [ ] 1.4 Add `Recipe.apply_to_agent(agent)` that mutates the agent in place (system_prompt, retries, reviewer rebuild with model+temperature+max_tokens).
- [ ] 1.5 Add `recipe: Recipe | None` kwarg to `Agent.__init__`. When set, recipe wins over explicit kwargs.

## 2. ClaudeReviewer temperature

- [ ] 2.1 Add `temperature: float = 0.0` + `max_tokens_override: int | None = None` to `ClaudeReviewer.__init__`.
- [ ] 2.2 Pass `temperature=self.temperature` to `client.messages.create(...)`.
- [ ] 2.3 Update `_select_reviewer` to thread `temperature` + `max_tokens` from recipe (when present).

## 3. Leaderboard

- [ ] 3.1 Create `src/peer/autoresearch/__init__.py` + `leaderboard.py` with `append_row(path, **fields)` doing atomic write (write to .tmp then os.replace).
- [ ] 3.2 Header row format: `commit_sha\trecipe_hash\tutility\tdetection_rate\tprecision_minor\tprecision_important\tprecision_critical\tcost_usd\tn_comments_total\tstatus\tdescription`. Header written iff file does not exist.

## 4. Utility formula

- [ ] 4.1 `src/peer/autoresearch/utility.py`: `parse_utility_formula(program_md_text) -> Callable[[dict], float]`. Extracts the first python-fenced block under `## Utility`. Safety: only allows `detection_rate`, `precision_*`, `cost_usd`, `n_comments_total`, `dataset_size`, and `max(0, ...)`. Disallow imports / dunders / function calls except `max`/`min`.
- [ ] 4.2 Fallback: when no `## Utility` block, formula = `lambda d: d["detection_rate"]`.

## 5. CLI: `peer autoresearch run`

- [ ] 5.1 Add `autoresearch` parent subparser in `src/peer/cli.py` with `run` and `loop` children.
- [ ] 5.2 `run` handler `_cmd_autoresearch_run` per spec. Loads recipe, runs eval, computes utility, appends TSV row, exits 0/1.

## 6. CLI: `peer autoresearch loop`

- [ ] 6.1 `loop` handler `_cmd_autoresearch_loop`. Implements the iterate-mutate-eval-keep-or-revert loop.
- [ ] 6.2 Default mutator hook: `peer.autoresearch.loop.no_op_mutator` — does nothing; the human/agent edits `recipe.yaml` between iterations.
- [ ] 6.3 `--mutator <dotted-path>` lets users plug in their own.
- [ ] 6.4 Keep decision: `git add recipe.yaml prompts/default_system_prompt.md && git commit -m "autoresearch iter <n>: utility=<v> — <desc>"`.
- [ ] 6.5 Revert decision: `git reset --hard HEAD` (only the recipe+prompt files are staged candidates).

## 7. program.md

- [ ] 7.1 Write `program.md` at repo root with: branch convention, files-under-mutation, eval command, keep rule, default utility formula in a ```python``` block, leaderboard schema, NEVER-STOP semantics.

## 8. Exports

- [ ] 8.1 Export `Recipe`, `append_row`, `parse_utility_formula` from `peer.autoresearch`.
- [ ] 8.2 Export `Recipe` from top-level `peer.__init__`.

## 9. BDD scenarios

- [ ] 9.1 Write `features/autoresearch_recipe.feature` covering all scenarios in the spec.
- [ ] 9.2 Write step defs in `features/steps/autoresearch_recipe_steps.py`. Patch subprocess.run for git commit/reset.

## 10. Quality gates

- [ ] 10.1 ruff / format / mypy / pytest / behave all clean.
