## 1. Extractor models

- [ ] 1.1 Create `src/peer/autoresearch/diagnose.py` with Pydantic models: `FailureSummary`, `TopicDriftSummary`, `CostOutlierSummary`, `PrecisionMiss`. Each `ConfigDict(extra="forbid")`.

## 2. Extractor functions

- [ ] 2.1 `extract_failure_modes(report) -> FailureSummary` — iterate `per_sample[*].metrics["mean_per_pr_recall"].per_sample_detail.unmatched_gold`; group by severity; track sample count.
- [ ] 2.2 `extract_topic_drift(report) -> TopicDriftSummary` — find samples where `review_summary.n_comments > 0` AND `metrics["detection_rate"].per_sample_detail.matched_count == 0`; collect (peer_path/line, gold_path/line) tuples.
- [ ] 2.3 `extract_cost_outliers(report, n_top=3) -> CostOutlierSummary` — sort per_sample by `cost_usd` desc; take top N.
- [ ] 2.4 `extract_precision_misses(report) -> list[PrecisionMiss]` — collect peer comments from `novelty_rate.per_sample_detail.unmatched_peer`.

## 3. render_markdown

- [ ] 3.1 Implement `render_markdown(failure, drift, cost, precision_misses) -> str` with deterministic ordering, no timestamps.
- [ ] 3.2 Section: Suggested mutation axes — hard-coded list of known recipe fields the agent can mutate.

## 4. CLI: `peer autoresearch diagnose`

- [ ] 4.1 Add `diagnose` subparser under the `autoresearch` parent.
- [ ] 4.2 Handler `_cmd_autoresearch_diagnose` per spec. Resolve latest report by mtime when `--report` omitted.
- [ ] 4.3 Exit 2 when no report found.

## 5. Loop integration

- [ ] 5.1 After each iteration in `peer autoresearch loop`, invoke the extractors + render_markdown against the iteration's just-saved EvalReport.
- [ ] 5.2 Write to `data/autoresearch/<run_tag>/iter-<n>-hypothesis.md`.
- [ ] 5.3 Update `current_hypothesis.md` to mirror the latest iter's content (copy, not symlink, for cross-platform safety).

## 6. Exports

- [ ] 6.1 Export the four extract_* + render_markdown + the four models from `peer.autoresearch`.

## 7. BDD

- [ ] 7.1 `features/autoresearch_diagnose.feature` covering all scenarios.
- [ ] 7.2 Step defs use synthetic EvalReport fixtures (small Pydantic-constructed reports).

## 8. program.md update

- [ ] 8.1 Add a section in `program.md` (created by `autoresearch-recipe-v01`): "Before mutating, read data/autoresearch/<tag>/current_hypothesis.md and cite specific failure modes in your mutation description."

## 9. Quality gates

- [ ] 9.1 ruff / format / mypy / pytest / behave all clean.
