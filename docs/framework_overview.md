# Framework overview

> The architectural deep-dive on `peer`. Written for someone who's run
> `peer eval` once and now wants to know what's actually happening, what's
> pluggable, and how to swap in their own pieces.
>
> Companion to [`docs/scope_research.md`](scope_research.md) (what's in/out of
> scope) and [`docs/dataset_curation_guide.md`](dataset_curation_guide.md)
> (the methodology for building the gold dataset).

## The eval loop

`peer` is built around one iteration loop:

```
   curate gold dataset   ───►   run EvalRunner   ───►   read EvalReport
        ▲                                                      │
        │                                                      │
        └────────  change reviewer / prompt / context  ◄───────┘
```

Every framework feature exists to make one stage of this loop cheaper or sharper:

1. **Curate gold dataset.** `peer dataset add <pr_url>` fetches a PR's inline comments, runs an LLM classifier over each one, drops the conversational ones, and stores the rest as a normalized `GoldSample`. You spot-check interactively or batch with `--auto-accept`.
2. **Run EvalRunner.** `peer eval --dataset PATH` runs your configured `Reviewer` over every PR in the dataset, judges its comments against the gold defects (path proximity + judge-LLM semantic match), and produces a versioned `EvalReport` with metrics, cost, and latency.
3. **Read EvalReport.** Tabular CLI summary by default; A/B diff against a prior report with `--baseline`. The JSON is stable-schemaed so you can store reports in git for trend tracking.
4. **Change something.** Swap the reviewer (different model, different prompt, different context-gathering). Re-run. Diff the reports.

Everything in the framework is shaped to keep this loop fast. If a feature would make any single stage slower without improving signal, it doesn't ship.

## The eight extension-point Protocols

The whole framework surface — agent + eval + dataset — is defined by eight Python `Protocol`s. Each has exactly one default implementation. You override by passing your own implementation to the relevant constructor; no subclassing, no registration, no config.

Structural typing means your class doesn't have to import or inherit from peer. It just needs the right method signatures.

| # | Protocol | Default impl | Purpose | Override example |
|---|---|---|---|---|
| 1 | `Reviewer` | `ClaudeReviewer` | Given a PR `Context`, produce inline `Comment`s. | `Agent(model="gpt-4o")` (dispatches to your `OpenAIReviewer`) |
| 2 | `RawSampleSource` | `GitHubInlineCommentSource` | Fetch raw `(PR, comments)` from somewhere. | `JiraTicketSource()` for internal review databases |
| 3 | `CommentClassifier` | `LLMCommentClassifier` | Decide each raw comment's category + severity. | `RuleBasedClassifier(patterns={...})` for deterministic teams |
| 4 | `Taxonomy` | `DefaultTaxonomy` | Define category list + severity scale + drop rules. | `Taxonomy(categories=[...], drop_categories=["wontfix"], ...)` |
| 5 | `EnrichmentStep` | `NoEnrichment` | Augment gold with non-human-comment defects. | `PostMergeBugfixCorrelation()` or `LLMOracleEnrichment()` |
| 6 | `GoldSampleStorage` | `JSONLStorage` | Persist + load `GoldSample`s. | `SQLiteStorage(path)` once your dataset outgrows a flat file |
| 7 | `EvalMetric` | `DefectRecall`, `NoveltyRate`, `SeverityCalibration` | Compute one number (or one struct) from a finished eval. | Anything with `.name` and `.compute(results, dataset)` |
| 8 | `EvalReport` (renderer) | `JSONEvalReport` + `render_summary` / `render_diff` | Serialize + render the report. | `MarkdownReport()` or a custom renderer that pushes to Slack |

The full default-impl table lives in `openspec/changes/eval-v01/design.md` Decision 1. Each Protocol's contract is one method signature; each default impl ships in the obvious place (`peer.dataset.classifier`, `peer.eval.metrics`, etc.) and is one line to import.

### What each Protocol's default does

**`Reviewer` → `ClaudeReviewer`.** Single Anthropic API call against `claude-sonnet-4-6`, tool-use schema forcing structured `Comment` output. Defined in `src/peer/reviewers.py`. The `Agent` class wraps it with PR context-gathering, codebase-context extraction, and post-hoc validation that dropped comments fall inside diff hunks.

```python
from peer import Agent
agent = Agent(model="claude-opus-4-7", system_prompt_file=Path("my_prompt.txt"))
```

**`RawSampleSource` → `GitHubInlineCommentSource`.** Shells out to `gh api` for PR metadata + inline review comments, drops bot comments (`coderabbitai`, `dependabot`, etc.). Returns a `RawSample`. Defined in `src/peer/dataset/sources.py`.

```python
from peer.dataset import GitHubInlineCommentSource
source = GitHubInlineCommentSource()
raw = source.fetch("https://github.com/owner/repo/pull/N")
```

**`CommentClassifier` → `LLMCommentClassifier`.** Single Haiku 4.5 call per raw comment. Prompt is generated from the active `Taxonomy`, so a custom taxonomy "just works" without rewriting the classifier. Disk-cached at `~/.cache/peer/classifier_cache.jsonl` keyed on `(repo, comment_id, taxonomy.version)` — change the taxonomy and the cache invalidates itself. Defined in `src/peer/dataset/classifier.py`.

```python
from peer.dataset import LLMCommentClassifier
classifier = LLMCommentClassifier(model="claude-haiku-4-5-20251001")
```

**`Taxonomy` → `DefaultTaxonomy`.** 8 categories × 4 severities, see the table below. Defined in `src/peer/dataset/taxonomy.py`.

```python
from peer.dataset import Taxonomy, CategoryDef
my_tax = Taxonomy(
    categories=[CategoryDef(name="security", description="...", is_defect=True), ...],
    severities=["blocker", "warning"],
    drop_categories=["chitchat"],
    nit_only_categories=[],
    version="acme-v1",
)
```

**`EnrichmentStep` → `NoEnrichment`.** Passthrough. The opt-in alternatives (`PostMergeBugfixCorrelation`, `LLMOracleEnrichment`) live in the same module and are imported by name. Defined in `src/peer/dataset/enrichment.py`.

```python
from peer.dataset import PostMergeBugfixCorrelation
enrich = PostMergeBugfixCorrelation()
```

**`GoldSampleStorage` → `JSONLStorage`.** One JSONL file per dataset, one `GoldSample` per line. Append-only is the common case; the Protocol also exposes `load_all`, `find`, `delete`. Defined in `src/peer/dataset/storage.py`.

```python
from peer.dataset import JSONLStorage
storage = JSONLStorage("dataset/my_team.jsonl")
samples = storage.load_all()
```

**`EvalMetric` → `DefectRecall` / `NoveltyRate` / `SeverityCalibration`.** See the dedicated section below. Defined in `src/peer/eval/metrics.py`.

```python
from peer.eval import DefectRecall, NoveltyRate
metrics = [DefectRecall(), NoveltyRate()]
```

**`EvalReport` (renderer) → `JSONEvalReport`.** The `EvalReport` Pydantic model is the data; `render_summary(report)` and `render_diff(a, b)` are the renderers. The model is JSON-serializable with a stable schema (`REPORT_SCHEMA_VERSION`) so reports survive across `peer` versions. Defined in `src/peer/eval/types.py` and `src/peer/eval/report.py`.

```python
from peer.eval import render_summary, render_diff
print(render_summary(report))
print(render_diff(baseline, report))
```

## The two subpackages

`peer` is one package with two internal subpackages, designed so they could split into `peer-eval` and `peer-dataset` if user demand ever justifies it. For now there's one `pip install peer`.

### `peer.dataset` — curation pipeline

Everything that turns raw `(PR, comments)` into a curated `GoldSample`. Lays out as:

```
peer.dataset
├── sources.py      # RawSampleSource Protocol + GitHubInlineCommentSource
├── classifier.py   # CommentClassifier Protocol + LLMCommentClassifier
├── taxonomy.py     # Taxonomy class + DefaultTaxonomy instance
├── enrichment.py   # EnrichmentStep Protocol + 3 impls (NoEnrichment, PostMerge, LLMOracle)
├── storage.py      # GoldSampleStorage Protocol + JSONLStorage
├── curation.py     # Curator: composes the above into the dataset-add workflow
└── types.py        # RawSample, GoldSample, GoldDefect, Classification, etc.
```

Top-level entry is `peer.dataset.Curator`. It composes the four pluggable stages (source → classify → enrich → store) and drives the interactive spot-check loop:

```python
from peer.dataset import Curator, JSONLStorage

curator = Curator(storage=JSONLStorage("dataset/my_team.jsonl"))
sample = curator.add("https://github.com/owner/repo/pull/N", auto_accept=False)
```

### `peer.eval` — runner + metrics + reporting

Everything that runs a configured reviewer against a dataset and produces a report.

```
peer.eval
├── runner.py    # EvalRunner: composes (reviewer, dataset, metrics) into one run
├── metrics.py   # EvalMetric Protocol + DefectRecall / NoveltyRate / SeverityCalibration
├── judging.py   # LLM judge for semantic match between peer comments and gold defects
├── pricing.py   # USD cost estimation from Review.usage
├── report.py    # render_summary, render_diff, JSON I/O
└── types.py     # EvalReport, EvalSampleResult, EvalSummary, MetricResult, AgentConfig
```

Top-level entry is `peer.eval.EvalRunner`. It accepts anything with a `.review(pr_url) -> Review` method as its `reviewer` — the `Agent` class is the obvious implementation, but a custom adapter (e.g., a `CodeRabbitReviewer` that calls the CodeRabbit API) satisfies the same shape.

The two subpackages don't import each other except through `peer.dataset.types` (which `peer.eval` reads to know the `GoldSample` shape). No cycles, no shared state.

## The default Taxonomy

The taxonomy is the single most opinionated decision in v0.1. It's the bridge between "what humans wrote in a PR review" and "what counts as a defect a reviewer should catch."

8 categories × 4 severities. The first six categories are kept as defects with classifier-assigned severity. `style-nit` is kept but forced to `nit` severity. `discussion` is dropped from gold entirely — that's the central correction to the MVP eval's 13% hit rate problem (see [`docs/dataset_curation_guide.md`](dataset_curation_guide.md) for the long version).

| Category | Kept as gold? | Severity | What it covers |
|---|---|---|---|
| `defect-correctness` | yes | classifier | Bug, logic error, broken behavior, regression risk |
| `defect-security` | yes | classifier | Security or privacy concern |
| `defect-performance` | yes | classifier | Perf concern with a concrete cost case |
| `defect-api-design` | yes | classifier | Wrong layer / wrong abstraction / breaking API change |
| `defect-test-gap` | yes | classifier | Change is untested or test coverage gap |
| `defect-doc-gap` | yes | classifier | Change needs docs / docstrings missing / changelog missing |
| `style-nit` | yes | forced `nit` | Pure formatting, naming nit, ordering |
| `discussion` | **no** | n/a | Q&A, "looks good", clarification chatter, off-topic, approval |

Severities: `critical / important / minor / nit`. Same scale as the agent's output, on purpose — eval mismatches are interpretable because the two sides are using the same vocabulary.

Eight categories is broad enough to capture what real OSS PR reviews contain (validated against the 14-PR Django + Pydantic batch the framework was bootstrapped against) and narrow enough for a zero-shot LLM classifier to choose reliably in one Haiku call.

To override: construct your own `Taxonomy(categories=..., severities=..., drop_categories=..., nit_only_categories=..., version=...)` and pass it into `LLMCommentClassifier(taxonomy=mine)`. The classifier prompt is generated from the taxonomy, so custom categories appear automatically — no prompt-rewriting required. The version string keys the disk cache, so changing it invalidates old classifications.

## The default metrics

Three metrics, all on by default. Each implements the `EvalMetric` Protocol independently — drop one, add your own, mix and match.

### `DefectRecall`

Of the defects in gold, what fraction did the reviewer flag? Match logic: same path + line within ±5 lines (`_LINE_PROXIMITY`) + judge-LLM semantic match. Per-severity breakdown included.

This is the headline number a team cares about. It's the answer to "is my reviewer actually catching the things humans caught?"

### `NoveltyRate`

What fraction of the reviewer's comments did NOT match any gold defect?

**Important: this is the warning light, not a "false positive rate."** Novel comments may be real defects gold missed (a junior reviewer noticed something the senior didn't), or they may be hallucinations / over-eager nits. The metric gives you the *signal* that something's off the rails; you read the per-sample drill-down to figure out which.

The framework deliberately never labels this "false positive rate" because that framing has caused real misreads in the wild. High novelty with low recall is concerning. High novelty with high recall might mean your reviewer is genuinely better than your humans were.

### `SeverityCalibration`

When the reviewer flagged a gold defect, how close was its severity to gold's? Reports the mean signed delta (positive means the reviewer over-severs, negative means it under-severs) and a confusion matrix (gold severity × peer severity).

This metric exists because the empirically-observed failure mode of v0.1 reviewers is severity drift, not detection — they find the defect but call a `critical` issue `minor`, or vice versa.

### Why not a single "quality score"

False precision. Compressing recall + novelty + calibration into one number hides exactly the trade-offs you care about. The trio is designed to be read together.

## Bring-your-own-everything

The whole framework is constructor injection. No `peer.toml`, no environment-variable plumbing, no registration mechanism. All customization happens in Python:

```python
from peer import Agent, EvalRunner, DefectRecall
from peer.dataset import JSONLStorage, LLMCommentClassifier, Taxonomy, CategoryDef

# 1. Custom taxonomy
my_taxonomy = Taxonomy(
    categories=[
        CategoryDef(name="security", description="auth, injection, secret leak", is_defect=True),
        CategoryDef(name="other", description="anything else", is_defect=False),
    ],
    severities=["blocker", "warning", "nit"],
    drop_categories=["other"],
    nit_only_categories=[],
    version="acme-v1",
)

# 2. Custom classifier wired to that taxonomy
my_classifier = LLMCommentClassifier(taxonomy=my_taxonomy)

# 3. Custom dataset loaded from disk
samples = JSONLStorage("acme/security_dataset.jsonl").load_all()

# 4. Custom metric set (drop SeverityCalibration; we don't care)
runner = EvalRunner(
    reviewer=Agent(model="claude-opus-4-7"),
    dataset=samples,
    metrics=[DefectRecall()],  # NoveltyRate dropped too
)
report = runner.run()
```

Each line above is one piece of the framework swapped independently of the others. No piece knows about any other — they communicate through the `GoldSample` / `Classification` / `Review` data shapes.

For the curation side, the same pattern:

```python
from peer.dataset import Curator, GitHubInlineCommentSource, JSONLStorage, PostMergeBugfixCorrelation

curator = Curator(
    source=GitHubInlineCommentSource(),
    classifier=my_classifier,        # from above
    enrichment=PostMergeBugfixCorrelation(),  # opt in to bugfix correlation
    storage=JSONLStorage("acme/security_dataset.jsonl"),
)
sample = curator.add("https://github.com/acme/repo/pull/123", auto_accept=False)
```

## The reference dataset

`dataset/reference/django_pydantic_v1.jsonl` ships 30 hand-spot-checked samples drawn from the Django + Pydantic 14-PR bootstrap batch plus follow-ups. It exists so newcomers can run `peer eval` end-to-end on day one without doing any curation themselves.

To inspect:

```bash
peer dataset list --dataset dataset/reference/django_pydantic_v1.jsonl
peer dataset list --dataset dataset/reference/django_pydantic_v1.jsonl --show-classifications
peer dataset show https://github.com/pydantic/pydantic/pull/7625
```

Or in Python:

```python
from peer.dataset import JSONLStorage
samples = JSONLStorage("dataset/reference/django_pydantic_v1.jsonl").load_all()
for s in samples:
    print(s.pr_url, len(s.gold_defects))
```

The dataset's bias is real and called out explicitly: 30 samples from two large Python OSS repos won't generalize to your repo's calibration. It exists as a credibility anchor and demo dataset, not as a benchmark. The forthcoming `benchmark-v01` will widen this materially across more repos and languages.

To regenerate or extend: `peer dataset add <pr_url>` against any GitHub PR will append a freshly-classified, spot-checkable sample. See [`docs/dataset_curation_guide.md`](dataset_curation_guide.md) for the methodology — what to spot-check, when to use `--auto-accept`, when to enable enrichment.

## Reports and reproducibility

Every `EvalReport` carries:

- `run_id` (UUID) and `timestamp`
- `agent_config` — model id, system-prompt hash, reviewer class name
- `dataset_path` and per-sample results (matched gold defects, novel peer comments, severity deltas)
- Aggregate metric results
- `cost` (USD estimate, computed from `Review.usage` × per-token pricing — `None` if pricing unavailable for the model)
- `latency` per-sample p50 / p95
- `report_schema_version` for forward-compat
- `peer_version`

`peer eval --baseline <prior.json>` runs a column-wise diff (`render_diff`) so you can see whether your prompt change moved recall, moved cost, or both. Storing report JSONs in git lets you read the eval trajectory across changes.

## What lives where

| Concern | Module |
|---|---|
| Top-level public exports | `src/peer/__init__.py` |
| Agent orchestration (gather → review → validate) | `src/peer/agent.py` |
| `Reviewer` Protocol + `ClaudeReviewer` | `src/peer/reviewers.py` |
| PR context gathering | `src/peer/context.py` |
| Codebase context (tree-sitter symbols, call sites, tests) | `src/peer/codebase_context.py` |
| Default system prompt | `src/peer/prompts.py` |
| Eval surface (runner, metrics, report, judging) | `src/peer/eval/` |
| Dataset surface (sources, classifier, taxonomy, enrichment, storage) | `src/peer/dataset/` |
| Unified CLI | `src/peer/cli.py` (entry: `peer` script) |
| Exceptions | `src/peer/exceptions.py` |
| Reference dataset | `dataset/reference/django_pydantic_v1.jsonl` |
| Design rationale | `openspec/changes/eval-v01/design.md`, `docs/design.md` |

## Where to go next

- **Building your own gold dataset:** [`docs/dataset_curation_guide.md`](dataset_curation_guide.md)
- **Why the framework is shaped the way it is:** `openspec/changes/eval-v01/design.md` (all 14 design decisions)
- **What's in / out of scope:** [`docs/scope_research.md`](scope_research.md)
- **How leading tools handle codebase context (informs the v0.2 roadmap):** [`docs/codebase_understanding_research.md`](codebase_understanding_research.md)
