# Pydantic Evals' design philosophy — what peer should learn

**Source:** [pydantic.dev/docs/ai/evals/](https://pydantic.dev/docs/ai/evals/) — Pydantic's eval framework that ships alongside Pydantic AI.

## TL;DR

Pydantic Evals has, in many ways, **already shipped what peer's `eval-v01` is** — Case → Dataset → Evaluator → Report, almost identical decomposition. But they made several design calls peer didn't, and on inspection some of those calls are clearly better:

| | peer's eval-v01 | pydantic-evals | Verdict |
|---|---|---|---|
| Sample unit | `GoldSample` (Pydantic model) | `Case` (Pydantic model) | Same shape |
| Sample collection | `list[GoldSample]` + JSONL storage | `Dataset` (with cases + dataset-wide evaluators) | pydantic-evals' shape is cleaner |
| Scorer | `EvalMetric` Protocol | `Evaluator` dataclass | Both work; dataclass is simpler |
| Return type | `MetricResult` (always `Optional[float]` + dict) | `bool \| int \| float \| str \| dict` | **pydantic-evals wins** — flexible |
| Per-case evaluators | Not supported (all metrics apply uniformly) | Supported per `Case` | **pydantic-evals wins** — important |
| Aggregation | sum-of-sums + mean (after eval-metrics-v01) | `pass_rate` + averages by default | Both work |
| Built-in evaluators | 0 generic; 3 PR-review-specific | 7 generic + LLMJudge | pydantic-evals has more generic |
| Async support | Sync default; no parallelism control | Async-first with concurrency settings | **pydantic-evals wins** — peer's eval is sequential and slow |
| Pytest integration | None | Stdlib pytest patterns + report assertions | pydantic-evals' is documented |

## Their abstractions

### Case = one test scenario

```python
Case(
    name='auth_pr',
    inputs='https://github.com/.../pull/42',     # passed to the task function
    expected_output=[GoldDefect(...), ...],       # ground truth
    metadata={'difficulty': 'hard', 'category': 'security'},
    evaluators=[LLMJudge(rubric='check security...')],  # case-specific!
)
```

The `evaluators=` on Case is a really important design choice — different cases can have completely different rubrics. peer's current design uses one set of metrics for the entire dataset.

### Dataset = cases + global evaluators

```python
Dataset(
    name='django_pydantic_v2',
    cases=[case1, case2, ...],
    evaluators=[DetectionRate(), CommentsPerPR()],  # apply to ALL cases
)
```

Two-tier evaluator system: case-specific (specialized rubrics per scenario) + dataset-wide (generic metrics across all). peer has only the dataset-wide tier.

### Evaluator = scores output

```python
@dataclass
class CustomEvaluator(Evaluator):
    def evaluate(self, ctx: EvaluatorContext) -> bool:
        return ctx.output == ctx.expected_output
```

Subclass `Evaluator` (a dataclass). Implement `evaluate(ctx)`. Return:
- `bool` → assertion (✔/✗)
- `int`/`float` → numeric score
- `str` → categorical label
- `dict` → multiple metrics from one evaluator

The dict-return pattern is what peer's `MetricResult.per_sample_detail` clumsily reinvents. Single mechanism, no awkward split.

### Built-in evaluators

| Evaluator | Purpose |
|---|---|
| `EqualsExpected` | Exact match |
| `Equals` | Match against specific value |
| `Contains` | Substring / element presence |
| `IsInstance` | Type validation |
| `MaxDuration` | Performance threshold |
| `HasMatchingSpan` | Behavior verification (e.g., "did the agent call tool X?") |
| `LLMJudge` | Subjective scoring with configurable rubric |
| `ConfusionMatrixEvaluator` | Report-level classification analysis |

`LLMJudge` is the gold one. Configurable:
- `rubric=` — what to check for, in natural language
- `include_input=True` — judge sees the original input
- `include_expected_output=True` — judge sees ground truth
- `include_reason=True` — judge must explain (debuggability)
- `model=` — which LLM to use as judge

### Execution model

`Dataset.evaluate(task_func)` is async-first. Runs `task_func(case.inputs)` for each case, collects outputs, runs evaluators (case-specific + dataset-wide), aggregates into `EvaluationReport`. Concurrency is configurable; retries via separate "Retry Strategies" guide.

`evaluate_sync(task_func)` is the sync wrapper.

### Report

`EvaluationReport.print(include_input=True, include_output=True, include_durations=True)` — prints a formatted table of cases, outputs, scores, assertions, durations. Top-line `pass_rate` attribute.

## Their explicit anti-patterns (worth taking to heart)

From the [LLM-as-a-judge guide](https://pydantic.dev/articles/llm-as-a-judge):

1. **"If you could write a single evaluator rubric that perfectly captured your requirements across all cases, you'd just incorporate that rubric into your agent's instructions."**

   This is a *deeply* important insight for peer. We've been trying to score peer's reviewer against human comments via a judge. But if the judge knows what makes a good review, why isn't that knowledge in the agent prompt? The smart eval is **complementary** to the agent — measures what the agent can't measure for itself (ground truth, side effects, behavior across many runs).

2. **Vague rubrics ("I'll know it when I see it") leave the judge improvising.** Make the rubric specific.

3. **Generic one-size-fits-all rubrics** produce mushy standards. Use case-specific rubrics where the variance is high.

4. **Brittle deterministic matching** (`'refund' in response`) fails on synonyms. Use semantic eval instead.

5. **Ignoring judge reasoning** — `include_reason=True` always; debug-able evals beat opaque scores.

6. **Deleting passing test cases** post-fix — keep them as regression guards. Prompts and models drift.

7. **Layer fast checks before slow ones**: IsInstance / MaxDuration / Contains first, LLMJudge last.

## What peer should adopt

### High-impact, small refactors

1. **Evaluator return-type flexibility.** Currently `MetricResult.value: Optional[float]`. Change to allow `bool | int | float | str | dict`. Removes the awkward `per_sample_detail` field — a dict-returning Evaluator carries multiple metrics natively. Affects `MetricResult`, `EvalRunner._aggregate_metrics`, and every metric impl. ~50 LOC.

2. **Case-specific evaluators.** Add `GoldSample.evaluators: list[EvalMetric] = Field(default_factory=list)`. In the runner, run dataset-wide metrics + case-specific metrics per sample. Lets users ship per-PR rubrics (e.g., a security-focused PR gets a security-specific LLMJudge). ~30 LOC.

3. **Configurable `LLMJudge` class.** Currently peer has a hardcoded `judge_match(peer, gold)`. Promote to:

   ```python
   @dataclass
   class LLMJudge(Evaluator):
       rubric: str
       model: str = 'claude-haiku-4-5-20251001'
       include_input: bool = False
       include_expected: bool = True
       include_reason: bool = True
   ```

   Lets users instantiate with custom rubrics per-Case. The current `judge_match` becomes `LLMJudge(rubric="determine if the two comments flag the same issue", ...)`. ~50 LOC.

4. **Async eval runner with concurrency control.** Currently peer's `EvalRunner.run()` is sequential — 30 PRs at ~15s each = 7-8 minutes. With async + concurrency=5, the same run finishes in ~90 seconds. Major UX win. ~100 LOC refactor.

5. **`pass_rate` top-level attribute on EvalReport.** Simple aggregate that complements `detection_rate`. Useful for "did we keep passing the same cases" regression check. ~10 LOC.

### Bigger architectural shifts

6. **Case = GoldSample with inputs + expected_output + evaluators.** Currently `GoldSample` has `gold_defects: list[GoldDefect]` (which plays the role of expected_output). Restructure to:

   ```python
   class GoldSample(BaseModel):
       name: str
       inputs: PRInputs           # pr_url + repo_info
       expected_output: list[GoldDefect]
       metadata: GoldSampleMetadata
       evaluators: list[EvalMetric] = []  # case-specific
   ```

   Schema change for v0.2 datasets. Old datasets need migration. Worth doing pre-1.0; bigger change post-1.0. ~moderate effort, schema migration tool needed.

7. **Layer eval: fast deterministic → slow LLM judges.** Currently peer runs all evaluators with no ordering. Add `Evaluator.priority: int = 0` so fast checks run first; if a sample fails a fast check, skip the slow LLMJudge. Cost saver. ~30 LOC.

8. **HasMatchingSpan-equivalent for agent tool calls.** If peer ever lets the agent call tools (find_callers, run_linter, etc.), we'd want to verify behavior: "did the agent call `find_call_sites` on this symbol?" Out of scope until peer has user-callable tools.

### Explicit non-adoptions

- **Don't depend on pydantic-evals.** Same reasoning as Pydantic AI: heavy dep, lock-in, framework-of-frameworks. Borrow patterns.
- **Don't adopt their pytest test patterns directly.** Our `peer eval` CLI is the right surface for our users; pytest assertions are useful internally for unit tests but not as the user-facing eval interface.

## The deeper insight

**"If your evaluator rubric matches your agent prompt, just include the rubric in the prompt."**

This reframes what peer's `eval-v01` should actually measure. Three categories of signal:

1. **Things the agent can self-check** (output format, line numbers in hunks, severity from a vocab). → encode in prompt; verify with deterministic evaluators.
2. **Things the agent CAN'T self-check** — needs ground truth (did human reviewers flag this? was a follow-up bugfix needed?). → this is where eval lives.
3. **Things requiring meta-judgment** (is this comment substantive? is the rationale grounded?). → LLMJudge with rich rubric.

peer's current `DetectionRate` is category 2 — comparing against human gold. Good.
peer's `PrecisionPerSeverity` is category 2 — same.
peer's `NoveltyRate` is category 1 — we already know in the agent prompt to be non-redundant; the metric just counts what slipped through.
peer's `SeverityCalibration` is category 2 — comparing agent severity to human severity.

But peer is MISSING category 3 entirely. We have no LLMJudge that scores "is this peer comment substantive?" or "is the rationale grounded in the cited code?" That's where the framework's real value lives — measuring things the agent can't measure for itself.

**Concrete missing evaluator: `RationaleGrounding`** — LLMJudge that takes a peer Comment + the cited diff + the cited codebase context, asks "does the comment's rationale accurately reference what's in this code?" Score 0-1. This would have caught the hallucinated-line-number issue we saw in PR 7677 directly.

## Net impact on the in-flight changes

Adding these capabilities is its own change — call it **`eval-v02`** — that ships after the current v0.2 wave (`eval-metrics-v01` through `benchmark-v01`). Doing it now would require pausing 5 in-flight changes for a deeper refactor.

Recommended order (updated from the Pydantic AI analysis):

1. `prompt-quality-v01` ✅ done
2. `eval-metrics-v01` finish implementing (already in progress)
3. **`peer-deps-v01`** new — Pydantic-AI-inspired deps_type/override/TestReviewer
4. `peer-config-v01` (slots into PeerDeps)
5. `linter-context-v01` (linters as PeerDeps field)
6. `patch-suggestions-v01` (with validation retries)
7. `benchmark-v01`
8. **`eval-v02`** new — Pydantic-evals-inspired Case-specific evaluators, flexible return types, async, configurable LLMJudge, RationaleGrounding
9. Defer: `peer-pydantic-ai-v01` (optional adapter), `peer-pydantic-evals-v01` (optional adapter)

The two adapter changes (8 and 9) let users plug in if they're already in those ecosystems, without forcing peer to depend on them.

## Decision needed

We've gone from 5 in-flight changes to 7 (added `peer-deps-v01` and `eval-v02`) plus 2 deferred adapters. The implementation cost is real — probably 20+ hours total across all of them.

Three options to bound scope:

**A) Ship everything.** All 7 changes implemented; ~20+ hours; produces a v0.2 that's industry-aligned in every dimension.

**B) Ship the original 5 (`eval-metrics-v01` through `benchmark-v01`).** Skip `peer-deps-v01` and `eval-v02`. Accept the technical debt of the flat-kwargs Agent constructor and the inflexible eval; address in a v0.3 refactor wave once we have real user evidence the v0.2 changes work.

**C) Ship `peer-deps-v01` + the original 5.** Skip `eval-v02`. The Agent constructor cleanup is the higher-value of the two refactors; the eval-v02 work can wait.

Lean: **C**. The Agent refactor is small (~3-4 hours), clean, and affects API surface that we'd otherwise have to break later. The eval-v02 refactor is bigger and lower-stakes (peer's current eval works; the upgrade is mostly ergonomic + flexibility).

## Sources

- [Pydantic Evals overview](https://pydantic.dev/docs/ai/evals/evals/)
- [Evaluators overview](https://pydantic.dev/docs/ai/evals/evaluators/overview/)
- [LLMJudge](https://pydantic.dev/docs/ai/evals/evaluators/llm-judge/)
- [Built-in Evaluators](https://pydantic.dev/docs/ai/evals/evaluators/built-in/)
- [Quick Start](https://pydantic.dev/docs/ai/evals/quick-start/)
- [LLM-as-a-Judge: A Practical Guide](https://pydantic.dev/articles/llm-as-a-judge)
