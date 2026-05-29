# Agentic reviewer vs bare baseline: the tool loop doesn't move detection_rate

## Context

[noise_floor_finding.md](./noise_floor_finding.md) showed that on the hard
subset, peer's narrower-context recipe doesn't beat a 5-line bare baseline on
`detection_rate`. The hypothesis we wanted to test next:

> Maybe peer's deterministic context-builder is what's limiting it. If we let
> Claude itself decide what to read (Read/Grep/Glob tools with up to 15 turns
> per PR), surely *that* will catch defects the bare-diff baseline misses.

This note is the empirical answer.

## The experiment

- **Recipe:** `AgenticReviewer` (new, see `openspec/changes/agentic-reviewer-v01/`)
  with `allowed_tools=[Read, Grep, Glob]`, `max_turns=15`, sonnet, temperature=0,
  `use_claude_code=true`. Same dataset (`django_pydantic_v2_hard.jsonl`, 7 PRs, 51 defects).
- **Baseline:** `BareClaudeCodeReviewer` — `gh pr diff <PR>` piped into
  `claude --print "review this"`. No peer machinery.
- **Method:** N=5 reruns of each, paired comparison via `cross-run-v01`
  + `compare_to_baseline` (noise_floor=0.06).

Artifacts: `data/eval_runs/multirun_d269ac1d_1199de6.json` (agentic),
`data/eval_runs/multirun_baseline_1199de6.json` (bare),
`data/eval_runs/comparison_d269ac1d_1199de6.json` (verdicts).

## The result

```
RecipeVerdict: AMBIGUOUS
above_noise: 1  |  in_noise: 3  |  below_noise: 2  |  unmeasured: 1
```

| metric | agentic median | bare baseline median | delta | verdict |
|---|---:|---:|---:|:---|
| detection_rate | 0.0392 | 0.0588 | -0.0196 | — in_noise |
| mean_per_pr_recall | 0.0192 | 0.0478 | -0.0286 | — in_noise |
| novelty_rate | 0.9357 | 0.9071 | +0.0286 | — in_noise |
| comments_per_pr | 2.7143 | 4.5714 | -1.8571 | ✗ below_noise |
| severity_calibration | 0.0000 | 0.2500 | -0.2500 | ✗ below_noise |
| suggestion_rate | 0.5861 | 0.0000 | +0.5861 | ✓ above_noise |
| precision_per_severity | n/a | n/a | n/a | n/a |

## What this says

1. **The tool loop does not catch more bugs.** `detection_rate` and
   `mean_per_pr_recall` are both within noise of the 5-line baseline.
   On `detection_rate` specifically the agentic median is *lower* than
   bare baseline (0.039 vs 0.059), inside noise but not directionally
   encouraging.

2. **The tool loop changes the *character* of the review.** Agentic
   posts notably fewer comments per PR (2.7 vs 4.6) and attaches a
   suggestion to ~59% of them (vs 0% for bare). Severity calibration
   gets worse because the agentic reviewer floors everything at one
   severity instead of distributing across minor/important/critical.

3. **The latency cost is significant.** Per-run wall time was ~25
   min for agentic (sonnet via CLI subscription, max 15 turns) vs
   ~9 min for bare baseline on the same 7-PR subset. ~2.8× slower for
   zero detection-rate lift.

4. **Pareto-front comparison vs narrower-context.** `peer autoresearch
   frontier` reports both AMBIGUOUS recipes as non-dominated:

   | axis | agentic | narrower-context | winner |
   |---|---:|---:|---|
   | detection_rate | 0.0392 | 0.0392 | tie |
   | comments_per_pr | 2.71 | 3.14 | agentic (quieter) |
   | mean_per_pr_recall | 0.019 | 0.091 | narrower |
   | novelty_rate | 0.94 | 0.90 | agentic |
   | severity_calibration | 0.00 | 0.00 | tie |
   | suggestion_rate | 0.59 | 0.45 | agentic |

   Agentic trades per-PR recall for selectivity + suggestion density.

## Important caveat (added after the v2-30 run)

After this 7-PR experiment, the narrower-context recipe was rerun on the
**full 30-PR v2 set** (see [../may25/narrower_v2_30pr.md](../may25/narrower_v2_30pr.md))
and produced **three above-noise wins vs bare baseline** (per-PR recall,
severity calibration, suggestion rate) — wins that were invisible on the
7-PR subset. That means *most* of the "in_noise" verdicts above for the
agentic-vs-baseline comparison are also likely measurement-resolution
ceilings, not real ties. A like-for-like agentic-vs-baseline run on the
v2-30 set is the next experiment to settle the question.

## What this does NOT say

- This was a single 7-PR dataset (gold defects skew to django/pydantic
  static-analysis bugs). A larger and more diverse dataset could
  change the picture. **Confirmed above:** on the 30-PR set, narrower
  context shows lifts that this 7-PR study did not detect. The same
  caveat almost certainly applies to agentic.
- This was N=5. Reviewer-side variance is ~0.06 (see noise floor finding),
  so the in-noise verdicts on detection_rate and recall don't *rule out*
  small improvements smaller than the band — they just say we can't see
  them at N=5 on 7 PRs.
- We didn't sweep `max_turns` or `allowed_tools`. It's possible
  (Bash, Edit, larger turn budget) would change agentic's behaviour. But
  the strongly-budgeted default (which is what most users would adopt
  OOB) does not beat the 5-line baseline.

## The interesting bit for the write-up

The intuition "give the model file-system tools and it will get better
at code review" has been a vibes-driven default in the AI-eng community.
Empirically, on this dataset, it doesn't move detection_rate — it just
reshapes the review's verbosity profile. That's worth saying out loud,
with the artifacts attached, even though it's a smaller dataset than
one would want for a definitive claim.
