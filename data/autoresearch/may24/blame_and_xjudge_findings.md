# Findings: blame enricher + cross-judge variance

Both experiments run via the `claude` CLI on the hard subset
(`dataset/reference/django_pydantic_v2_hard.jsonl`, 7 PRs / 51 gold defects).
Zero API spend — all calls subscription-routed.

## Phase 1: does git-blame as context lift detection?

Comparison against the prior narrower-context frontier point (DR=0.0980).

| variant | DR | n_comments | cost |
|---|---:|---:|---:|
| narrower context (no blame, prior) | 0.0980 | 29 | $0.83 |
| narrower context + git_blame | 0.0392 | 26 | $0.7148 |

**Blame HURTS detection by -0.0588.** Don't enable by default; revisit the rendering or scope of the section.

## Phase 2: how noisy is the cross-judge measurement?

- DR min: 0.0392
- DR median: 0.0392
- DR max: 0.0392
- DR range: 0.0000
- n judges: 3

Judge variance is below the 2× threshold. Point estimates are reasonable but should still cite the judge model.

## Implications

1. The blame delta (-0.0588) must be interpreted against the cross-judge variance band (range 0.0000 if non-None). If the blame delta is smaller than the variance range, it's noise.

2. Whatever the next defaults are, they should be expressed with cross-judge bands, not point estimates. The `peer eval --cross-judge` workflow is now first-class.