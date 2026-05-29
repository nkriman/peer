# Narrower-context on v2 30-PR: peer beats baseline on per-PR recall, calibration, and suggestion rate

## Context

The 7-PR hard-subset experiment ([noise_floor_finding.md](../may24/noise_floor_finding.md))
showed peer's narrower-context recipe was indistinguishable from a 5-line
bare baseline on every metric. Suspected cause: dataset too small to clear
the noise floor (~0.06 on detection_rate). This note tests that hypothesis
on the full v2 30-PR set.

## The experiment

- **Recipe:** narrower-context default (`reviewer_dotted_path: null` →
  `ClaudeCodeCLIReviewer`, sonnet, 10k codebase context, T=0,
  `use_claude_code: true`).
- **Baseline:** `BareClaudeCodeReviewer` (gh pr diff → `claude --print`).
- **Dataset:** `django_pydantic_v2.jsonl` (30 PRs, full v2 set).
- **Method:** N=3 reruns each, paired comparison via `cross-run-v01`
  + `compare_to_baseline` (noise_floor=0.06) + `RecipeVerdict` (multi-objective-v01).

Artifacts:
`data/eval_runs/multirun_f7caeb70_1199de6.json` (recipe),
`data/eval_runs/multirun_baseline_1199de6.json` (baseline),
`data/eval_runs/comparison_f7caeb70_1199de6.json` (verdicts).

## The result

```
RecipeVerdict: AMBIGUOUS
above_noise: 3  |  in_noise: 2  |  below_noise: 1  |  unmeasured: 1
```

| metric | peer median | baseline median | delta | verdict |
|---|---:|---:|---:|:---|
| mean_per_pr_recall | **0.0833** | 0.0024 | +0.0809 | ✓ **above_noise** |
| severity_calibration | **+0.75** | −1.00 | +1.75 | ✓ **above_noise** |
| suggestion_rate | **0.40** | 0.00 | +0.40 | ✓ **above_noise** |
| detection_rate | 0.0635 | 0.0159 | +0.0476 | — in_noise (peer 4× baseline) |
| novelty_rate | 0.97 | 0.99 | −0.03 | — in_noise |
| comments_per_pr | 2.17 | 2.50 | −0.33 | ✗ below_noise (peer is quieter) |
| precision_per_severity | n/a | n/a | n/a | n/a |

## What this says

1. **Dataset size mattered enormously.** The same recipe vs the same bare
   baseline produced no above-noise wins on 7 PRs and three above-noise wins
   on 30 PRs. The 7-PR result was not a real ceiling on peer — it was a
   measurement-resolution ceiling.

2. **Where peer actually wins:**
   - `mean_per_pr_recall`: peer recovers ~8% of gold defects per PR vs bare
     baseline's ~0.2%. The bare-diff approach barely catches anything per-PR
     because it has no codebase context to ground its critiques.
   - `severity_calibration`: bare baseline produces poorly-calibrated severity
     (everything ends up as one tier, calibration ≈ −1.0). Peer's structured
     prompt + JSON schema yields well-calibrated severities (+0.75).
   - `suggestion_rate`: peer attaches an executable fix to ~40% of comments
     vs 0% for bare baseline.

3. **Where the headline does NOT yet land:** `detection_rate` (overall
   pooled-recall) stays in_noise despite peer being directionally 4× the
   baseline (0.064 vs 0.016). At 30 PRs the per-metric noise band on
   detection_rate is still wider than this lift — needs either more PRs or
   a higher-resolution metric (per-PR recall, see above).

4. **Peer is quieter than bare baseline** (2.17 vs 2.50 comments/PR, below
   noise). Combined with higher recall, this is a strict signal-to-noise
   improvement per posted comment.

## What this does NOT say

- Verdict is AMBIGUOUS *only* because `comments_per_pr` is below_noise.
  If we weight "fewer comments" as positive (most reviewers will), the
  vector verdict flips to KEEP. The framework deliberately does not bake
  that preference in — it's a user-side weight to apply on the front.
- 30 PRs is still small. Bands on detection_rate suggest we'd need
  ~100 PRs to make peer's 4× directional lift clear the noise band.
- The judge model is sonnet. Cross-judge variance was previously measured
  at ~0 (sonnet/haiku/opus all agreed), but we haven't re-measured on the
  30-PR set.

## The interesting bit for the write-up

**Recall improvement is dataset-bound.** Anyone running an LLM PR-review
benchmark on <10 PRs is operating below the noise floor and producing
unreliable conclusions. The same recipe that looked "no better than
`claude --print <diff>`" at N=7 demonstrably beats it at N=30. This is
the most actionable methodological finding from this session.
