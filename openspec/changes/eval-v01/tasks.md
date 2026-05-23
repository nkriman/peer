## 1. Type schemas (foundation)

- [ ] 1.1 Create `src/peer/dataset/types.py` with Pydantic models: `RawComment`, `RawSample`, `Classification`, `CategoryDef`, `Taxonomy`, `GoldDefect`, `GoldSample`, `ProposedSample`. Severity / Comment / Review reused from `peer.types`.
- [ ] 1.2 Create `src/peer/eval/types.py` with Pydantic models: `MetricResult`, `EvalReport` (with `report_schema_version`, `run_id`, `timestamp`, `agent_config`, `dataset_path`, `summary`, `per_sample` fields), `EvalSummary` (aggregate metrics + cost + latency percentiles), `EvalSampleResult`.
- [ ] 1.3 Add exceptions in `src/peer/exceptions.py`: `InvalidGoldSample`, `EvalReportSchemaMismatch`, `DatasetNotFound`, `CurationRejected`.

## 2. Taxonomy + default Taxonomy instance (`src/peer/dataset/taxonomy.py`)

- [ ] 2.1 Define `CategoryDef` (name, description, is_defect bool, force_severity Optional[str]).
- [ ] 2.2 Define `Taxonomy` dataclass with `categories`, `severities`, `drop_categories`, `nit_only_categories`, `version`.
- [ ] 2.3 Export `DefaultTaxonomy` populated with the 8 categories from `design.md` Decision 4 (six defect categories, `style-nit`, `discussion`) and severities `["critical", "important", "minor", "nit"]`. Drop `discussion`, force `style-nit` to `nit`.
- [ ] 2.4 Unit test: `DefaultTaxonomy.categorize(category_name)` returns the right `CategoryDef`.

## 3. Raw sample source (`src/peer/dataset/sources.py`)

- [ ] 3.1 Define `RawSampleSource` Protocol with `fetch(pr_url: str) -> RawSample`.
- [ ] 3.2 Implement `GitHubInlineCommentSource` reusing the `gh` CLI wrappers from `peer.context`. Fetch PR metadata + bot-filtered inline + issue comments; return a typed `RawSample`.
- [ ] 3.3 Bot-filter: heuristic (login contains `bot` / ends with `[bot]`) plus explicit deny-list (`coderabbit`, `greptile`, `qodo-ai`, `graphite-app`, `codium`, `github-actions`, `dependabot`).
- [ ] 3.4 Unit test (no network): mock `_gh_run` to return fixture JSON; assert filtering and parsing.

## 4. Comment classifier (`src/peer/dataset/classifier.py`)

- [ ] 4.1 Define `CommentClassifier` Protocol with `classify(comment, pr_context) -> Classification`.
- [ ] 4.2 Implement `LLMCommentClassifier`: Haiku 4.5 default; one prompt per call; reads from a configurable `Taxonomy`; returns `Classification(category, severity, reasoning)`.
- [ ] 4.3 Implement disk-cache (default at `~/.cache/peer/classifier_cache.jsonl`) keyed on `(repo, comment_id, taxonomy.version)`. Cache hits skip the LLM call.
- [ ] 4.4 Cache invalidation: if `taxonomy.version` differs from the cached key, the call re-runs.
- [ ] 4.5 Unit tests: mock the Anthropic client; assert (a) a defect-body comment returns a defect category, (b) a question-body comment returns `discussion`, (c) cache hit avoids the mock call.

## 5. Enrichment (`src/peer/dataset/enrichment.py`)

- [ ] 5.1 Define `EnrichmentStep` Protocol with `enrich(sample, pr_context) -> GoldSample`.
- [ ] 5.2 Implement `NoEnrichment` (default — passthrough).
- [ ] 5.3 Implement `PostMergeBugfixCorrelation`: heuristic — look for PRs merged within 30 days after the current PR with `fix` / `regression` / `bug` in the title and overlap with the modified files; convert the follow-up's diff into low/medium-confidence `GoldDefect` entries. Mark `source="post_merge_correlation"`.
- [ ] 5.4 Implement `LLMOracleEnrichment`: configurable strong model (default Opus 4.7); same prompt shape as `Agent.review` but with "be a senior reviewer" framing; only `confidence="high"` defects pass through. Mark `source="llm_oracle"`.

## 6. Storage (`src/peer/dataset/storage.py`)

- [ ] 6.1 Define `GoldSampleStorage` Protocol with `add(sample)`, `load_all()`, `find(pr_url)`, `delete(pr_url)`.
- [ ] 6.2 Implement `JSONLStorage(path: Path)`: one sample per line; `add` is append + overwrite-on-duplicate by `pr_url` (rewrite file once detection occurs); `load_all` reads + validates every line via Pydantic; `InvalidGoldSample` raised with line number on malformed records.
- [ ] 6.3 Unit tests: round-trip a sample; duplicate overwrite; malformed line raises with line number.

## 7. Curator (`src/peer/dataset/curation.py`)

- [ ] 7.1 Implement `Curator` class composing source / classifier / enrichment / taxonomy / storage. Constructor uses defaults if not specified.
- [ ] 7.2 Implement `Curator.preview(pr_url) -> ProposedSample`: fetch + classify + enrich, no write.
- [ ] 7.3 Implement `Curator.add(pr_url, auto_accept=False) -> GoldSample`: same pipeline plus operator prompt (unless auto-accept) plus storage write.
- [ ] 7.4 Implement `Curator.add_batch(pr_urls, auto_accept=False)`: loop over URLs; per-PR failure logs warning, continues.
- [ ] 7.5 Operator prompt: print proposed sample, accept (`y`) / reject (`n`) / edit (`e` opens `$EDITOR` on a JSON dump). Records `metadata.spot_checked=True` on accept.

## 8. EvalMetric (`src/peer/eval/metrics.py`)

- [ ] 8.1 Define `EvalMetric` Protocol with `score(sample: GoldSample, review: Review) -> MetricResult`.
- [ ] 8.2 Implement `DefectRecall`: greedy match peer comments to gold defects by path equality + line-proximity (≤5 lines) + Haiku judge for semantic same-issue. Compute aggregate recall + per-severity breakdown.
- [ ] 8.3 Implement `NoveltyRate`: count unmatched peer comments / total peer comments. Always paired with DefectRecall.
- [ ] 8.4 Implement `SeverityCalibration`: for each matched pair, compute signed delta (peer severity ordinal − gold severity ordinal); aggregate mean + confusion matrix.
- [ ] 8.5 Reuse `judge_match` logic from the existing Slice 3a `eval.py` MVP; promote to a shared helper in `peer.eval.judging`.
- [ ] 8.6 Unit tests: synthetic GoldSample + Review fixtures covering full-hit, full-miss, partial-hit, severity-mismatch.

## 9. EvalRunner + EvalReport (`src/peer/eval/runner.py`, `src/peer/eval/report.py`)

- [ ] 9.1 Implement `EvalRunner(reviewer, dataset, metrics=None)` — defaults metrics to `[DefectRecall(), NoveltyRate(), SeverityCalibration()]`.
- [ ] 9.2 Implement `EvalRunner.run() -> EvalReport`: loop over samples, run reviewer, run every metric, capture cost (per-token pricing table) + latency (wall clock), aggregate.
- [ ] 9.3 Per-sample failure: log error, mark sample with `error` field, continue. Aggregate only successful samples.
- [ ] 9.4 Build the per-token pricing table for Claude family (Opus/Sonnet/Haiku 4.x) and OpenAI family (gpt-4o, gpt-4o-mini). Pricing fetched from `peer/eval/pricing.py` — hand-maintained table, dated.
- [ ] 9.5 `EvalReport.to_json()` / `from_json()` round-trip; raise `EvalReportSchemaMismatch` on version mismatch.
- [ ] 9.6 `render_summary(report) -> str` — CLI table renderer for a single report.
- [ ] 9.7 `render_diff(report_a, report_b) -> str` — per-metric delta + cost/latency delta + per-sample regression/improvement counts.

## 10. Unified CLI (`src/peer/cli.py`)

- [ ] 10.1 Implement `peer` console entry point via `pyproject.toml [project.scripts]`. Top-level argparse with subparsers.
- [ ] 10.2 Implement `peer review` subcommand — moves logic from `peer.review.main` here; existing `python -m peer.review` becomes a thin forwarder.
- [ ] 10.3 Implement `peer eval` subcommand — wraps `EvalRunner`; supports `--dataset`, `--model`, `--baseline`, `--out`. Default dataset is `dataset/reference/django_pydantic_v1.jsonl`.
- [ ] 10.4 Implement `peer dataset add` subcommand — wraps `Curator.add`; `--dataset`, `--auto-accept`.
- [ ] 10.5 Implement `peer dataset list` subcommand — `--dataset`, `--show-classifications`.
- [ ] 10.6 Implement `peer dataset show <pr_url>` subcommand — pretty-prints the full sample; non-zero exit on not-found.
- [ ] 10.7 Update `pyproject.toml` `[project.scripts]` to register `peer = "peer.cli:main"`.

## 11. Reference dataset (`dataset/reference/`)

- [ ] 11.1 Use `Curator(...).add(..., auto_accept=False)` to curate the 14 PRs from `data/slice2_runs/` plus ~16 more (mix of Django + Pydantic, varied complexity). All spot-checked.
- [ ] 11.2 Save as `dataset/reference/django_pydantic_v1.jsonl`.
- [ ] 11.3 Write `dataset/reference/CURATION_NOTES.md`: methodology, per-PR notes for borderline classifications, version of `DefaultTaxonomy` used, total spot-check time.

## 12. Reshape existing `eval.py` into the new framework

- [ ] 12.1 Delete current `src/peer/eval.py` after its primitives are absorbed into `src/peer/eval/judging.py` (judge prompt + `judge_match`) and `src/peer/dataset/sources.py` (`fetch_human_comments` reborn as part of `GitHubInlineCommentSource`).
- [ ] 12.2 Confirm `src/peer/__init__.py` exports: `Agent`, `Reviewer`, `EvalRunner`, `Curator`, `GoldSample`, `DefaultTaxonomy`, `EvalReport`.

## 13. Docs

- [ ] 13.1 README: replace the existing quickstart with a 3-step flow: `pip install peer` → `peer review <pr_url>` → `peer eval --dataset dataset/reference/django_pydantic_v1.jsonl`. Show one customization example (custom classifier).
- [ ] 13.2 `docs/framework_overview.md`: the 8 Protocols, their default impls, how to override each, with a code example per Protocol.
- [ ] 13.3 `docs/dataset_curation_guide.md`: the methodology — what each Taxonomy category means, when to use enrichment, the spot-check workflow.

## 14. Tests + smoke

- [ ] 14.1 End-to-end smoke: build a 3-sample fake dataset, run `peer eval` against a mocked Reviewer, assert the resulting `EvalReport` has the right shape + non-zero metrics.
- [ ] 14.2 Cross-version cache compat: write classifier cache with taxonomy.version A, run with taxonomy.version B, assert re-classification.
- [ ] 14.3 `peer dataset add --auto-accept` against one real PR (gated on `gh auth status`), assert resulting JSONL line validates.

## 15. Out-of-scope confirmation

- [ ] 15.1 No `peer.toml` config in v0.1 (Decision 3).
- [ ] 15.2 No commercial-reviewer adapters in v0.1 (`benchmark-v01` scope).
- [ ] 15.3 No deepeval integration in defaults; `deepeval` import is reserved for user-side custom metrics.
- [ ] 15.4 No web UI / continuous-eval / CI integration.
