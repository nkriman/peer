## 1. New metrics

- [ ] 1.1 Implement `DetectionRate` in `src/peer/eval/metrics.py` — sum-of-sums recall across samples, `MetricResult.value = matches / total_gold`; aggregate via sum-of-sums (not mean-of-rates).
- [ ] 1.2 Implement `CommentsPerPR` in `src/peer/eval/metrics.py` — record `n_comments` per sample, report mean + median + min + max in aggregate.
- [ ] 1.3 Implement `PrecisionPerSeverity` in `src/peer/eval/metrics.py` — per-tier precision with `{precision, n}` shape per severity; aggregate as sum-of-sums per tier; skip tiers where `n==0`.

## 2. Rename + deprecation

- [ ] 2.1 Rename existing `DefectRecall` class to `MeanPerPRRecall` in `src/peer/eval/metrics.py`. Update `name` attribute to `mean_per_pr_recall`. Update docstring with explicit Simpson's-paradox warning + a reference to `DetectionRate`.
- [ ] 2.2 Add `DefectRecall = MeanPerPRRecall` back-compat alias that emits a `DeprecationWarning` on instantiation.
- [ ] 2.3 Update `src/peer/eval/__init__.py` to export both `DetectionRate`, `CommentsPerPR`, `PrecisionPerSeverity`, `MeanPerPRRecall` (kept) and `DefectRecall` (back-compat).

## 3. Default metric set

- [ ] 3.1 Update `EvalRunner.__init__` default `metrics=` from `[DefectRecall(), NoveltyRate(), SeverityCalibration()]` to `[DetectionRate(), CommentsPerPR(), PrecisionPerSeverity(), MeanPerPRRecall(), NoveltyRate(), SeverityCalibration()]`.

## 4. Report rendering

- [ ] 4.1 Update `render_summary` in `src/peer/eval/report.py` — group output into "Headline:" (detection_rate, comments_per_pr, precision_per_severity) and "Secondary:" (mean_per_pr_recall + caveat, novelty_rate, severity_calibration). Use plain text formatting; no external libs.
- [ ] 4.2 Update `render_diff` to handle metrics present in B but missing in A — render `(not in baseline) → <value>` instead of raising.

## 5. Conventions wrapper softening

- [ ] 5.1 Update `src/peer/agent.py` `Agent.__init__` wrapping of `team_conventions` — remove "treat as nit or minor severity" prescription; keep section header and direction to flag departures; let agent infer severity from context.

## 6. Tests

- [ ] 6.1 Add `tests/test_metrics_v2.py` covering DetectionRate (single-sample, multi-sample aggregate, zero-gold edge), CommentsPerPR (mean/median/min/max), PrecisionPerSeverity (single-sample per-tier, multi-sample aggregate, n==0 tier suppression).
- [ ] 6.2 Add test to `tests/test_report.py` for render_summary: assert "Headline:" section appears before "Secondary:" section and that `mean_per_pr_recall` line contains the caveat string.
- [ ] 6.3 Add test to `tests/test_report.py` for render_diff with old-baseline + new-current; assert no crash and `(not in baseline)` markers present.
- [ ] 6.4 Add test to existing test_runner: instantiating EvalRunner with no `metrics=` gives the new 6-metric default.
- [ ] 6.5 Add test to existing test_curator or test_agent: instantiating `Agent(team_conventions="...")` produces a system_prompt that does NOT contain "nit or minor" — verifies softening.
- [ ] 6.6 Verify deprecation: instantiating `DefectRecall()` emits `DeprecationWarning` (use `pytest.warns`).

## 7. Re-run + writeup

- [ ] 7.1 Re-run `peer eval --dataset dataset/reference/django_pydantic_v2.jsonl --out data/eval_runs/reference_v2_sonnet46_metrics_v2.json` with default agent (no conventions) — captures the new headline numbers for the v2 dataset.
- [ ] 7.2 Re-run conventions experiment (`scripts/eval_with_conventions.py`) against the v2 dataset with the softened wrapper, save to `data/eval_runs/reference_v2_sonnet46_with_conventions_metrics_v2.json`.
- [ ] 7.3 Write `data/eval_runs/metrics_v2_comparison.md` showing v2-baseline-with-old-metrics vs v2-baseline-with-new-metrics vs v2-conventions-with-new-metrics. Demonstrates the Simpson's-paradox correction and the softening fix.
