# Adversarial review of v0.2 OpenSpec changes

Reviewer perspective: try to break the proposals. Cite files/lines. The author should respond to each item before landing.

---

## Section 1 — Should block landing as-is

### 1.1 `peer-deps-v01` breaks every `EvalMetric` and the EvalRunner in one stroke, with no spec or task acknowledging it

`src/peer/eval/metrics.py:298–322` (and every other `score`) is `def score(self, sample, review, client: Optional[anthropic.Anthropic] = None) -> MetricResult`. `EvalRunner.run` at `src/peer/eval/runner.py:258` calls them as `metric.score(sample, review, client=self._get_client())`.

`eval-v02` Decision 1 (`openspec/changes/eval-v02/design.md:35`) rewrites this signature to `def score(self, sample, review, ctx=None) -> MetricResult` and Task 6.5 (`openspec/changes/eval-v02/tasks.md:43`) requires *every* default metric to be rewritten to "use the new LLMJudge under the hood." There is no `client=` parameter in the new shape — the deps wrapper (`ctx.deps.client` or some such) is implied but never specified. eval-v02 spec.md doesn't promise back-compat with the existing keyword. Combined with `peer-deps-v01`'s "Reviewer Protocol gains an optional `ctx`" pattern, but only mentioning Reviewer — not EvalMetric — there's a hidden surface mismatch:

- `peer-deps-v01` Decision 11 only touches `Reviewer`. EvalMetric is not updated to accept `RunContext`.
- `eval-v02` Decision 1 changes EvalMetric.score signature but uses `ctx` (an opaque term that's never typed as `RunContext` in the spec).
- Neither change spec describes how a 3rd-party metric that takes `client=` will keep working when both land.

**Block:** add a `MODIFIED Requirement` in `eval-v02` for EvalMetric.score's signature explicitly, document the back-compat path (e.g., `inspect.signature` to detect `client=` vs `ctx=`), and add a scenario covering "legacy metric with `client=` parameter still runs."

### 1.2 `peer-deps-v01`'s `capture_run_messages` via contextvars will silently lose data under `eval-v02`'s async runner — and they're proposed to land together

`peer-deps-v01` tasks.md:10 (Task 2.1) says: *"Implement `capture_run_messages()` context manager in `src/peer/context.py`. Uses contextvars to maintain a per-thread/task list."*

`eval-v02` design.md:79: *"Reviewer's `review()` is currently sync. Wrap in `asyncio.to_thread()` so the runner doesn't block on synchronous Reviewer implementations."*

Python's `contextvars` does propagate into `asyncio.to_thread` (which uses `contextvars.copy_context`), but the captured-messages list is *mutated* inside the thread — and the recorder lives in the *caller's* context. If `Task 12.2` (`peer-deps-v01/tasks.md:88`: *"EvalRunner runs each sample inside a `capture_run_messages` block when configured"*) wraps `await asyncio.gather(...)` inside one outer block, then every concurrent sample shares one list, with no per-sample ordering guarantee.

Worse: `eval-v02`'s `EvalSampleResult.captured_messages: Optional[list[CapturedMessage]]` (`peer-deps-v01/proposal.md:42`) implies *per-sample* capture, but the contextvar approach assigns by enclosing context, not by sample. The spec is silent on this. The user running `peer eval --concurrency 10 --capture-messages` will get 10 sets of messages interleaved into the wrong samples on day one.

**Block:** specify the threading model. Either capture must be per-task-local (via a `ContextVar` set inside `_eval_sample`), or the runner must serialize capture, or the docs must explicitly state "capture+concurrency are mutually exclusive."

### 1.3 `peer-deps-v01` Decision 12 ("back-compat absorbed into default PeerDeps") contradicts the v01 spec for the existing test surface

`peer-deps-v01/design.md:226-234` says legacy `Agent(model=..., team_conventions=...).review(pr_url)` keeps working via `_default_deps`. But `src/peer/agent.py:21-30`'s `_select_reviewer` does `if model.startswith("claude"): return ClaudeReviewer(model=model, system_prompt=system_prompt)`. The new code in tasks 4.1/4.2 changes that signature to `_select_reviewer(provider, model_id)` and tasks 4.3 changes `ClaudeReviewer(model=model_id, …)` — so `model` is now the bare model id without prefix.

But the back-compat for legacy bare names emits a DeprecationWarning and infers a provider. Fine — *for the constructor*. The problem is that downstream code in `src/peer/eval/runner.py:154-169` (`_infer_agent_config`) currently reads `getattr(reviewer, "model", None)` and serializes that to `AgentConfig.model`. After this change, the reviewer instance's `.model` will be the *bare* model id ("claude-sonnet-4-6") regardless of whether the user passed "anthropic:claude-sonnet-4-6". This silently changes the canonical form in every saved EvalReport. Reports comparing pre/post change can't be diffed because `agent_config.model` won't round-trip back.

`peer-deps-v01` Task 4.3 doesn't acknowledge this. There's no `Reviewer.canonical_model_id` or similar.

**Block:** decide whether `Reviewer.model` is provider-prefixed or bare, and update `_infer_agent_config` and all eval-report fixtures accordingly. Otherwise A/B diffs across this boundary become meaningless.

### 1.4 `benchmark-v01` makes an empirically unverified assumption that breaks the whole bug-detection methodology

`benchmark-v01/design.md:60` and spec.md:33: *"the bug judge runs once per (bug, peer-comment) pair where the peer comment's path overlaps any `BugLocation.path` AND its line is within `[start_line - 10, end_line + 10]`."*

This silently assumes the *peer comment's line numbers refer to the same file revision as the bug location*. But `BugSample.commit_sha` (spec.md:5) is "the buggy commit" — i.e., the commit *before* the fix. `Agent.review(pr_url)` calls `gather(pr_url)` (`src/peer/agent.py:106`) which fetches a PR's diff via `gh api`. The runner Task 4.2 (`benchmark-v01/tasks.md:23`) is hand-wavy: *"build a synthetic PR URL pointing at the bug's commit (or use `repo_url + "/commit/" + commit_sha`)"*. A commit URL is *not* a PR URL; `gather` will fail. There is no design for "review a single commit" vs "review a PR." And even if you fix that, "the bug exists at line N of file F in commit X" tells you nothing about line numbers in the diff of the PR that *introduced* the bug — the diff's `new_start` may or may not coincide with the bug's `start_line`.

This is a load-bearing design hole. With it left open, every Macroscope number peer publishes is meaningless.

**Block:** the benchmark spec needs to nail down (a) the unit-of-review (PR-introducing-bug vs commit-containing-bug vs file-at-revision), (b) the line-number coordinate system, (c) what `Agent.run` accepts in non-PR mode. Without it, Task 4.2 is unimplementable.

### 1.5 `eval-v02`'s `RationaleGrounding` doesn't address the failure mode it claims to address

`eval-v02/proposal.md:16`: *"Adding it via a new `RationaleGrounding` LLMJudge would have caught the hallucinated-line-number issue in PR 7677 directly."*

But — per `data/eval_runs/diagnosis_reference_v1.md:39-46`, the PR 7677 case is the *opposite*: peer **correctly** cited line 432 with `==` reasoning; the analysis note that "ground truth was line 444" was the analyst's confirmation that peer was right (the substring check is at 444, peer commented at 432 with rationale). There is no actual hallucinated line number in the v1 dataset. The cited motivating example does not exist. `RationaleGrounding`'s claimed cost ($0.001 per peer comment × 90 = $0.09, design.md:178) is small, but the rubric (design.md:140-148) asks "are the cited line numbers correct?" — that requires the judge to know what's at line N of the file, but the judge only sees the diff hunk (Decision 7, design.md:152: `include_input = True   # judge needs to see the diff hunk`). For a peer comment that references "consistent with X" in unchanged code outside the hunk, the judge cannot verify the claim.

This is empirically untestable on the existing dataset (no hallucinations to catch). It's a metric solving a phantom problem, costing 90 extra LLM calls per run, biased toward false positives (judge will say "ungrounded" any time peer cites code outside the diff hunk, even when correct).

**Block:** either find a real positive example in the existing eval runs, or downgrade `RationaleGrounding` to optional / off-by-default.

---

## Section 2 — Should be acknowledged but not necessarily blocked

### 2.1 `peer-deps-v01`'s `ALLOW_LLM_CALLS = True` module flag is global mutable state and a footgun

`peer-deps-v01/design.md:111-124`. The pattern is *exactly* the pattern Pydantic AI itself uses (their doc: `ALLOW_MODEL_REQUESTS = False`). But on pytest-xdist the flag is per-worker; if a fixture sets it `False` for one worker and another spawns a subprocess for an integration test, the subprocess has the default `True` and burns API credits. The risk note (design.md:239: *"surprising to find when debugging"*) understates this. The author should acknowledge: under `pytest-xdist -n auto` or any subprocess fork, the flag does not propagate. Document a worker-fixture pattern in `conftest.py` examples.

### 2.2 `peer-deps-v01`'s validation retries claim a benefit they probably can't show

design.md:191-194: *"unbounded could spin on a stubborn LLM"* and Task 13.3 says *"Sanity check: re-run with `Agent(retries={"output": 2})` on at least one PR — verify retry path actually exercises (force a bad-line via a TestReviewer wrapper to confirm the retry-then-fix flow works end-to-end)."* — i.e., the verification is for a `TestReviewer` that's been programmed to fail, not for a real LLM. No data shows that real Sonnet 4.6 produces bad-line/path comments at a rate where 1 retry meaningfully recovers them. Per `data/eval_runs/diagnosis_reference_v1.md` aggregates, validation drops are not in the top failure modes — gold over-classification (~38%) and missing context (~45% peer misses, ~11% peer-couldn't-see) dominate. Retries are a speculative cost (worst-case +100% LLM tokens per review for a problem that may not exist). Should be opt-in (default `retries={"output": 0}`).

### 2.3 `eval-v02`'s `MetricSpec` round-trip for case-specific evaluators is going to be unreliable

spec.md:132-144: *"each evaluator SHALL be written as a `MetricSpec` … on load, the framework SHALL instantiate the metric via `_resolve_metric_spec(spec)` which imports the named class and applies `**spec.args`."* — i.e., `eval(import_string)(**dict_args)`. Any user metric carrying a non-JSON-serializable arg (a function reference, a regex pattern, an anthropic.Client) cannot round-trip. For an `LLMJudge` configured with `model="anthropic:claude-haiku-..."` it's fine, but for a customer's `MyMetric(scorer=lambda x: ...)`, round-trip silently fails or raises. The spec needs an explicit scenario: "MetricSpec rejects non-serializable args with a clear error at *save* time, not load time." (Currently scenario only covers the load-time failure.)

### 2.4 `peer-config-v01`'s "first-matching-glob wins" is the wrong default for `severity_floor`/`severity_cap`

design.md:62-63 picks first-match-wins. But for severity bounds users almost certainly want *the most-restrictive applicable rule* — if `tests/**` caps at `minor` and `**` floors at `important`, a `tests/test_security.py` change should be capped at `minor`, but if both rules apply *and the more-specific one is listed second*, the floor wins and security tests get bumped to `important`. The user's mental model is "more specific wins." This will produce real bugs.

Mitigation in the spec: document loudly that *order matters; specific first*. But better: split rule-matching into "conventions" (first-match) and "severity bounds" (most-restrictive intersection). Acknowledge or revise.

### 2.5 `peer-config-v01` `ignore.generated_code` defaults but the spec doesn't say what the defaults are

spec.md:138-159: "the latter pre-populated with vendored PR-Agent patterns when no user override is provided." But what patterns? `*_pb2.py` is in scenario 150. Are protobuf, OpenAPI, GraphQL, etc. patterns all in there? The default is load-bearing because it changes peer's behavior on every PR with any generated file. A future user who has a hand-written `something_pb2.py` will silently have peer skip it.

The spec needs the literal default-patterns list (or a pointer to where it lives in source). And a scenario: "Default generated_code patterns are documented and stable across releases."

### 2.6 `linter-context-v01` Token-budget ordering will starve linter findings on large PRs

design.md:75-83 and spec.md:82-94: drop order is `related_tests` → `linter_findings` (lowest severity first) → `call_sites`. Decision 5 says: *"a PR with 50 lint findings, that's ~2500 tokens — meaningful but tractable."* But on a *legacy* codebase that violates ruff in 1000 places (typical when first adopting peer), Tasks 3.4 caps findings_per_file at 50 — still, 50 modified files × 50 findings × 30 tokens = 75k tokens, well above the 30k budget. The budget will drop linter findings *before call_sites*, leaving the agent without the most actionable signal (linter caught it, just tell me). This contradicts Decision 6 ("System prompt directs agent to consult linter findings"). Acknowledge: the priority is wrong on first-adoption PRs.

### 2.7 `patch-suggestions-v01` validation-on-suggestion is purely length-based and will warn on every well-formed suggestion that adds lines

spec.md:36-47: warning fires *"when the suggestion has more newlines than the surrounding hunk has new-file lines."* A legitimate small fix that adds 3 lines to a 1-line hunk is *correct* — GitHub's `\`\`\`suggestion` semantics allow replacing N lines with M lines. The heuristic conflates "suggestion length" with "number of replacement lines." This warning will fire on most well-formed suggestions and train users to ignore the WARNING channel. Acknowledge: heuristic is weak; suggest dropping it or rewriting in terms of GitHub's suggestion semantics.

### 2.8 `eval-v02`'s `SkipLater` exception is the wrong abstraction

design.md:126-134. The semantics ("raise an exception to communicate normal control flow to the runner") are a Pythonic anti-pattern. Worse: there's no way for a *lower-priority* metric to skip a *specific* higher-priority metric — it's all-or-nothing. Realistic use case ("output is malformed → skip the *expensive* LLMJudge but still record the deterministic checks") needs metric-level granularity. Should be a `MetricResult.skip_higher: list[str]` field or a return-value-based signal, not an exception. Acknowledge.

### 2.9 `eval-metrics-v01` `MeanPerPRRecall` (the renamed metric) keeps the same JSON key `mean_per_pr_recall` but old reports have `defect_recall` → A/B diffs are silently broken

`eval-metrics-v01` Task 4.2 says: *"Update `render_diff` to handle metrics present in B but missing in A — render `(not in baseline) → <value>` instead of raising."* Per spec.md:48-50, `DefectRecall` is "renamed" to `MeanPerPRRecall` with the new name `mean_per_pr_recall`. So existing reports (`data/eval_runs/reference_v2_sonnet46.json`) have `defect_recall` and new reports have `mean_per_pr_recall` — same numerical concept, different key. Diff will say `(not in baseline) → 0.026` instead of showing the actual delta. The diff renderer should map deprecated-key → canonical-key. Currently doesn't.

### 2.10 `benchmark-v01` `published_baselines` is hardcoded in source as a moving target

design.md:81-84 and tasks.md:30-33: baselines in `src/peer/benchmark/baselines.py`. These numbers change as vendors update their tools. Six months from now the table will be stale and misleading. Either (a) tag baselines with a date and require explicit re-fetch every release, (b) move them out of source into a versioned JSON file that surfaces "last verified: <date>" in the CLI output, or (c) accept that they'll drift. Doc the drift policy.

---

## Section 3 — Cross-cutting concerns

### 3.1 Three changes ("PeerDeps integration") get added as a section of three different proposals (`peer-config-v01`, `linter-context-v01`, `patch-suggestions-v01`) without any of them being marked as depending on `peer-deps-v01` in their `.openspec.yaml` ordering

`peer-config-v01/proposal.md:21` says: *"PeerConfig is set on `PeerDeps.config` rather than on `Agent.__init__` directly (per `peer-deps-v01`)."* Similar in `linter-context-v01/proposal.md:16` and `patch-suggestions-v01/proposal.md:18`. But the tasks.md for these changes don't show "Depends on peer-deps-v01" anywhere. If `peer-deps-v01` slips, do the others land first with the old Agent kwarg shape and a TODO to migrate later? Or do they block? Need an explicit dependency graph (probably in `openspec/changes/README.md`).

### 3.2 The retry mechanism is described in three different specs with three different verification depths

- `peer-deps-v01/spec.md:48-67` defines validation retries.
- `patch-suggestions-v01/spec.md:107-114` adds retry semantics for `end_line` validation.
- `patch-suggestions-v01/spec.md:116-124` adds retry semantics for `suggestion` misalignment.

Each one says "feed validation error back" but each has its own user-message format. Should be one canonical "validation retry request" template used by all of them. Otherwise the prompt-shape drifts across releases and the agent gets confused when multiple kinds of fixes are requested in one retry.

### 3.3 Three changes ship a new "default metric" (eval-metrics-v01: 3 new; patch-suggestions-v01: 2 new; eval-v02: 1 new) — the default metric list will be ~8 metrics, with ~5 of them LLM-judged

`patch-suggestions-v01/spec.md:135-142` puts the default at `[DetectionRate, CommentsPerPR, PrecisionPerSeverity, SuggestionRate, MeanPerPRRecall, NoveltyRate, SeverityCalibration]` (7); `eval-v02` adds RationaleGrounding (8). At 30 PRs × ~3 comments/PR × ~5 LLM-judged metrics-per-comment, a default eval run is ~450 judge calls. At Haiku pricing that's $0.45 — multiplied if MeanPerPRRecall + NoveltyRate use the same judge.

The "run eval after every change" pattern that the framework promotes becomes meaningfully expensive. There's no spec for "fast-default" vs "full-eval" metric profiles. Today's `peer eval` is the framework's fast iteration loop; after v0.2, it isn't.

### 3.4 Naming inconsistency: `PeerConfig.enabled_linters()` vs `PeerDeps.linters` vs Reviewer's `ctx.deps.linters`

`linter-context-v01/spec.md:121` and tasks.md 4.3: *"`PeerConfig.enabled_linters() -> list[Linter]` resolver"*; spec.md:135-150: *"`PeerDeps.linters`"*. Two different APIs for "the linters to run." A user expecting `cfg.linters` will get nothing; a user expecting `deps.linters` will get the explicit list but not the config-implied list. The resolution rule (spec scenario 148-150: explicit wins) is documented but the duality is itself the bug. Pick one accessor.

### 3.5 `benchmark-v01` requires `peer-deps-v01` AND `eval-v02`, but its spec.md:116-118 only mentions peer-deps

*"`BugBenchmarkRunner` SHALL accept ONE Agent (constructed once) and use `with agent.override(deps=deps_for_this_sample):`"* — needs `peer-deps-v01`. But `judge_bug_caught` (tasks.md 3.1) is "a single Haiku call per pair" — that's a hand-rolled LLM call, not a use of `eval-v02`'s `LLMJudge`. So benchmark-v01 deliberately re-invents what eval-v02 just designed. Should the benchmark use `LLMJudge(rubric="Did this reviewer catch the bug? CAUGHT/NOT_CAUGHT", ...)` instead? Worth a Decision section.

### 3.6 Five of eight changes claim Pydantic AI / Pydantic Evals influence without explaining why peer isn't just *using* Pydantic AI

Every "Why" section name-drops the design philosophy doc. The Non-Goals reject the dep ("would lock peer into PA's design + version + concept hierarchy", `peer-deps-v01/design.md:15`). But "lock peer into PA's design + concept hierarchy" is exactly what peer-deps-v01 *does* — `Agent`, `RunContext[T]`, `deps_type`, `agent.override`, `ALLOW_LLM_CALLS`, `capture_run_messages`, `retries={'output': N}`, provider:model strings. Same names, same semantics. The justification ("don't take the dep") doesn't survive the test of "we're going to maintain a parallel implementation forever." Worth being honest: either take the dep, or pick names + semantics that diverge enough to give peer its own identity. Pretending these are inspired-by rather than copied-from creates legal and credit risk.

### 3.7 Schema versioning isn't coordinated

- `peer-deps-v01` adds `EvalSampleResult.captured_messages` ("no schema bump"; proposal.md:42).
- `eval-metrics-v01` adds new metrics in `metric_values` (`design.md:75-77` says "stays at 1.0").
- `eval-v02` bumps to "2.0" (`design.md:160-167`).
- `benchmark-v01` introduces a *separate* schema with version "1.0" (`design.md:67-68`).
- `patch-suggestions-v01` extends Comment without bumping the schema.

If a user runs `peer eval` with v0.2 partially landed (`peer-deps-v01` merged but `eval-v02` not), they get a v1.0 report with a `captured_messages` field that's invalid against the strict `from_json` loader (`src/peer/eval/report.py:25-36`, which raises on any mismatch). The current `_from_json` doesn't do additive forward-compat. Either every change touching the schema needs an explicit version-coord plan, or the loader needs to be made permissive *first*. Right now it's brittle by accident.

---

## Section 4 — What's NOT in scope but probably should be

### 4.1 Reviewer-side rate limit / retry handling

Once `eval-v02` defaults concurrency=5 and `benchmark-v01` runs 118 reviews back-to-back, hitting Anthropic's per-minute rate limit becomes the default failure mode. There is no spec for "what happens when the API returns 429." `src/peer/reviewers.py:67-90` has no retry logic. The runner's `try/except Exception` (runner.py:219) just marks the sample as failed. Eight changes touching the eval surface, and none of them handles the most common production failure.

### 4.2 Empirical baselines for the new metrics

`eval-metrics-v01` ships `DetectionRate`, `CommentsPerPR`, `PrecisionPerSeverity` and re-runs the v2 dataset (Task 7.1). But there's no spec for "the expected numbers" — a user running on day one has no idea whether their 5% detection rate is acceptable or terrible. A README baseline table from the v2 reference run would set expectations.

### 4.3 Versioned + tagged reference dataset

`dataset/reference/django_pydantic_v2.jsonl` is the de facto reference. There's no schema version on it. If `peer-config-v01` adds an `ignore` section that's auto-applied during `peer eval`, the reference dataset's results change without anyone editing the dataset. Reference data should be tagged with which framework version produced it.

### 4.4 Per-call cost tracking inside `Agent.run`, not just at the EvalRunner layer

`peer-deps-v01`'s validation retries (design.md:241) increase cost. The retry budget is "1 by default" — at scale, that's a hidden ~+30-50% LLM spend. `Review.usage` currently aggregates input/output tokens but doesn't break out retry vs first-call cost. A user diffing two EvalReports won't see that the cost increase is from retries.

### 4.5 Concurrency story for `Agent.override` + asyncio

`peer-deps-v01` Task 7.5: *"Verify re-entrance: nested overrides work; exception inside inner block restores both levels."* But the stack is per-instance (`_override_stack: list[dict]`). Under `eval-v02`'s concurrent `_eval_sample`, two coroutines on the same Agent (which the benchmark spec mandates: "ONE Agent constructed once") can interleave overrides on the same `_override_stack`. The spec needs "override is thread-safe / asyncio-safe" or "override must not be used inside async contexts that share the agent."

### 4.6 Dataset-level deduplication of LLMJudge calls

`eval-v02` design.md:103-109 wires `judge_match` through `LLMJudge`. `RationaleGrounding` is *another* LLMJudge with a different rubric. On the same (peer comment, gold defect) pair, the framework will issue 2+ Haiku calls. Caching by `(rubric, prompt_hash)` is obvious but absent. For a 30-PR run that adds ~$0.20 of needless cost; for `benchmark-v01`'s 118-bug run that adds real money.

---

## Section 5 — What IS in scope but probably shouldn't be

### 5.1 `eval-v02` `pass_rate` is dead weight in v0.2

design.md:111-122 and spec.md:69-82. None of the v0.2 default metrics return `bool` — DetectionRate is float, CommentsPerPR is float, PrecisionPerSeverity is dict, RationaleGrounding is float. Per spec.md:78-81: *"Pass rate is None when no boolean evaluators"*. So `pass_rate` will always be `None` for the default metric set, rendered as "n/a" in the CLI. It's a feature for hypothetical user metrics. Don't ship until at least one boolean default lands, OR ship as a planned doc placeholder.

### 5.2 `peer-deps-v01` `instructions` field is a parallel to `system_prompt` whose semantic difference is undocumented in peer

design.md:67-68: *"`system_prompt`: Optional[str] = None, # static prompt (back-compat); `instructions`: Optional[str] = None, # regenerated per-run (Pydantic-AI pattern)"*. peer has no notion of multi-turn history that would distinguish "static prompt" vs "regenerated per-run." Adding `instructions` as a parallel field that does the same thing as `system_prompt` but conceptually "later" introduces user confusion with no benefit. Drop until peer actually has multi-turn / message-history.

### 5.3 `linter-context-v01` ships MypyLinter as a default impl when it's disabled by default

`linter-context-v01/design.md:112`: *"mypy is disabled in the default `peer-config-v01` if not explicitly enabled"*. And mypy is famously slow + needs project-specific config + needs a venv with deps. Shipping a default MypyLinter implementation that's not enabled by default and won't work without `mypy --install-types` + `pyproject.toml` config + the right `python_version` setting is shipping a footgun. Either include it in `examples/` or wait for a user to ask.

### 5.4 `peer-deps-v01` `RunContext.metadata: dict` is a typed escape hatch that contradicts the framework's "type-safe everything" Pydantic AI inheritance

design.md:46. A `dict` is exactly what RunContext is supposed to replace. If users need adaptive metadata (per-attempt customization, etc.), give them a typed `attempt_metadata: AttemptMetadata` Pydantic model. The current spec lets users put anything in `.metadata` and lose type safety the moment they do — the same trap Pydantic AI exists to avoid. Drop `metadata` from the v0.1 RunContext.

### 5.5 `patch-suggestions-v01` `IssueHeaderDistribution` is informational and wouldn't change any decision

spec.md:127-133: *"Returns a dict aggregate of how many peer comments fall under each `issue_header` value."* `metric_values["issue_header_distribution"]` is None. It's only in `metric_details`. So it's a logged fact, not a metric. Doesn't belong as an EvalMetric class; should be a derived stat in `render_summary`.

### 5.6 `peer-config-v01` `extra_instructions` overlaps with `team_conventions` overlaps with `system_prompt`

The current shape is three ways to inject text into the system prompt:
1. `Agent.system_prompt` (replace whole)
2. `Agent.team_conventions` (legacy single-conventions blob)
3. `PeerConfig.agent.extra_instructions` (short ad-hoc)
4. `PeerConfig.rules[*].conventions_file` (per-path)

This is four ways. Users will pick wrong, mix them, and ask why their setting is being ignored. Pick two (system_prompt = full override; per-path conventions = path-scoped additions) and deprecate the rest.

---

## Section 6 — Devil's advocate strategic challenge

> **In 6 months, when v0.2 is shipped, what would the author most regret?**

**The most likely regret: peer turns into a third-rate Pydantic AI clone with an eval framework attached, instead of being the eval-first framework.**

All 8 changes are catch-up moves. `peer-deps-v01` is a Pydantic AI re-implementation; `eval-v02` is a Pydantic Evals re-implementation; `linter-context-v01` mimics CodeRabbit; `peer-config-v01` mimics CodeRabbit's `.coderabbit.yaml`; `patch-suggestions-v01` mimics CodeRabbit's suggestion blocks; `benchmark-v01` adopts the Macroscope benchmark and promises to publish numbers that will be lower than Macroscope's. Even `prompt-quality-v01` is "copy PR-Agent's prompt language."

The original peer differentiator per `docs/framework_overview.md` was the 8-Protocol extension model + the eval-driven iteration loop. After v0.2, those Protocols (Reviewer, EvalMetric, etc.) gain optional `ctx` parameters and `client=` kwargs but stay mostly intact — *and the new sources of value are all borrowed*. A user evaluating "should I use peer or just use Pydantic AI + write a Reviewer protocol?" will increasingly choose Pydantic AI for the support / ecosystem / docs / first-class status.

The benchmark trap (`benchmark-v01`) is the sharpest cut. The framework will run on Macroscope. It will get a number. The number will be lower than Macroscope's 48% or CodeRabbit's 46%. Per design.md:131-134, this is "mitigated" by docs framing — *"peer is the framework; the number is the default-configuration baseline a user starts from and iterates upward."* But the headline number is what users see. A 30% detection rate posted next to CodeRabbit's 46% is a worse marketing position than no number at all. The benchmark capability is a credibility bet that — if the number is bad — backfires.

**Six months in, the regrets in order of severity:**

1. **The benchmark number didn't move the conversation in our favor.** It cost real money to run, real attention to interpret, and yielded a baseline that needed defensive framing.

2. **eval-v02 + peer-deps-v01 together blow up the eval surface area.** What was a tight 5-Protocol contract becomes a 7+-Protocol contract with optional ctx, async semantics, configurable LLMJudge inheritance hierarchies, layered priority + SkipLater control flow. The "8 Protocols, structurally typed" pitch becomes hard to explain in 30 seconds.

3. **Validation retries (peer-deps-v01) doubled some users' API bill on the first day they upgraded** — the default of 1 retry per validation failure is benign on small datasets but expensive on production-scale ones, and the cost surfaces only in aggregate.

4. **No one is asking for `extra_instructions` + `team_conventions` + per-path `conventions_file` + `system_prompt`** — users want one knob and pick the wrong one of the four.

5. **`RationaleGrounding` ships at 90 Haiku calls per default run, catches no real-world hallucinations because peer rarely hallucinates per the v1 diagnosis (0% in the sample)**, and the metric is silently expensive.

6. **Pydantic AI ships a 1.0** and the maintenance burden of peer's parallel `PeerDeps`/`RunContext`/`override`/etc. starts feeling silly. A v0.3 `peer-pydantic-ai-integration-v01` change becomes urgent and gets blocked because we have parallel concepts everywhere.

The author's hardest call: **does peer remain a framework, or accept that it's becoming a "production AI PR review tool that happens to be open source"?** All 8 changes drift toward the latter. If that's intentional, the framework Protocols should be deprecated. If not, several of these features (the LLMJudge subclasses, the published-baselines comparison, the auto-detected `.peer.yaml`) belong in a `peer-tools` package, not in `peer` itself.

---

## One-paragraph triage summary

Five blockers exist before any of this lands: (1) the `EvalMetric.score(..., client=)` signature is silently broken by `eval-v02` with no back-compat scenario; (2) `capture_run_messages` + the new async runner share a contextvar across concurrent samples and will interleave captures into wrong samples on day one of `peer eval --capture-messages --concurrency 5`; (3) `peer-deps-v01`'s provider:model parsing leaves `Reviewer.model` in a bare/prefixed form that `_infer_agent_config` (eval/runner.py:154) reads into every EvalReport, silently breaking pre/post diff; (4) `benchmark-v01`'s coordinate system between "bug at line N in commit X" and "peer comment at line M in PR diff Y" is undefined, making `Task 4.2` unimplementable; (5) `eval-v02`'s `RationaleGrounding` is sold as catching the PR 7677 hallucinated-line issue but that issue doesn't exist in the v1 diagnosis. Cross-cutting: schema versioning isn't coordinated across the five changes that touch it, the default metric set after v0.2 makes `peer eval` materially expensive (~$0.45+ per default run), and the three "ways to inject conventions text" already overlap with what `peer-config-v01` adds making it four. Strategic: the v0.2 stack is almost entirely catch-up moves — pure Pydantic AI / Pydantic Evals re-implementations, plus CodeRabbit feature parity, plus a Macroscope benchmark whose number will be worse than the published baselines and need defensive framing. If the eval-first iteration loop is still the differentiator, several of these features (`benchmark-v01`, `linter-context-v01`'s MypyLinter default, the LLMJudge subclass hierarchy) are dilutive of that pitch and could ship in a separate `peer-tools` extension instead.
