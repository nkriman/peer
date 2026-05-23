## Context

`agent-v01` shipped the agent surface. This change ships the eval surface that closes the framework's iteration loop: golden dataset → eval framework → framework changes → re-eval.

The naming-of-the-game is **framework, not product**. We expect every team adopting `peer` to plug in their own variants of several pieces — their own classifier, their own taxonomy of "what counts as a defect worth flagging", their own gold-sample source (some teams will pull from GitHub, others from Jira tickets, others from internal review databases), their own custom metrics. The job of v0.1 is to define the right extension points (Protocols), ship "good enough" defaults so OSS users get value with zero config, and provide a credibility-anchor reference dataset they can run against on day one.

## Goals / Non-Goals

**Goals:**
- Eight Protocols define the eval pipeline; each has exactly one default implementation that's "good enough" for OSS Python repos.
- `EvalRunner` composes those Protocols and produces a versioned `EvalReport`.
- The dataset-curation workflow is opinionated enough that a developer can run `peer dataset add <pr_url>` and get a usable, classified, spot-checkable sample with no extra effort.
- A unified `peer` CLI replaces the per-script entry points.
- The framework is set up so a team can swap any single piece (e.g., custom classifier) without touching the others.
- A small reference dataset (~30 samples) ships so new users can run the whole flow immediately.
- A documented path from this change to a benchmark-vs-commercial credibility result, even though the actual benchmark run is `benchmark-v01`.

**Non-Goals:**
- Implementing every imaginable default (e.g., a Jira `RawSampleSource`, a `peer.toml` config loader, deepeval-as-default). Each is enabled by the Protocols but kept out of v0.1.
- A web UI for browsing eval results.
- Continuous-eval / regression-detection / CI integration. The data shapes support it; the integration ships in a future change.
- Actually achieving SOTA-on-a-public-benchmark in this change. That's `benchmark-v01`. This change ships the *measurement instrument* that makes the benchmark run possible.

## Decisions

### 1. Eight extension-point Protocols, not classes

The eval pipeline is defined by eight Python Protocols. Each has a default implementation. Users override by passing their own implementation into `EvalRunner` or the relevant constructor — no subclassing required.

| # | Protocol | Default impl | Default's scope |
|---|---|---|---|
| 1 | `Reviewer` (from `agent-v01`) | `ClaudeReviewer`, `OpenAIReviewer` | already shipped |
| 2 | `RawSampleSource` | `GitHubInlineCommentSource` | pulls PR + bot-filtered inline review comments via `gh api` |
| 3 | `CommentClassifier` | `LLMCommentClassifier` | Haiku 4.5 with the default Taxonomy; one call per raw comment |
| 4 | `Taxonomy` | `DefaultTaxonomy` (8 categories × 4 severities) | see Decision 4 |
| 5 | `EnrichmentStep` | `NoEnrichment` (passthrough) | opt-in upgrades (post-merge bugfix correlation, LLM-oracle) live as named non-default impls |
| 6 | `GoldSampleStorage` | `JSONLStorage` | one file per dataset, line-delimited GoldSample records |
| 7 | `EvalMetric` | `DefectRecall`, `NoveltyRate`, `SeverityCalibration` | see Decision 7 |
| 8 | `EvalReport` | `JSONEvalReport` | JSON file + CLI table renderer + A/B diff render |

**Why Protocols, not ABCs:** matches the existing `Reviewer` Protocol pattern from `agent-v01`. Structural typing means a user's custom class doesn't need to import or inherit from peer — it just needs the right method signatures. This is the framework's contract; ABCs would be unnecessary ceremony.

### 2. Defaults are "good enough", not perfect

Each default implementation is chosen to be sensible and usable, not state-of-the-art. The bar is "a developer running `peer eval` on the reference dataset gets numbers that mean something." Sharper / more accurate / better-tuned versions are user-supplied or future-change.

**Why:** the framework's value is the *shape*, not the defaults. If the defaults were optimized, every user customizing them would feel like they were degrading the system. With "good enough" defaults, users start from a working baseline and customize upward.

**Concretely:** `LLMCommentClassifier` uses Haiku 4.5 with a single prompt and no calibration / few-shot examples / chain-of-thought. It will misclassify some comments. That's acceptable for v0.1; users who care override it.

### 3. Bring-your-own-everything via constructor injection

No global configuration, no `peer.toml`, no environment-variable plumbing for the v0.1 framework surface. All customization happens in Python code:

```python
from peer.eval import EvalRunner
from peer.dataset import GitHubInlineCommentSource, LLMCommentClassifier

runner = EvalRunner(
    reviewer=my_custom_reviewer,
    dataset=load_from_jsonl("my_team_dataset.jsonl"),
    metrics=[DefectRecall(), MyTeamMetric()],
)
report = runner.run()
```

**Why:** Python code is more flexible than config files for the kinds of customization developers will want (custom Protocols are arbitrary code, not parameter-tuning). A `peer.toml` for parameter-level config can land in a future change once we see what parameters users actually want exposed.

### 4. Default Taxonomy: 8 categories × 4 severities

Categories (each raw comment classified into exactly one):

- `defect-correctness` — bug, logic error, broken behavior, regression risk
- `defect-security` — security or privacy concern
- `defect-performance` — perf concern with a concrete cost case
- `defect-api-design` — wrong layer / wrong abstraction / breaking API change
- `defect-test-gap` — change is untested or test coverage gap
- `defect-doc-gap` — change needs docs / docstrings missing / changelog missing
- `style-nit` — pure formatting, naming nit, ordering
- `discussion` — implementation Q&A, "looks good", "please review", clarification chatter, off-topic, approval

The first six categories are **defects** (kept in gold). `style-nit` is **kept but at nit severity only**. `discussion` is **dropped from gold**.

Severities: `critical / important / minor / nit` (same as the agent's output taxonomy — symmetric so eval mismatches are interpretable).

**Why this taxonomy:** broad enough to capture what real OSS PR reviews actually contain (validated against the 14-PR batch in `data/eval_runs/batch_14prs_sonnet46.json`), narrow enough to be classified reliably by an LLM in a single zero-shot call. Eight categories means the classifier rarely has to make a hard choice between similar options.

**Why "discussion" gets dropped:** that's the central bug in the MVP eval. ~80% of human inline comments on small PRs are conversational, not defect reports. A taxonomy that doesn't separate them produces nonsense hit rates.

**Override:** users pass a custom `Taxonomy` instance with their own category list, severity scale, and drop rules.

### 5. Enrichment is opt-in and conservative-by-default

The default `EnrichmentStep` is `NoEnrichment` (passthrough). Gold samples come solely from filtered human comments.

Named non-default enrichment impls live in `src/peer/dataset/enrichment.py`:

- `PostMergeBugfixCorrelation` — for PRs that introduced bugs later fixed in follow-up PRs, the follow-up's diff is converted into a "this should have been caught" defect on the original PR.
- `LLMOracleEnrichment` — run a strong model (Opus 4.7) over the PR with a "be a senior reviewer" prompt and add its high-confidence defects to gold, marked `source: llm_oracle`.

**Why off by default:** enrichment is judgmental and may introduce noise. A team's first gold dataset should reflect *their* humans' judgments; enrichment is the upgrade once they want to push past human-only.

**Why named impls in the same module:** discoverable, importable in one line, no extra package install.

### 6. JSONL on disk by default; storage is pluggable

Default `GoldSampleStorage` is `JSONLStorage(path)`. One `.jsonl` file = one dataset. Each line is a serialized `GoldSample` record (schema in `specs/dataset-curation/spec.md`). Append-only is the common case; the storage Protocol also exposes load / delete operations.

**Why JSONL:**
- Inspectable in any text editor / `jq` / `head` / git diff
- Append-only friendly
- Trivially version-controllable
- Matches the existing `curate.py` output format from agent-v00

**Override path:** users with bigger datasets / multi-user editing needs / cloud-shared datasets implement `SQLiteStorage`, `S3Storage`, etc. against the same Protocol.

### 7. Default metrics: DefectRecall, NoveltyRate, SeverityCalibration

Three default metrics. Each is one `EvalMetric` Protocol implementation. All three run by default.

- **`DefectRecall`** — of the defects in gold, what fraction did the reviewer flag? (Path equality + same-line-or-adjacent + judge-LLM semantic match.) Per-severity breakdown included.
- **`NoveltyRate`** — what fraction of the reviewer's comments did NOT match any gold defect? Important *signal*, not a "false positive rate" — novel comments may be real defects gold missed. Always reported alongside `DefectRecall` to give the right shape.
- **`SeverityCalibration`** — when the reviewer flagged a gold defect, how close was its severity to gold's? Reports mean signed delta + confusion matrix.

**Why these three:**
- `DefectRecall` is the headline number a team cares about.
- `NoveltyRate` is the warning light — high novelty without high recall means the reviewer is hallucinating; high novelty with high recall might mean it's catching things humans missed.
- `SeverityCalibration` catches the under/over-severing pattern empirically observed (e.g., PR 7528 in Slice 1).

**What's deliberately NOT a default metric:** a single "quality score" that compresses everything. False precision; users should look at the trio together.

### 8. EvalReport: JSON + CLI table + A/B diff

`EvalReport` is JSON-serializable with a stable schema (versioned via `report_schema_version` field). Default renderer prints a tabular CLI summary. A second renderer (`render_diff(report_a, report_b)`) produces a column-wise diff for A/B comparison.

Each report carries: `run_id` (UUID), `timestamp`, `agent_config` (model name, prompt hash), `dataset_path`, per-sample results, aggregate metrics, `cost` (USD estimate), `latency` (per-sample p50/p95). Reproducibility info (peer version, agent-v01 spec hash if available) included.

**Why a stable schema:** so users can `peer eval` weekly and store reports in git for trend tracking, without rewriting analysis tooling each release.

### 9. Cost and latency are first-class

Every `EvalReport` includes cost (USD estimate, computed from `Review.usage` × per-token pricing) and latency (per-sample wall-clock). Tracked so users can A/B comparing prompt changes don't only optimize quality and forget the bill.

**Why:** the "I improved recall by 5pp but doubled cost" trade-off is the most common eval result in practice. Hiding cost makes that invisible.

### 10. Unified `peer` CLI via argparse subparsers

Single entry point `peer`. Subparsers:

- `peer review <pr_url>` — existing single-PR review (alias of `python -m peer.review` for back-compat).
- `peer eval --dataset PATH [--baseline RUN_ID] [--out PATH]` — run the configured eval.
- `peer dataset add <pr_url> [--auto-accept | --interactive]` — fetch, classify, optionally human-review, store.
- `peer dataset list [--dataset PATH]` — show what's in a dataset.
- `peer dataset show <pr_url> [--dataset PATH]` — full record for one sample.

**Why subparsers:** standard Python pattern, no extra deps, scales to more subcommands cleanly. `click` / `typer` rejected for v0.1 per the scope research — argparse is fine.

**Back-compat:** `python -m peer.review <pr_url>` stays as a thin forwarder to `peer review` for users with existing scripts.

### 11. Single package, single pip install

`pip install peer` brings everything: agent, eval, dataset, CLI. Internal subpackages (`peer.eval`, `peer.dataset`) have clean module boundaries — no cross-imports back to `peer.agent` from `peer.eval` for example — so a future `pip install peer-core / peer-eval` split is trivial if user demand ever justifies it.

**Why not split now:** we have zero users. Splits create version-skew pain immediately and pay off only at scale. Designing-for-future-split costs zero in code organization; *shipping* the split costs ongoing release coordination.

### 12. Reference dataset ships in-repo

A small reference dataset (~30 hand-spot-checked samples drawn from the 14-PR Django + Pydantic batch + ~16 more) lives at `dataset/reference/django_pydantic_v1.jsonl`. New users run `peer eval --dataset dataset/reference/django_pydantic_v1.jsonl` to see the whole flow work without doing any curation.

The accompanying `dataset/reference/CURATION_NOTES.md` documents the curation methodology: how each raw comment was classified, which were spot-checked, what was kept, what was dropped. This doubles as the worked-example for the framework's documented dataset-curation workflow.

**Why ship it:** "framework with no demo dataset" is the same friction problem as "model with no demo input." Newcomers need a one-command path to seeing the system work end-to-end.

**Why hand-spot-check:** see Decision 13 — the dataset is small enough that human review of every sample is feasible and elevates its credibility above LLM-only curation. We're not publishing it as research; we just need it to be defensibly clean.

### 13. Curation workflow: classify, optionally enrich, spot-check, store

`peer dataset add <pr_url>` runs:

1. Fetch raw `(PR, comments)` via configured `RawSampleSource`.
2. Run `CommentClassifier` on each raw comment.
3. Run configured `EnrichmentStep` (default: pass-through).
4. Print proposed `GoldSample` for human review (with `--interactive`, default).
5. On accept, store via configured `GoldSampleStorage`.

`--auto-accept` skips step 4 for batch ingestion. Recommendation: use `--interactive` for the first N samples to build trust, then `--auto-accept` for the long tail with `peer dataset list --show-classifications` providing a sanity-check view.

**Why interactive by default:** the framework's intended use is iterative dataset building, not turnkey ingestion. The spot-check is the most important quality lever; making it default-on signals that.

### 14. SOTA-credibility comes from `benchmark-v01`, enabled by this change

The framework's credibility claim — "build AI PR reviewers competitive with commercial baselines" — gets *demonstrated* in a future `benchmark-v01` change that:

- Builds commercial-adapter `Reviewer` implementations (`CodeRabbitReviewer`, `GreptileReviewer`, `CursorReviewer` — each BYO API key) using the `agent-v01` Reviewer Protocol.
- Curates a larger reference dataset (~200 samples) across more repos / languages.
- Runs the comparison via this change's `EvalRunner`.
- Publishes the report.

This change makes that possible by shipping the measurement instrument. Doing the comparison itself is properly its own change so it gets its own review and its own design space (which commercial reviewers, which repos, what's the dataset license story, what's the comparison methodology).

## Risks / Trade-offs

- **[Risk]** "Good enough" defaults can be embarrassing if reviewed in isolation ("the classifier mis-categorized this comment"). **Mitigation:** documentation up front that defaults are baselines, not optima; per-default `Limitations:` section in docstrings; reference dataset includes the human spot-check log so misclassifications are visible.
- **[Risk]** Eight Protocols is a lot of surface area for users to learn. **Mitigation:** the default-everything path is one constructor call (`EvalRunner(reviewer=Agent(model='...').reviewer)`). Users only learn the Protocols when they want to customize.
- **[Risk]** LLM classifier cost compounds: 14-PR batch had ~50 raw comments → 50 Haiku calls just to classify. **Mitigation:** Haiku is cheap (~$0.001/call); cache classifications keyed on `(repo, comment_id)` so re-runs are free. Cache invalidation only on Taxonomy change.
- **[Risk]** Severity calibration metric assumes monotonic ordering of `critical>important>minor>nit`. Some teams use orthogonal severity dimensions (e.g., `(security, performance)` × `(blocker, suggestion)`). **Mitigation:** the metric is one Protocol impl; teams with different severity models implement their own.
- **[Risk]** Reference dataset bias — 30 samples from Django + Pydantic biases the framework's apparent calibration. **Mitigation:** docs make the bias explicit; users with different repos are expected to curate their own; `benchmark-v01` widens this materially.
- **[Risk]** JSONL storage doesn't scale past ~10k samples (no indexing). **Mitigation:** acceptable for v0.1; storage Protocol lets users plug in a DB; document the threshold.
- **[Risk]** `peer dataset add` interactive prompt blocks scripted workflows. **Mitigation:** `--auto-accept` flag; programmatic API (`Curator.add(pr_url, auto_accept=True)`) for batch use.
- **[Risk]** `NoveltyRate` is easily misread as "false positive rate." **Mitigation:** explicit docs + the CLI renderer labels it as "novel comments (may be real defects or noise)"; never the bare term "false positive."

## Open Questions

None blocking v0.1. The following are flagged for follow-on changes:

- Continuous-eval / CI integration shape (which CI hooks? what failure modes? regression-detection threshold UX) — deferred to a future change once users adopt the manual flow.
- `peer.toml` config file format — deferred until we know which parameters users want exposed declaratively vs in Python code.
- Multi-language defaults — eval is language-agnostic; the default `RawSampleSource` and the reference dataset are Python-only. Other languages can be added by users (`Reviewer` and `RawSampleSource` are language-blind) but a multi-language default config is its own design exercise.
