## Context

`eval-v01` shipped the right decomposition (GoldSample / EvalMetric / EvalRunner / EvalReport). `eval-metrics-v01` improved the headline metrics. This change adopts the remaining good ideas from Pydantic Evals — flexibility, per-case rubrics, async, the missing meta-judgment category — without taking pydantic-evals as a dep.

## Goals / Non-Goals

**Goals:**
- Match pydantic-evals' Evaluator-return-type flexibility (`bool | int | float | str | dict`).
- Match its case-specific evaluator pattern (different rubrics per Case).
- Match its async-first runner with configurable concurrency.
- Match its configurable `LLMJudge` (rubric / model / include_input / include_expected / include_reason).
- Add the missing category-3 metric: `RationaleGrounding`.
- Layer eval (fast checks first; LLMJudge last) for cost.
- Maintain back-compat for existing EvalMetric impls + EvalRunner callers.

**Non-Goals:**
- pydantic-evals as a dep.
- `HasMatchingSpan` — no user-callable agent tools yet.
- `ConfusionMatrixEvaluator` — can land later as a specialized metric.
- Pytest-as-eval-framework — peer's `peer eval` CLI is the user-facing surface.
- Streaming eval results.
- Distributed eval (single-process async is enough for v0.2).

## Decisions

### 1. Evaluator return type widens to `Union[bool, int, float, str, dict, None]`

`MetricResult.value: Union[bool, int, float, str, dict, None]`. Old impls returning `Optional[float]` stay valid.

**Why this isn't backward-incompat:** `Optional[float]` is a subset of the new union. Old user code reading `result.value` gets the same float; new user code may see a dict. Renderers + aggregators learn to switch on type.

**Aggregation kind tracking:** each metric exposes `aggregate_kind: AggregateKind` (`SUM_OF_SUMS`, `MEAN`, `PASS_RATE`, `PER_TIER`, `LATENCY_PERCENTILE`). The runner uses this to decide aggregation strategy (currently hand-coded per-metric-name in `eval-metrics-v01`). Cleaner extension surface for users adding their own metrics.

```python
class EvalMetric(Protocol):
    name: str
    priority: int  # lower runs first
    aggregate_kind: AggregateKind

    def score(self, sample, review, ctx=None) -> MetricResult: ...

    @classmethod
    def aggregate(cls, per_sample_results: list[MetricResult]) -> tuple[Optional[Any], dict]:
        # Default: mean of floats; metrics override for sum-of-sums, per-tier, etc.
        ...
```

### 2. Case-specific evaluators via `GoldSample.evaluators`

```python
class GoldSample(BaseModel):
    pr_url: str
    pr_title: str
    gold_defects: list[GoldDefect]
    evaluators: list[EvalMetric] = Field(default_factory=list)  # case-specific
    # ... existing fields
```

EvalRunner per-sample flow:
1. Run dataset-wide metrics on the sample.
2. Then run `sample.evaluators` (if any).
3. Merge results into one `EvalSampleResult.metrics: dict[str, MetricResult]`.

**Naming collision:** if a case-specific metric has the same `name` as a dataset-wide one, the case-specific WINS (overrides for this sample). Logged at DEBUG.

### 3. Async-first runner with concurrency control

```python
class EvalRunner:
    def __init__(self, reviewer, dataset, metrics=None, concurrency: int = 5): ...

    async def run_async(self) -> EvalReport: ...
    def run(self) -> EvalReport:  # sync wrapper via asyncio.run
        return asyncio.run(self.run_async())
```

Per-sample concurrent via `asyncio.gather` with a `Semaphore(concurrency)`. Each sample's pipeline (reviewer call + per-metric scoring) is awaitable.

Reviewer's `review()` is currently sync. Wrap in `asyncio.to_thread()` so the runner doesn't block on synchronous Reviewer implementations. Metric scoring (LLMJudge calls etc.) is similarly wrapped.

**Why default concurrency=5:** Anthropic rate limits comfortably allow 5 parallel; OpenAI same. Users hitting rate limits set lower.

### 4. Configurable `LLMJudge` Evaluator

```python
@dataclass
class LLMJudge(Evaluator):
    rubric: str
    model: str = "anthropic:claude-haiku-4-5-20251001"
    include_input: bool = False
    include_expected_output: bool = True
    include_reason: bool = True
    priority: int = 20  # runs after deterministic checks

    def score(self, sample, review, ctx=None) -> MetricResult:
        # Build prompt from rubric + (optionally) input + (optionally) expected + ...
        # Call LLM judge; parse SAME / DIFFERENT or score 0-1 per rubric type
        ...
```

Used both as a default metric (`peer.eval.LLMJudge(rubric="...")`) and as the building block for `RationaleGrounding` (which is `LLMJudge` with a specific rubric).

The existing `judge_match(peer, gold)` becomes a thin wrapper:
```python
def judge_match(peer, gold, client=None) -> bool:
    judge = LLMJudge(rubric="Same issue or different issue? Return SAME or DIFFERENT.", ...)
    result = judge.score(...)
    return result.value == "SAME"
```

### 5. `pass_rate` top-level aggregate

`EvalSummary.pass_rate: Optional[float]` = fraction of samples where ALL boolean-returning evaluators passed.

Computed via `_aggregate_metrics` post-run. Visible in `render_summary` under Headline:

```
Headline:
  detection_rate              0.079
  comments_per_pr             1.97
  precision_per_severity      ...
  pass_rate                   0.733   (22/30 samples passed all assertions)
```

### 6. Layered eval via `priority` field + `SkipLater` exception

Default priorities:
- 0-9: deterministic (peer's existing metrics return float, but you can write boolean asserts at priority 0)
- 10-19: pricing/latency aggregates (CommentsPerPR, etc.)
- 20+: LLMJudge-based (PrecisionPerSeverity uses LLMJudge internally — priority 20)

Per-sample, metrics run in priority order. If an Evaluator raises `SkipLater(reason)`, all higher-priority metrics for that sample are skipped (logged at INFO with reason). Useful when a fast deterministic check shows the output is broken; no point spending LLMJudge calls.

Example: a hypothetical `OutputFormatValid` check (priority 0) returns False → SkipLater. Saves the LLMJudge run.

### 7. New default: `RationaleGrounding`

```python
class RationaleGrounding(LLMJudge):
    rubric = (
        "Score 0-1: does this code review comment's rationale accurately reference "
        "the code it cites? Specifically: are the line numbers correct? Are the "
        "function/variable names referenced actually present in the cited code? "
        "Are any cited 'consistent with X' claims actually consistent with X? "
        "Score 1.0 if the rationale is fully grounded; 0.0 if it's hallucinated. "
        "Always include reasoning."
    )
    model = "anthropic:claude-haiku-4-5-20251001"
    include_input = True   # judge needs to see the diff hunk
    include_expected_output = False
    include_reason = True
    priority = 25
```

Runs once per peer comment (not per sample). Reports mean grounding score across all peer comments in the sample. New default metric added after PrecisionPerSeverity.

**Why this is novel:** none of peer's existing metrics measure whether the rationale CITES real code — they only measure agreement with gold. `RationaleGrounding` is a category-3 meta-judgment per the pydantic-evals analysis.

### 8. Schema bump to `"2.0"` with migration

`EvalReport.report_schema_version: "2.0"`.

`EvalReport.from_json` checks the schema field:
- `"2.0"` → load as-is.
- `"1.0"` → log INFO, auto-upgrade. New fields (`pass_rate`, etc.) default to None; old metric_values dict reads identically.
- Anything else → raise `EvalReportSchemaMismatch`.

### 9. `peer eval` CLI: new flags

- `--concurrency N` (default 5)
- `--metrics FILE` (Python module providing custom metrics)
- `--with-rationale-grounding` (default OFF — opt-in; metric is expensive and the v1 reference dataset shows ~0% hallucination, so it's not worth running by default. Users with weaker reviewer models / less constrained prompts should opt in.)

## Risks / Trade-offs

- **[Risk]** Async refactor of EvalRunner is invasive; existing sync callers must keep working. **Mitigation:** `run()` is the sync wrapper; existing callers see no API change. Async-only internally.
- **[Risk]** Widening `MetricResult.value` type breaks code that reads `result.value` and assumes float. **Mitigation:** all peer's own callers do `Optional[float]` typing; external user code that read it as `Optional[float]` is now mildly inaccurate but doesn't break (the runtime value is still a float for the metrics that always returned floats). New metric types (dict, bool) require new caller code to consume — by definition the caller is opting in.
- **[Risk]** `RationaleGrounding` is expensive — one Haiku call per peer comment. With 30 PRs × ~3 comments avg = 90 calls × ~$0.001 = ~$0.09. Tractable but non-zero. **Mitigation:** opt-out via CLI flag; document in eval cost section.
- **[Risk]** Case-specific evaluators inside `GoldSample` JSONL serialization: how do you serialize a function/class instance? **Mitigation:** ship a `MetricSpec` Pydantic model with `class_name` + `args` that gets resolved to a Metric instance at load time. Same pattern as scikit-learn's `from_config`. Document.
- **[Risk]** Layered eval's `SkipLater` could hide failures (operator thinks all metrics ran). **Mitigation:** `EvalSampleResult.skipped_metrics: list[tuple[str, str]]` tracks which were skipped + why. Rendered in `render_summary`.
- **[Risk]** Concurrency=5 hits rate limits on Haiku-heavy benchmarks. **Mitigation:** CLI override; documented in benchmark docs.
- **[Risk]** Auto-upgrade of v1.0 reports may produce inaccurate `pass_rate` (no boolean metrics existed in v1.0). **Mitigation:** auto-upgraded reports have `pass_rate=None`; CLI renderer shows `n/a` rather than `0%`.
- **[Risk]** Naming collision in dataset-wide vs case-specific evaluators may surprise users. **Mitigation:** DEBUG log on collision; documented; perhaps a `peer eval --strict-no-collisions` flag.

## Open Questions

None blocking. Deferred:
- Should we ship a `HasMatchingSpan` analog now in anticipation of user-callable tools, or wait? Probably wait.
- Should `RationaleGrounding` score per-comment vs per-sample? Probably per-comment, aggregated; need to expose the per-comment scores in `per_sample_detail`.
- Should we let users override aggregation kind on a metric instance (e.g., user wants `MeanPerPRRecall` but with custom weights)? Maybe in `eval-v03`.
