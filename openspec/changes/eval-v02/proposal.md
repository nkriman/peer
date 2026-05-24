## Why

Pydantic Evals (`docs/pydantic_evals_design_philosophy.md`) shipped the same Case→Dataset→Evaluator→Report decomposition peer's `eval-v01` did, but with several design calls that are clearly better:

1. **Evaluator return types are flexible** (`bool | int | float | str | dict`) — peer's hard-coded `Optional[float]` + `per_sample_detail` is awkward.
2. **Case-specific evaluators** — different PRs deserve different rubrics (PR 16603 with 23 architectural concerns vs PR 7900 with 2 docstring nits).
3. **Async-first with concurrency control** — peer's sequential 7-minute eval could be a 90-second async run.
4. **Configurable `LLMJudge`** with `include_input` / `include_expected_output` / `include_reason` flags — peer's hardcoded `judge_match` can't be tuned without code edits.
5. **`pass_rate` as a top-level summary** — simple, recognizable.
6. **Layered eval**: fast deterministic checks → slow LLM judges (cost saver via early skip).

But the deepest insight is from their LLM-as-judge guide:

> "If you could write a single evaluator rubric that perfectly captured your requirements across all cases, you'd just incorporate that rubric into your agent's instructions."

This reframes peer's eval entirely. Three categories of measurement: (1) things the agent can self-check (encode in prompt), (2) things the agent can't self-check (needs ground truth — current eval's territory), and (3) meta-judgment (is the rationale grounded? is the comment substantive?). **peer is missing category 3 entirely.** Adding it via a new `RationaleGrounding` LLMJudge would have caught the hallucinated-line-number issue in PR 7677 directly.

This change refactors peer's eval framework to adopt the patterns + adds the missing meta-judgment metric, without depending on `pydantic-evals` itself.

## What Changes

### Evaluator API: flexible return types

- `MetricResult.value` becomes `Union[bool, int, float, str, dict, None]`.
- Dict-returning evaluators (like `PrecisionPerSeverity`) carry multiple metrics natively; remove the awkward `per_sample_detail` split.
- Update default-metric implementations to use the native return type.
- Aggregation logic in `_aggregate_metrics` becomes metric-type-aware via `Evaluator.aggregate` classmethod (sum-of-sums for floats, mean for floats, per-tier for dicts, pass-rate for bools).

### Case-specific evaluators

- `GoldSample` gains `evaluators: list[EvalMetric] = Field(default_factory=list)`.
- `EvalRunner` runs dataset-wide metrics + per-sample metrics per case.
- Custom case-specific evaluators (e.g., per-PR LLMJudge with a tailored rubric) shipped as user-facing pattern.

### Configurable LLMJudge

- New `peer.eval.LLMJudge` Evaluator class: configurable `rubric`, `model`, `include_input`, `include_expected_output`, `include_reason`. `include_reason=True` always default — surfaces the judge's explanation in `per_sample_detail`.
- Existing `judge_match` becomes a thin wrapper around `LLMJudge(rubric="determine if two comments flag the same issue", ...)`.

### Async-first runner

- `EvalRunner.run_async(concurrency: int = 5)` is the new canonical entry; `run()` is the sync wrapper.
- Per-sample reviewer + judge calls run in parallel via `asyncio.gather` with a semaphore.
- Configurable `concurrency` keyword on `EvalRunner.__init__` (default 5).

### pass_rate aggregate

- `EvalSummary.pass_rate: Optional[float]` reports the fraction of samples that passed all boolean assertions across all evaluators.
- Top-level field; rendered in CLI summary.

### Layered eval

- `EvalMetric.priority: int = 0` (lower runs first).
- Default ordering: deterministic checks (priority 0) → numeric metrics (priority 10) → LLMJudge-based (priority 20).
- When an Evaluator emits a "skip later" signal (new `SkipLater` exception), subsequent higher-priority evaluators are skipped for that sample (cost optimization).

### New default: RationaleGrounding LLMJudge

- New default metric: takes a peer Comment + the cited diff hunk + cited codebase context; judge prompt: "Does this comment's rationale accurately reference the code it cites? Score 0-1 with reasoning."
- Caught directly the hallucinated-line citation issue from PR 7677.
- Added to default metric set (after PrecisionPerSeverity).

### Schema-bumped EvalReport

- `report_schema_version` bumps from `"1.0"` to `"2.0"`.
- New: `pass_rate`, `per_metric_aggregation_kind` (sum-of-sums / mean / pass-rate / per-tier), captured-message linkage.
- Migration path: `EvalReport.from_json` accepts both `"1.0"` and `"2.0"`; old reports auto-upgrade with sensible defaults.

## Capabilities

### Modified Capabilities

- `eval-runner` (from `eval-v01`): EvalMetric return type widens; per-sample evaluators added; async-first; new metrics. Existing user code (`EvalRunner(reviewer, dataset, metrics=[...])`) keeps working — defaults change, signatures preserve.

### New Capabilities

None — extension of `eval-runner`.

## Impact

- **Code**: rewrites of `src/peer/eval/metrics.py` (flexible return types + LLMJudge + RationaleGrounding + priority), `src/peer/eval/runner.py` (async + concurrency + case-specific eval), `src/peer/eval/judging.py` (refactored to be the LLMJudge default impl), `src/peer/eval/report.py` (pass_rate rendering), `src/peer/eval/types.py` (MetricResult.value union + schema bump).
- **Schema bump**: `EvalReport.report_schema_version: "1.0"` → `"2.0"`. Loader supports both with auto-upgrade.
- **Tests**: significant additions — new `tests/test_eval_v02.py` covering flexible return types, per-sample evaluators, async runner, configurable LLMJudge, layered eval, RationaleGrounding.
- **Performance**: re-running the 30-PR reference dataset goes from ~7min to ~90s at concurrency=5. Cost is unchanged.
- **Migration**: old `EvalReport` JSON files load with auto-upgrade; new fields default to None / empty.
- **Out of scope**: pydantic-evals as a dependency; HasMatchingSpan (no user-callable tools yet); ConfusionMatrixEvaluator (specialized, can land later).
