## Why

`peer` is positioned as a *framework* for building AI PR review agents, with evaluation built in. `agent-v01` shipped the agent surface (pluggable Reviewer, PR context, codebase context). What's missing is the second half of the framework: the evaluation toolkit teams use to build their own gold-standard dataset for their own repository, measure their custom reviewer against it, and iterate.

The MVP eval ad-hoc'd as part of Slice 3a (committed in `5b78409`'s tree) demonstrated two things:

1. The plumbing works — judge-LLM scoring against fetched human comments produces numbers.
2. **The naive shape is wrong.** Treating raw GitHub inline comments as ground truth conflates defects with author-reviewer Q&A; 6/14 PRs in the first batch had zero defect-style human comments at all. The resulting 13% hit rate is meaningless without a transformation pipeline that converts raw conversational data into a clean defect-labeled dataset.

This change defines that pipeline — and frames it correctly. The transformation is per-team and per-repo; what `peer` ships is the *pipeline shape* with extension points, plus sensible defaults that work out of the box on generic OSS Python repos.

In parallel, the change introduces a unified `peer` CLI that hosts the existing `peer review` and the new `peer eval` / `peer dataset` subcommands, replacing the current per-script entry points.

## What Changes

- Define eight extension-point Protocols that compose the eval pipeline (`RawSampleSource`, `CommentClassifier`, `Taxonomy`, `EnrichmentStep`, `GoldSampleStorage`, `EvalMetric`, `EvalReport`, plus the existing `Reviewer` from `agent-v01`).
- Ship one default implementation per Protocol that is "good enough" for the OSS user with no configuration — not perfect, but useful out of the box.
- Implement `EvalRunner` that composes a configured pipeline and produces a versioned, JSON-serializable `EvalReport` with summary + per-sample drill-down + cost + latency.
- Implement the dataset-curation workflow: fetch raw → classify → (optional enrich) → human spot-check loop → store as JSONL.
- Implement the unified `peer` CLI: `peer review`, `peer eval`, `peer dataset add|list|show`.
- Ship a small *reference dataset* (~30 hand-spot-checked samples from Django + Pydantic) so newcomers can see the framework working end-to-end immediately.
- Document the framework's SOTA-credibility path: how a team uses these pieces to build a reviewer that competes with commercial baselines (CodeRabbit, Greptile, Cursor review). The Reviewer Protocol from `agent-v01` already enables BYO-API-key commercial adapters as comparison targets in the same `EvalRunner`. The actual benchmark run is a separate forthcoming change (`benchmark-v01`), not v0.1 scope.

## Capabilities

### New Capabilities

- `eval-runner`: composes a `(Reviewer, dataset, metrics)` pipeline, runs it, produces a versioned `EvalReport` with per-sample breakdown, severity calibration, cost, and latency. Supports A/B comparison of two reports.
- `dataset-curation`: end-to-end workflow that transforms raw `(PR, comments)` data into curated `(PR, gold_defects)` samples. Pluggable at every step. Default classifier is LLM-based with an 8-category taxonomy.
- `unified-cli`: a single `peer` entry point with subcommands for review, eval, and dataset operations. Existing `python -m peer.review` keeps working as an alias.

### Modified Capabilities

- `pr-review-agent` (from `agent-v01`): no behavioral change. The `Reviewer` Protocol stays exactly as defined. This change *uses* it from `EvalRunner`; it does not modify it.

## Impact

- **Code**: new modules `src/peer/eval/` (subpackage: `runner.py`, `metrics.py`, `report.py`), `src/peer/dataset/` (subpackage: `sources.py`, `classifier.py`, `taxonomy.py`, `enrichment.py`, `storage.py`, `curation.py`), `src/peer/cli.py` (the unified CLI). The existing `src/peer/eval.py` MVP gets reshaped into `src/peer/eval/` and its primitives become default implementations.
- **Dependencies**: no new heavy deps. `deepeval` (already declared) stays declared but is *not* used in the v0.1 default impls — judged not worth the abstraction overhead for our default metrics. Reserved for users who want it.
- **Reference dataset**: ships at `dataset/reference/django_pydantic_v1.jsonl` (~30 samples). Format defined in `specs/dataset-curation/`. Curation methodology + the spot-check log shipped alongside in `dataset/reference/CURATION_NOTES.md`.
- **CLI migration**: `python -m peer.review <pr_url>` keeps working (the entry stays as a thin alias forwarder). `python -m peer.eval` removed in favor of `peer eval` (or `python -m peer eval`).
- **Repo / packaging**: single `peer` package, single `pip install peer`. Optional extras may be added for heavy deps in future (e.g., `peer[deepeval]`); none in v0.1. The internal subpackage structure (`peer.eval.*`, `peer.dataset.*`) is designed to enable future `peer-eval` / `peer-dataset` splits if user demand ever justifies the version-skew cost.
- **Out of scope for this change**: actually running peer-built reviewers against commercial baselines on a public benchmark (deferred to `benchmark-v01`); GitLab/Bitbucket sources (`RawSampleSource` Protocol enables it, default impl is GitHub-only); deepeval integration (Protocol enables it, no default); per-team configuration files / `peer.toml` (deferred — for v0.1, configuration is via constructor injection in Python code).
