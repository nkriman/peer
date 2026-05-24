# program.md — autoresearch for peer

You are an autonomous research agent improving `peer`'s default reviewer recipe. Your job is to iteratively edit `recipe.yaml` (and the prompt file it points at) to maximize the scalar utility defined below, measured on the hard-subset eval dataset.

> Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch). The shape is the same: fix the eval, fix the file(s) under mutation, loop edit → eval → keep-or-revert until the human interrupts.

## Files under mutation

Only these two files are fair game to edit:

1. **`recipe.yaml`** — full reviewer configuration (model, temperature, max_tokens, prompt path, retries, codebase-context budgets, post-processing). Schema is `peer.recipe.Recipe`.
2. **`prompts/default_system_prompt.md`** — the system prompt content. Everything from instructions about what to flag to instructions about how to format comments lives here.

Optionally, you may add a NEW prompt file under `prompts/` and point `recipe.system_prompt_path` at it. The default file stays put as the v0 reference.

Do NOT edit any other files. Do NOT add dependencies. Do NOT modify `src/peer/`.

## Branch convention

Each run lives on its own branch: `autoresearch/<tag>` where `<tag>` is a short identifier (e.g. `mar5`, `mar5-temp-sweep`). Create with `git checkout -b autoresearch/<tag>` from `main`. Each accepted experiment is a single git commit on this branch.

## Eval command

The fixed evaluation is one invocation of:

```bash
peer autoresearch run --recipe recipe.yaml --dataset dataset/reference/django_pydantic_v2_hard.jsonl --leaderboard data/eval_runs/leaderboard.tsv --description "<short summary of the mutation>"
```

This runs the recipe against 7 PRs (51 gold defects, 21 high-severity), appends one row to the leaderboard TSV, and writes a full EvalReport JSON under `data/eval_runs/`. Expect ~$0.40 per iteration, ~2 minutes wall-clock at concurrency=5.

## Utility

Compute one scalar from the per-iter metrics. The autoresearch loop reads this formula from the python-fenced block below.

```python
score = detection_rate - 0.02 * max(0, n_comments_total - 35)
```

Reading: detection_rate is the primary signal (max possible ≈ 1.0). The `n_comments_total > 35` penalty discourages comment-volume blowup on the 7-PR hard subset (peak observed per-PR volume is ~5; 35 is "everyone got 5"). Cost is NOT in the scalar formula — it's a separate hard guardrail (see Budget).

Mutate this formula by hand when your goals change. Only `detection_rate`, `precision_minor`, `precision_important`, `precision_critical`, `cost_usd`, `cost_usd_total`, `n_comments_total`, `dataset_size`, `suggestion_rate` and the `max`/`min` builtins are allowed (enforced by `peer.autoresearch.utility.parse_utility_formula`).

## Keep / discard rule

After each iteration:

- If `utility_new > utility_best`: **keep**. Run `git add recipe.yaml prompts/ && git commit -m "<one-line description>"`. Update `utility_best = utility_new`.
- If `utility_new <= utility_best`: **discard**. Run `git reset --hard HEAD` to revert the working tree to the last accepted state.
- If the run crashed: status is `crash`, leaderboard row still written for forensics, working tree reverted.

## Budget

Hard guardrails — stop the loop when either is breached:

- **Per-iteration cost**: if any single iteration's `cost_usd` exceeds **$2.00**, treat it as a failure (revert, don't keep) regardless of utility.
- **Total session cost**: stop the loop when cumulative `cost_usd` across all iterations exceeds **$20.00**.

Both are configurable on the `peer autoresearch loop` CLI (`--budget-usd`, `--max-iters`).

## Leaderboard schema

`data/eval_runs/leaderboard.tsv` is tab-separated. Header row is:

```
commit_sha	recipe_hash	utility	detection_rate	precision_minor	precision_important	precision_critical	cost_usd	n_comments_total	status	description
```

One row per iteration. `commit_sha` = current git HEAD short hash AFTER the keep/discard decision. `recipe_hash` = first 8 hex chars of SHA-256 over the canonical YAML. `status` ∈ {`ok`, `discard`, `crash`}.

## Before you mutate: read the hypothesis

After every iteration, `peer autoresearch loop` writes a structured diagnostic to:

```
data/autoresearch/<tag>/iter-<n>-hypothesis.md
data/autoresearch/<tag>/current_hypothesis.md   # always points at the latest
```

Read `current_hypothesis.md` before proposing your next mutation. Your mutation description (the `--description` flag / commit message) MUST cite specific failure modes from that file — e.g. "raise temperature to 0.4 to combat the convergent-comment pattern noted in iter-3 hypothesis under Topic drift" rather than "tune temperature."

## Strategies registry (autoresearch-strategies-v01)

In addition to mutating the prompt + simple config, you may wire a different reviewer strategy by setting `recipe.reviewer_dotted_path` to one of:

- `draft_critique` — wraps any inner reviewer in a draft → critique → revise pipeline
- `two_model_pipeline` — cheap screen pass + expensive detail pass
- `self_filter` — drops low-confidence comments

See `docs/strategies.md` for what each does and what `reviewer_kwargs` they accept. Introducing a NEW strategy (a new `Reviewer`-Protocol-shaped class) is out of scope for the agent loop — it requires touching `src/peer/strategies/`; ask the human if you have a strong reason.

## NEVER STOP

Once the loop has begun, do not pause to ask "should I keep going?" or "is this a good stopping point?". The human may be asleep. Your job is to iterate until manually interrupted or until budget is exceeded. If you run out of ideas: read the latest hypothesis again, re-read this file, scan the leaderboard for patterns ("every recipe with temperature > 0.5 has lost precision — try a recipe with temperature 0.5 AND a more restrictive prompt"), try combining previous near-misses, try a more radical reframe of the prompt entirely.

You are autonomous. Optimize.
