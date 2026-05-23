## Context

Per the diagnosis in `data/eval_runs/diagnosis_reference_v1.md` and the conventions experiment in commit `eval-v01: team conventions injection — real +3pp recall lift hidden by metric`, our default headline metric (`DefectRecall` mean-of-rates) misrepresents the framework's actual behavior. Adopting industry-standard metrics fixes the misreport, makes peer's numbers comparable to Macroscope / CodeRabbit / Greptile benchmarks, and removes a small but real piece of prompt over-engineering that's harming severity calibration.

## Goals / Non-Goals

**Goals:**
- Reporting reflects industry-standard "detection rate + precision + noise" trio.
- Per-tier precision metric quantifies whether severity labels are meaningful (e.g., "critical" should be ~100% precise).
- Defaults work out of the box; users see a sensible eval summary on first run.
- Old reports still load via `EvalReport.from_json`.
- Agent prompting no longer issues a global severity instruction that the model over-applies.

**Non-Goals:**
- Changing the `EvalMetric` Protocol surface.
- Re-curating the dataset.
- Adding new gold sources / enrichments.
- Live commercial-baseline runs (deferred to `benchmark-v01`).

## Decisions

### 1. `DetectionRate` is the new headline recall metric

`DetectionRate` is sum-of-sums: total matched gold defects across all samples divided by total gold defects across all samples. Single number, not a per-sample mean. Reported as a percentage in CLI rendering.

**Why:** when sample-level denominators vary (1 to 23 in our v2 dataset), mean-of-rates obscures aggregate performance. Sum-of-sums is what Macroscope's benchmark uses ("48% detection") and what most published comparisons report.

**Trade-off:** sum-of-sums weights PRs proportional to their gold count, so a 23-defect PR dominates a 1-defect PR by 23x. For framework users who want to weight all PRs equally, the demoted `MeanPerPRRecall` is still available. The right metric depends on the question being asked.

### 2. `MeanPerPRRecall` stays but is demoted with explicit caveat

Rename the old `DefectRecall` to `MeanPerPRRecall`. Keep it in the default metric set so users can see both numbers + their disagreement. Docstring + CLI rendering call out the Simpson's-paradox risk explicitly.

**Why:** there are legitimate uses (e.g., "average reviewer-PR experience"). Removing it would be a regression for users who already track it. But the framework should not lead with it.

### 3. `CommentsPerPR` is a first-class metric, not a derived stat

Mean and median peer comments per sample. The industry's primary noise indicator (Macroscope reports it as `Comments/PR` in their leaderboard; Graphite's 0.62 / CodeRabbit's 10.84 / etc. are how teams choose).

**Why:** the recall/precision number alone doesn't tell you adoption viability. A 95%-precision agent that posts 30 comments per PR will be muted by teams. Surfacing it as a metric — not a footnote — encourages users to optimize for the trade-off they actually face.

### 4. `PrecisionPerSeverity` measures severity calibration honestly

For each severity tier (`critical / important / minor / nit`), compute: `(peer comments at that severity that matched gold) / (peer comments at that severity, total)`. Returns a dict keyed by severity with `precision` + `n` per tier. Aggregates skip tiers where `n == 0` to avoid divide-by-zero noise.

**Why:** this is the Sentry Seer pattern ("when Seer says critical, ship the fix"). A reviewer whose `critical` is 100% precise is genuinely usable for blocking-merge automation. A reviewer whose `critical` is 50% precise is not. Without a per-tier number, severity is decorative.

**Aggregation across samples:** sum matches at each severity across all PRs, divide by total comments at that severity across all PRs. Same sum-of-sums logic as `DetectionRate`.

### 5. Soften the conventions-wrapper severity instruction

The current `Agent(team_conventions=...)` wrapper appends this to the system prompt:

> "Treat departures from these conventions as defects (at appropriate severity — usually nit or minor for pure style)."

The conventions experiment showed this caused the model's severity to flip from +0.75 over-severing to -0.33 under-severing — a one-sentence change with a large quantified effect. The instruction is overly directive; the conventions doc itself already indicates severity contextually (a style nit reads as a style nit; a security concern reads as a security concern).

Replacement: simply state "treat departures from these conventions as defects you should flag" without prescribing severity. The agent will choose severity from the convention's framing + the rest of the system prompt.

### 6. CLI rendering reorders headline metrics

`render_summary(report)` currently lists metrics in the order they were registered. Update to use a fixed industry-aligned order at the top:

```
Headline:
  detection_rate              0.079  (sum-of-sums: 5 / 63)
  comments_per_pr             1.97   (median: 2.0)
  precision_per_severity      critical: 100% (1/1)  important: 25% (1/4)  minor: 18% (3/17)  nit: 0% (0/6)
Secondary:
  mean_per_pr_recall          0.026  (Simpson's-paradox risk — see docs/competitive_landscape_research.md)
  novelty_rate                0.960  (warning light; not a false-positive rate)
  severity_calibration       -0.333  (mean signed delta; n=3)
```

### 7. Schema-compatible additions

`EvalReport.report_schema_version` stays at `1.0`. The new metrics' `MetricResult` records simply append into `metrics_values` / `metrics_details`. Old reports loaded via `from_json` won't have the new metrics — that's expected; `render_diff` shows `null → 0.079` for missing baseline metrics rather than crashing.

## Risks / Trade-offs

- **[Risk]** Users tracking `MeanPerPRRecall` over time see a metric "renamed" — could read as a regression. **Mitigation:** keep both `DefectRecall` (deprecated alias) and `MeanPerPRRecall` (canonical) names for one minor version; add release notes.
- **[Risk]** `DetectionRate` of 7.9% on the v2 dataset looks bad in absolute terms. **Mitigation:** include the published Macroscope numbers (Greptile 24%, CodeRabbit 46%, Macroscope 48%) in the conventions writeup so users have context. peer's reference dataset is harder than Macroscope's runtime-bug dataset (more style-nit / Django-specific items that any tool would struggle with).
- **[Risk]** `PrecisionPerSeverity` has tiny denominators on small datasets (often 0–2 per tier). **Mitigation:** report `n` alongside `precision`; CLI suppresses tiers with `n==0`.
- **[Risk]** Softening the conventions wrapper instruction may regress recall on the wins-with-conventions PRs. **Mitigation:** re-run the conventions experiment as part of this change's validation; if recall regresses materially, revisit the instruction wording.

## Open Questions

None blocking. The next-step question (whether `DetectionRate` should also have a per-severity variant, e.g. `detection-among-criticals` for "do we catch the high-stakes bugs") is reserved for a follow-on change once we see the per-tier precision numbers.
