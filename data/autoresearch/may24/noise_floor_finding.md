# The noise-floor finding: most of our prior "results" were variance

## Context

This branch produced a series of confident-sounding findings from autoresearch
on the hard subset (7 PRs, 51 gold defects):

1. "Removing suppressive prompt guardrails doubles DR twice in a row" (autoresearch session 1)
2. "Narrower codebase context beats wider by 25%" (architecture sweep)
3. "Opus is dominated by Sonnet on PR review" (architecture sweep)
4. "Git-blame as context HURTS detection by 60%" (blame experiment)

Then we ran cross-judge variance on the narrower-context recipe AND ran a
pure-`claude --print <diff>` baseline alongside it. Both produced a single
unambiguous result that **invalidates most of the prior confident framing**.

## The new data

Four runs on the **same dataset** (django_pydantic_v2_hard.jsonl, 7 PRs, 51 gold defects):

| Run | Recipe | DR | n_comments |
|---|---|---:|---:|
| 1 | arch[narrower context] (sonnet, 10K ctx, 2 sites) | **0.0980** | 29 |
| 2 | arch[narrower + git_blame] (same + blame section) | **0.0392** | 26 |
| 3 | cross-judge narrower (same recipe as run 1, re-run) | **0.0392** | — |
| 4 | bare baseline (`gh pr diff` → `claude --print`, no peer at all) | **0.0392** | 29 |

Cross-judge variance across sonnet/haiku/opus on the cached run-2 reviews
was **0.0000** — all three judges produced identical detection_rate
estimates. So judge variance is NOT the dominant noise source.

The dominant noise source is reviewer-side: **the same recipe run twice
at temperature=0 produced 2.5× different detection rates** (0.098 vs
0.039). And the bare baseline — a 5-line shell script with no peer
machinery — matched peer's typical output exactly.

## What this means for the prior findings

| Prior claim | Status after this finding |
|---|---|
| "Narrower context beats wider by 25%" | **Likely noise.** Run 1 (DR=0.098) was the outlier, not the typical. Re-running the same recipe got 0.039. |
| "Opus is dominated by Sonnet" | **Possibly noise.** Opus scored 0.039 on its run, sonnet scored 0.078. Both are within the run-to-run variance we just measured. |
| "Git-blame hurts detection" | **Unfalsifiable.** The "blame" run scored 0.039, matching the cross-judge re-run of *no blame*. There's no signal here — both are at the noise floor. |
| "Removing prompt restrictions doubles DR" | **Unknown.** Those measurements were each N=1 on the same recipe. Could be real (prompt-content variance might be smaller than recipe-run variance), but we haven't measured it rigorously. |

## The existential test

If peer's "best" recipe is no better than `claude --print <diff>`, what is
the framework actually for?

The honest read:
- **Peer's OOB detection_rate is NOT better than pure `claude` CLI on this dataset.**
  Both score ~0.04 = 2 matches out of 51 gold defects.
- The 0.098 number we'd been celebrating was a single lucky run, not a
  reproducible win.
- The framework's machinery (context construction, prompt tuning, strategies)
  doesn't visibly justify itself on the headline metric.

## Where peer's value actually lives (honest reframing)

Three claims that survive this finding:

1. **Reproducibility/auditability**: peer produces structured EvalReport JSON
   per run, leaderboard rows with recipe hash, hypothesis markdown — not
   just an LLM response. Pure `claude` produces nothing systematic.

2. **The autoresearch loop itself**: even if the OOB recipe is no better than
   bare claude, peer is a *framework for systematically improving reviewers
   per repo*. Users with their own gold datasets can autoresearch their way
   to a recipe that beats bare claude *on their corpus*. The framework's job
   is the loop, not the default.

3. **Honest measurement**: cross-judge + reviewer-noise findings are
   themselves the kind of insight peer-as-framework produces. Pure `claude`
   would never have surfaced them. The framework is a microscope, not (just)
   a reviewer.

## What we have to publish honestly

If we ever publish benchmarks, the table needs to include:

| Variant | DR (single run) | DR (median of 5 reruns) | Δ vs bare baseline |
|---|---|---|---|
| bare claude code | 0.039 | TBD | (zero) |
| peer narrower context | 0.098 (run 1) / 0.039 (run 2) | TBD | TBD |
| peer + curated prompt | TBD | TBD | TBD |

Until "DR (median of 5 reruns)" is filled in for both, **we cannot
honestly claim peer beats the baseline**.

## What this implies for the next moves

1. **Multi-run averaging is now table-stakes** before any "peer beats X"
   claim. Every leaderboard entry should be N≥3 runs with median + range.
2. **CrossJudgeRunner should be extended to CrossRunRunner** — re-run the
   reviewer N times against the same dataset, report median + variance.
3. **The autoresearch loop's keep/discard rule needs to gate on multi-run
   delta**, not single-run delta. Otherwise we hill-climb on noise (which
   is exactly what we did for the past 4 hours).
4. **The "narrower context wins" recipe calibration should NOT be shipped
   as a default change** until it's confirmed across N≥5 reruns. The
   recommendation from the architecture sweep was premature.
5. **Reframe peer's pitch**: not "peer catches more bugs than `claude --print`"
   (which we can't currently demonstrate), but "peer is the framework that
   lets you measure whether it catches more bugs, and iterate until it does
   on YOUR corpus." That's defensible and unique.

## The blog-post-worthy meta-finding

> "I built an autoresearch loop for AI code review. After 12 iterations
> with confident-sounding 'wins,' I added a cross-judge variance utility
> + a pure-`claude --print <diff>` baseline. Both immediately revealed
> that the run-to-run reviewer noise on this 7-PR / 51-defect benchmark
> is 2-3× — bigger than every claimed win. The baseline matched my
> 'best' recipe. The autoresearch had been hill-climbing on variance for
> 12 iterations. The fix isn't more hill-climbing — it's multi-run
> averaging as a precondition for any keep/discard decision."

That's the post. The discovery that you've been climbing on noise is more
interesting than any of the individual climbs.
