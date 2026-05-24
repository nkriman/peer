## MODIFIED Requirements

### Requirement: MetricResult.value accepts a flexible union of types

`MetricResult.value` SHALL be typed as `Union[bool, int, float, str, dict, None]`. Old metrics returning `Optional[float]` continue to validate; new metrics may return bool / dict / str natively without using `per_sample_detail` as a workaround.

#### Scenario: Bool-returning evaluator

- **WHEN** a custom `Evaluator` returns `MetricResult(name="x", value=True)`
- **THEN** the result validates AND `result.value is True` (not coerced to 1.0)

#### Scenario: Dict-returning evaluator carries multiple metrics

- **WHEN** an `Evaluator` returns `MetricResult(name="multi", value={"a": 0.5, "b": "good"})`
- **THEN** `result.value == {"a": 0.5, "b": "good"}` and downstream renderers handle the nested structure

### Requirement: GoldSample supports case-specific evaluators

The `GoldSample` Pydantic model SHALL gain an optional `evaluators: list[EvalMetric] = Field(default_factory=list)` field. `EvalRunner` SHALL run dataset-wide metrics AND each sample's case-specific evaluators on every sample.

#### Scenario: Case-specific evaluator runs only on its sample

- **WHEN** a `GoldSample(evaluators=[LLMJudge(rubric="security-focused")])` is in a Dataset alongside other samples without that evaluator
- **THEN** the `LLMJudge(rubric="security-focused")` runs only on this one sample, and its results appear only in this sample's `EvalSampleResult.metrics`

#### Scenario: Name collision: case-specific wins

- **WHEN** a dataset-wide evaluator has `name="precision_per_severity"` AND a sample's case-specific evaluator also has `name="precision_per_severity"`
- **THEN** the case-specific evaluator's result replaces the dataset-wide one in `sample_result.metrics["precision_per_severity"]`; a DEBUG log records the override

### Requirement: EvalRunner.run_async with configurable concurrency

`EvalRunner.__init__` SHALL accept `concurrency: int = 5`. A new `run_async() -> EvalReport` method SHALL run samples in parallel via `asyncio.gather` with a `Semaphore(self.concurrency)`. The existing `run() -> EvalReport` SHALL become a sync wrapper that invokes `asyncio.run(self.run_async())`.

#### Scenario: Sync wrapper works as before

- **WHEN** `EvalRunner(reviewer, dataset).run()` is called (no concurrency arg, sync entry)
- **THEN** behavior matches eval-v01 + eval-metrics-v01 (same returned EvalReport shape, possibly faster due to internal parallelism); all existing tests pass

#### Scenario: Custom concurrency

- **WHEN** `EvalRunner(reviewer, dataset, concurrency=10).run_async()` is awaited
- **THEN** up to 10 samples are processed concurrently

#### Scenario: Sync reviewer + sync metrics still work

- **WHEN** a Reviewer's `review()` is synchronous and the metrics' `score()` is synchronous
- **THEN** EvalRunner wraps each via `asyncio.to_thread`; the run still parallelizes effectively

### Requirement: LLMJudge is a configurable Evaluator

The framework SHALL provide `peer.eval.LLMJudge` as a configurable `Evaluator` dataclass with fields: `rubric` (str, required), `model` (str, default `"anthropic:claude-haiku-4-5-20251001"`), `include_input` (bool, default False), `include_expected_output` (bool, default True), `include_reason` (bool, default True), `priority` (int, default 20).

#### Scenario: Configure rubric and model

- **WHEN** `LLMJudge(rubric="Custom rubric", model="anthropic:claude-sonnet-4-6")` is instantiated and called via `.score(...)`
- **THEN** the LLM call uses the supplied model and the rubric appears in the prompt

#### Scenario: include_reason adds reasoning to result

- **WHEN** `LLMJudge(rubric="...", include_reason=True)` scores a sample
- **THEN** the returned `MetricResult.per_sample_detail` (or `MetricResult.value` if dict-returning) includes a `reason` field with the judge's natural-language explanation

#### Scenario: legacy judge_match still works

- **WHEN** existing call to `judge_match(peer, human, client=None)` is made
- **THEN** it returns a bool identical to prior behavior (wrapper around `LLMJudge(rubric="Same issue?")`)

### Requirement: pass_rate is NOT introduced by eval-v02

Per adversarial review 5.1 — `pass_rate` SHALL NOT be added to `EvalSummary` in this change. All default metrics return float or dict, so `pass_rate` would always be `None`. The framework MUST defer introducing this field until a change ships a boolean default metric whose pass/fail aggregate is meaningful.

#### Scenario: No pass_rate field on EvalSummary

- **WHEN** an `EvalReport` is constructed
- **THEN** the EvalSummary does NOT have a `pass_rate` field — it can be added in a future change without breaking schema compat (additive field)

### Requirement: Layered eval via priority + SkipLater

Each `EvalMetric` SHALL expose `priority: int = 0`. EvalRunner SHALL run metrics on a sample in ascending priority order. A new `SkipLater` exception, when raised by a metric's `score()`, SHALL cause all higher-priority metrics to be skipped for that sample (logged at INFO). Skipped metrics are recorded in `EvalSampleResult.skipped_metrics: list[tuple[str, str]]` (metric name + skip reason).

#### Scenario: Lower-priority metric runs first

- **GIVEN** `[DetectionRate(priority=10), LLMJudge(rubric="...", priority=20)]`
- **WHEN** EvalRunner runs on a sample
- **THEN** DetectionRate runs first, then LLMJudge

#### Scenario: SkipLater short-circuits

- **WHEN** a priority-0 metric raises `SkipLater("output malformed")` for a sample
- **THEN** all higher-priority metrics for that sample are skipped; their absence is recorded in `sample_result.skipped_metrics`; INFO log "skipped N metrics due to SkipLater from <metric>: output malformed"

### Requirement: RationaleGrounding metric (opt-in)

The framework SHALL ship `peer.eval.RationaleGrounding` as an `LLMJudge` subclass with a specific rubric. It SHALL be available for users to opt into but is NOT in the default metric set (cost: ~$0.09/30-PR-run that may not catch anything on well-calibrated reviewers — see eval-v02 proposal.md "Honest note on motivation"). The rubric checks whether each peer Comment's rationale accurately references the code it cites. Returns a per-comment dict `{score: 0..1, reason: str}`, aggregated to a per-sample mean score.

#### Scenario: RationaleGrounding NOT in defaults

- **WHEN** `EvalRunner(reviewer, dataset).run()` is called with no `metrics=` override
- **THEN** `report.summary.metric_values` does NOT contain the key `"rationale_grounding"` — users must opt in by passing `metrics=[..., RationaleGrounding(), ...]` or via `peer eval --with-rationale-grounding`

#### Scenario: RationaleGrounding opt-in via CLI

- **WHEN** `peer eval --with-rationale-grounding --dataset ...` is invoked
- **THEN** the default metric list is extended with `RationaleGrounding()` and the resulting report includes `rationale_grounding` aggregate

#### Scenario: RationaleGrounding penalizes hallucinated citation

- **GIVEN** a peer Comment whose rationale says "line 442 uses ==" but the cited code at line 442 doesn't use `==`
- **WHEN** RationaleGrounding scores this Comment
- **THEN** the per-comment score is low (≤0.5) and the reason field cites the discrepancy

#### Scenario: RationaleGrounding can be disabled

- **WHEN** `peer eval --no-rationale-grounding` is invoked
- **THEN** the run skips RationaleGrounding (savings ~$0.001 per peer comment)

### Requirement: EvalReport schema bumps to 2.0 with migration support

`EvalReport.report_schema_version` SHALL bump from `"1.0"` to `"2.0"`. `EvalReport.from_json` SHALL accept BOTH versions; v1.0 reports auto-upgrade with sensible defaults (`pass_rate=None`, no `per_metric_aggregation_kind`, etc.) and an INFO log. Unknown versions raise `EvalReportSchemaMismatch`.

#### Scenario: New report writes v2.0

- **WHEN** an EvalReport produced by the new EvalRunner is `to_json`-saved
- **THEN** the file's `report_schema_version` is `"2.0"`

#### Scenario: Old v1.0 report loads with auto-upgrade

- **WHEN** `EvalReport.from_json` reads a file with `report_schema_version: "1.0"`
- **THEN** the report loads successfully; an INFO log records the auto-upgrade; `report.summary.pass_rate is None`

### Requirement: Case-specific evaluators are JSONL-serializable via MetricSpec

The framework SHALL provide a `MetricSpec` Pydantic model with `class_name: str` and `args: dict`. When `GoldSample.evaluators` is serialized to JSONL, each evaluator SHALL be written as a `MetricSpec`; on load, the framework SHALL instantiate the metric via `_resolve_metric_spec(spec)` which imports the named class and applies `**spec.args`.

#### Scenario: Round-trip a case-specific evaluator

- **WHEN** `GoldSample(evaluators=[LLMJudge(rubric="security")])` is serialized via `JSONLStorage.add` and reloaded via `load_all`
- **THEN** the loaded sample's `evaluators[0]` is a `LLMJudge` instance with `rubric="security"`

#### Scenario: Unknown MetricSpec class raises

- **WHEN** a JSONL line contains `evaluators: [{"class_name": "peer.eval.UnknownEvaluator", "args": {}}]`
- **THEN** load raises `InvalidGoldSample` with a clear message naming the unresolvable class

## ADDED Requirements

### Requirement: EvalMetric.score signature back-compat

The existing `EvalMetric.score(self, sample, review, client: Optional[anthropic.Anthropic] = None) -> MetricResult` signature SHALL continue to work in `eval-v02` via introspection. The Runner SHALL inspect the metric's `score` signature: if it accepts `client=`, the legacy Anthropic client is passed; if it accepts `ctx=`, a `RunContext` is passed; metrics that accept neither receive the call without optional params. NEW metrics SHOULD prefer `ctx=` (typed access to deps); legacy metrics keep working unchanged.

#### Scenario: Legacy metric with `client=` keyword still runs

- **GIVEN** a custom `LegacyMetric` whose `score(self, sample, review, client=None)` matches the pre-v02 signature
- **WHEN** the Runner invokes `LegacyMetric().score(...)` during a run
- **THEN** the runner inspects the signature, sees `client` parameter, and passes the shared Anthropic client; no `ctx` is passed

#### Scenario: New metric with `ctx=` keyword

- **GIVEN** a custom `NewMetric` whose `score(self, sample, review, ctx=None)` uses the new signature
- **WHEN** the Runner invokes `NewMetric().score(...)`
- **THEN** the runner passes a `RunContext` with the sample's deps; no `client` is passed

#### Scenario: Bare-signature metric

- **GIVEN** a metric whose `score(self, sample, review)` accepts neither
- **WHEN** the Runner invokes it
- **THEN** the call succeeds with only sample + review; no client or ctx parameter is passed

### Requirement: AggregateKind drives report-level aggregation

The framework SHALL define an `AggregateKind` enum (e.g., `MEAN`, `SUM_OF_SUMS`, `PASS_RATE`, `PER_TIER`, `LATENCY_PERCENTILE`). Each `EvalMetric` SHALL declare its `aggregate_kind`. The EvalRunner's aggregator SHALL dispatch on this enum instead of switching on metric name strings (current `eval-metrics-v01` shape).

#### Scenario: Custom metric declares aggregate kind

- **WHEN** a user defines `class MyMetric: name="my"; aggregate_kind=AggregateKind.PASS_RATE; def score(...): return MetricResult(value=True)` and adds it to EvalRunner
- **THEN** report-level aggregation for `"my"` uses pass-rate semantics (fraction of samples that returned True)

### Requirement: --concurrency / --no-rationale-grounding CLI flags

`peer eval` SHALL accept:
- `--concurrency N` (int, default 5)
- `--no-rationale-grounding` (flag, default on)

#### Scenario: Concurrency flag wires to runner

- **WHEN** `peer eval --concurrency 10 --dataset ...` is invoked
- **THEN** the constructed EvalRunner uses `concurrency=10`

#### Scenario: No-rationale-grounding skips the metric

- **WHEN** `peer eval --no-rationale-grounding --dataset ...` is invoked
- **THEN** the constructed default metric list excludes `RationaleGrounding`
