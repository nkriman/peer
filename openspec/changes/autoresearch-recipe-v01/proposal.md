## Why

We just demonstrated (triage on 7-PR hard subset, deterministic to the digit) that the v0.2 prompt addition cost us 3× detection_rate. The fix is one of: revert, reword, or *search the joint space of prompt + context + post-processing knobs to find a better recipe than the human-written baseline*. The third is the most leveraged.

Karpathy's [autoresearch](https://github.com/karpathy/autoresearch) shows the shape: fix the eval, fix the one file under mutation (`train.py`), let an agent iterate overnight on a TSV. Peer's analog is bigger: ~20 dimensions including model, prompt, context budgets, retries, post-processing, multi-pass orchestration. This change defines a `Recipe` that captures the full surface, externalizes the prompt to a file, and ships the loop that lets a Claude Code session autonomously hill-climb.

This is the v0 autoresearch shape — config-only mutation. Code-level mutation (introducing new `Strategy` implementations) ships separately in `autoresearch-strategies-v01`. Diagnostic introspection (eval-as-mutator) ships in `autoresearch-eval-as-mutator-v01`.

## What Changes

- New `peer.recipe.Recipe` Pydantic model — single source-of-truth for a reviewer configuration. Fields cover: model, temperature, max_tokens, system_prompt path, tool-schema overrides, codebase-context budgets (tokens / call-sites / test-file-chars), retries, post-processing (max_comments_per_pr, severity_floor, drop_paths globs), per-strategy reviewer wiring (defaulting to `ClaudeReviewer`). All fields have defaults that match today's behavior — a default `Recipe()` reproduces current peer.
- New `prompts/default_system_prompt.md` — extract `DEFAULT_SYSTEM_PROMPT` to a file. `peer.prompts` loads it. The agent mutates this file (or points the recipe at a different one) between experiments.
- New `peer.recipe.load_recipe(path)` + `recipe.apply_to_agent(agent)` — construct an `Agent` configured by a recipe.
- New `program.md` at repo root — meta-instructions for the experimenting agent: branch convention (`autoresearch/<tag>`), what to mutate (`recipe.yaml` + the linked prompt file), eval command, keep/discard rule, leaderboard schema, "never stop" loop semantics.
- New `data/eval_runs/leaderboard.tsv` schema — `commit_sha\trecipe_hash\tdetection_rate\tprecision_minor\tprecision_important\tprecision_critical\tcost_usd\tn_comments_total\tstatus\tdescription`.
- New `peer autoresearch` CLI parent subcommand with two children:
  - `peer autoresearch run --recipe <path> [--dataset <path>]` — single iteration: load recipe → construct Agent → run eval against hard subset → append a TSV row → print result. Composable into shell loops.
  - `peer autoresearch loop --recipe <path> [--max-iters N] [--budget-usd X]` — autonomous mode. Reads `program.md` for the keep rule + scalar utility formula. Each iteration: invoke a configurable mutator hook (default: no-op, expects the user-driven agent to mutate the file between iterations), run eval, score utility, keep (commit) or revert (`git reset --hard`).
- Scalar utility formula in `program.md` — single number derived from per-iter metrics. Default: `score = detection_rate × (precision_minor + precision_important + precision_critical) / 3 - 0.05 × max(0, n_comments_total / dataset_size - 5)`. Cost not in default formula (kept as a separate budget guardrail). Human edits the formula by hand.
- Temperature=0 by default — eliminate the stochastic-noise floor that would otherwise drown out small recipe deltas. (Today's `ClaudeReviewer` doesn't pass `temperature`; the SDK defaults to 1.)

## Capabilities

### New Capabilities

- `autoresearch-recipe`: the `Recipe` model, recipe loader, recipe→Agent application, `peer autoresearch run/loop` CLI, `program.md` + `prompts/default_system_prompt.md` + `leaderboard.tsv` artifacts.

### Modified Capabilities

- `pr-review-agent`: `Agent.__init__` accepts an optional `recipe: Recipe | None` parameter; when set, the recipe's `system_prompt`/`model`/`retries`/etc. are applied (recipe wins over explicit kwargs). `ClaudeReviewer.review` passes `temperature` from the recipe (default 0.0).

## Impact

- **Code**: new `src/peer/recipe.py`, `src/peer/autoresearch/__init__.py` + `runner.py` + `loop.py` + `leaderboard.py`, new `prompts/default_system_prompt.md`, new `program.md` at repo root, modifications to `src/peer/prompts.py` (load from file), `src/peer/reviewers.py` (pass temperature), `src/peer/agent.py` (accept recipe), `src/peer/cli.py` (new `autoresearch` subcommand).
- **Schema**: `Recipe` JSON/YAML round-trip via Pydantic; `leaderboard.tsv` is a flat tab-separated log appended atomically.
- **Dependencies**: `pyyaml` for `recipe.yaml`. No other new deps.
- **Tests**: BDD coverage in `features/autoresearch_recipe.feature`. Existing tests stay green via defaults.
- **Out of scope**: code-mutation strategies (separate change); diagnostic introspection (separate change); population-based search; auto-distillation; Pareto frontier visualization (manual analysis of TSV is enough for v0).
- **Back-compat**: a freshly-constructed `Agent()` with no `recipe=` argument behaves identically to today.
