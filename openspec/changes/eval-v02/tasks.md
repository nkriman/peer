## 1. Schema bump + types

- [ ] 1.1 Add `AggregateKind` Enum to `src/peer/eval/types.py` with values `MEAN`, `SUM_OF_SUMS`, `PASS_RATE`, `PER_TIER`, `LATENCY_PERCENTILE`.
- [ ] 1.2 Widen `MetricResult.value` type to `Union[bool, int, float, str, dict, None]`. Update Pydantic field definition.
- [ ] 1.3 Add `EvalSummary.pass_rate: Optional[float] = None`.
- [ ] 1.4 Add `EvalSummary.per_metric_aggregation_kind: dict[str, str] = {}` for forensic visibility.
- [ ] 1.5 Add `EvalSampleResult.skipped_metrics: list[tuple[str, str]] = []`.
- [ ] 1.6 Bump `REPORT_SCHEMA_VERSION = "2.0"`. Keep `"1.0"` recognition path in `from_json`.

## 2. EvalMetric Protocol extension

- [ ] 2.1 Add `priority: int = 0` to EvalMetric Protocol (structural, doesn't break existing impls — Protocols are duck-typed).
- [ ] 2.2 Add `aggregate_kind: AggregateKind = AggregateKind.MEAN` (default — back-compat).
- [ ] 2.3 Add `aggregate(per_sample_results: list[MetricResult]) -> tuple[Any, dict]` classmethod for metric-specific aggregation. Default = mean (current eval-metrics-v01 behavior).

## 3. New SkipLater exception + layered execution

- [ ] 3.1 Add `SkipLater` exception in `src/peer/exceptions.py`.
- [ ] 3.2 In EvalRunner per-sample loop, sort `metrics` by priority before iterating.
- [ ] 3.3 Catch `SkipLater` during per-metric scoring; record skip + reason in `sample_result.skipped_metrics`; INFO log.

## 4. Case-specific evaluators

- [ ] 4.1 Add `evaluators: list[EvalMetric] = Field(default_factory=list)` to `GoldSample` Pydantic model.
- [ ] 4.2 In EvalRunner per-sample loop, run dataset-wide metrics + `sample.evaluators` merged (case-specific overrides dataset-wide on name collision; DEBUG log).
- [ ] 4.3 Add `MetricSpec` Pydantic model (class_name + args) for JSONL serialization of case-specific evaluators.
- [ ] 4.4 Implement `_resolve_metric_spec(spec)` → import + instantiate. Raises `InvalidGoldSample` on unknown class.
- [ ] 4.5 Update `GoldSample.model_validate` / `model_dump` so evaluators round-trip via MetricSpec.

## 5. Async-first runner

- [ ] 5.1 Refactor `EvalRunner` per design.md Decision 3: `__init__` accepts `concurrency=5`; new `run_async()` method; existing `run()` becomes `asyncio.run(self.run_async())`.
- [ ] 5.2 Per-sample logic moved into `async def _eval_sample(sample) -> EvalSampleResult`.
- [ ] 5.3 `Semaphore(self.concurrency)` gates concurrent runs.
- [ ] 5.4 Sync reviewer wrapped in `asyncio.to_thread`; sync metric `.score()` similarly wrapped.

## 6. Configurable LLMJudge class

- [ ] 6.1 Promote `LLMJudge` to first-class Evaluator class in `src/peer/eval/judging.py`. Fields per design.md Decision 4.
- [ ] 6.2 Build prompt dynamically from `rubric` + (optional) `include_input` + (optional) `include_expected_output` + (always) `include_reason`.
- [ ] 6.3 Parse LLM response: SAME/DIFFERENT for boolean rubrics; 0-1 float for score rubrics. Heuristic-based; document the parsing.
- [ ] 6.4 Existing `judge_match(peer, gold)` becomes a thin wrapper around `LLMJudge(rubric="Same issue or different?", ...)`.
- [ ] 6.5 Update DefectRecall (now MeanPerPRRecall) + NoveltyRate + PrecisionPerSeverity + SeverityCalibration to use the new LLMJudge under the hood.

## 7. RationaleGrounding metric

- [ ] 7.1 Implement `RationaleGrounding` as `LLMJudge` subclass with fixed rubric + per-comment scoring loop.
- [ ] 7.2 For each peer Comment, build a per-comment judge prompt including the cited diff hunk + relevant codebase context.
- [ ] 7.3 Aggregate per-comment scores into a per-sample mean.
- [ ] 7.4 Add to default metric set in EvalRunner: `[DetectionRate, CommentsPerPR, PrecisionPerSeverity, RationaleGrounding, SuggestionRate, MeanPerPRRecall, NoveltyRate, SeverityCalibration]`.

## 8. Aggregation refactor

- [ ] 8.1 Replace per-metric-name switch in `_aggregate_metrics` (eval-metrics-v01 shape) with dispatch on `metric.aggregate_kind`.
- [ ] 8.2 Implement `_aggregate_sum_of_sums`, `_aggregate_mean`, `_aggregate_pass_rate`, `_aggregate_per_tier`, `_aggregate_latency_percentile` helpers.
- [ ] 8.3 Surface `EvalSummary.per_metric_aggregation_kind` post-run for forensics.

## 9. Schema migration

- [ ] 9.1 `EvalReport.from_json` recognizes `"1.0"` and `"2.0"`. v1.0 auto-upgrades: missing new fields default to None / empty.
- [ ] 9.2 INFO log on auto-upgrade: "loaded v1.0 report; pass_rate not computed (v1.0 reports lack boolean metrics)".

## 10. Reporting

- [ ] 10.1 Update `render_summary` to render `pass_rate` in Headline section.
- [ ] 10.2 Render `skipped_metrics` count in per-sample section.
- [ ] 10.3 Render `aggregate_kind` next to each metric in Secondary section ("(sum-of-sums)" / "(mean)" / "(pass-rate)" / "(per-tier)").
- [ ] 10.4 Update `render_diff` to handle missing pass_rate in baseline (when baseline is v1.0).

## 11. CLI

- [ ] 11.1 Add `--concurrency N` to `peer eval` (default 5).
- [ ] 11.2 Add `--with-rationale-grounding/--no-rationale-grounding` flag (default on).
- [ ] 11.3 Add `--metrics MODULE_PATH` flag (loads user-defined metrics from Python module).

## 12. Tests

- [ ] 12.1 `tests/test_eval_v02_returntype.py` — MetricResult accepts bool/int/float/str/dict/None.
- [ ] 12.2 `tests/test_eval_v02_case_specific.py` — GoldSample with case-specific evaluators; runner runs them; name collision case-wins.
- [ ] 12.3 `tests/test_eval_v02_async.py` — run_async with mocked reviewer + metrics; concurrency=1 sequential vs concurrency=5 parallel timing assertion.
- [ ] 12.4 `tests/test_eval_v02_llmjudge.py` — LLMJudge with mock client; rubric included; include_reason populates reason field.
- [ ] 12.5 `tests/test_eval_v02_layered.py` — priority ordering; SkipLater skips higher-priority; skipped_metrics populated.
- [ ] 12.6 `tests/test_eval_v02_rationalegrounding.py` — RationaleGrounding scores correctly identify grounded vs hallucinated rationale (mock judge returns).
- [ ] 12.7 `tests/test_eval_v02_aggregation.py` — AggregateKind dispatch; pass_rate computed; per_metric_aggregation_kind populated.
- [ ] 12.8 `tests/test_eval_v02_schema_migration.py` — v1.0 report loads + auto-upgrades; v2.0 round-trips.
- [ ] 12.9 `tests/test_eval_v02_metricspec.py` — case-specific evaluators round-trip via JSONL.

## 13. Docs

- [ ] 13.1 Update `docs/framework_overview.md` with the eval-v02 surface (case-specific evaluators, async, configurable LLMJudge, RationaleGrounding, layered eval).
- [ ] 13.2 Add migration notes for eval-v01 → eval-v02 (mostly seamless; schema auto-upgrades; new metrics opt-out via CLI).

## 14. Verification

- [ ] 14.1 Re-run `peer eval --dataset dataset/reference/django_pydantic_v2.jsonl` with eval-v02 implementation. Expect:
  - ~90s wall-clock at concurrency=5 (down from ~7min sequential)
  - pass_rate reported (likely None until users add bool metrics)
  - rationale_grounding score per sample
  - Detection rate / precision unchanged from eval-metrics-v01 baseline (this is structure refactor + new metric, not changes to existing scoring)
- [ ] 14.2 Spot-check RationaleGrounding output on PR 7677 — should catch any hallucinated-line-citation issues in peer's comments.
- [ ] 14.3 Verify schema migration on the existing v1.0 reports in `data/eval_runs/`.
