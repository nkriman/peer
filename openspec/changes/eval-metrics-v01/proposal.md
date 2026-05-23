## Why

The eval framework's headline metric is `defect_recall` computed as mean of per-PR recall rates. This is **misleading** when gold counts vary across PRs (range in v2 dataset: 1 to 23 defects per PR):

- v2 baseline run: 3 matches / 63 gold = 4.8% sum-of-sums recall, but mean-of-rates = 5.8%
- v2 + conventions: 5 matches / 63 gold = 7.9% sum-of-sums (a +66% relative win), but mean-of-rates = 2.6% (looks like a regression)

This is Simpson's paradox: gains on big-denominator PRs are diluted to ~0 in per-PR rates; losses on small-denominator PRs (2/2 → 0/2 = -100% on one PR) dominate the mean.

The competitive landscape (`docs/competitive_landscape_research.md`) confirms the industry uses sum-of-sums recall + comments-per-PR + per-tier precision, not mean-of-rates. Macroscope, CodeRabbit, Greptile, Cursor BugBot, Sentry Seer all calibrate severity tiers to precision so a `critical` label means "ship the fix immediately." Our v0.1 default conventions doc accidentally caused peer to flip from over-severing (+0.75) to under-severing (-0.33) — clear evidence the prompt-level severity guidance is fragile.

This change makes peer's metrics industry-comparable and removes the over-correcting severity instruction.

## What Changes

- Add `DetectionRate` metric: sum-of-sums recall (matches / total_gold across all samples). Becomes the default headline metric.
- Add `CommentsPerPR` metric: mean number of peer comments per sample. Default; standard noise indicator.
- Add `PrecisionPerSeverity` metric: of matched peer comments, what fraction at each severity (critical / important / minor / nit) actually correspond to gold defects. Validates whether the severity rubric is meaningful.
- Keep existing `DefectRecall` (mean-of-rates) but rename to `MeanPerPRRecall` and demote to secondary, with an explicit docstring warning that it Simpson's-paradoxes when gold counts vary.
- Soften the `Agent(team_conventions=)` system-prompt wrapper: remove the "treat as nit or minor severity for pure style" instruction that caused the calibration flip. Let the agent infer severity from the conventions doc itself.
- Update the CLI summary renderer to lead with the new metrics + flag the caveat on mean-of-rates.

## Capabilities

### Modified Capabilities

- `eval-runner`: default metric set changes from `[DefectRecall, NoveltyRate, SeverityCalibration]` to `[DetectionRate, MeanPerPRRecall, NoveltyRate, SeverityCalibration, PrecisionPerSeverity, CommentsPerPR]`. The Protocol surface (`EvalMetric`) is unchanged.

### New Capabilities

None — this is a refinement to existing metrics + a prompt tweak.

## Impact

- **Code**: `src/peer/eval/metrics.py` (add 3 new metric classes), `src/peer/eval/runner.py` (update default metric list), `src/peer/eval/report.py` (update render_summary headline), `src/peer/agent.py` (soften conventions wrapper), `tests/test_metrics.py` (add tests for new metrics).
- **Reports**: existing `EvalReport.json` files remain readable (schema unchanged); new runs include the new metrics. Old runs missing new metrics are flagged with `null` values in A/B diffs rather than crashing.
- **CLI**: `peer eval` summary output reorders to lead with `DetectionRate` and `CommentsPerPR`; relegates `MeanPerPRRecall` to a "(per-PR avg — caveat: Simpson's paradox)" suffix line.
- **Existing eval runs in `data/eval_runs/` are NOT re-run automatically** — users can re-run with new metrics by re-invoking `peer eval`. We'll re-run the v2 reference run as part of this change to produce the new headline numbers.
- **Out of scope**: changing the eval Protocol shape; renaming files; changing dataset schema; adding live commercial-baseline comparison (deferred to `benchmark-v01`).
