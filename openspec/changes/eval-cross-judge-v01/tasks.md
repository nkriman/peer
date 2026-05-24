## 1. Cross-judge models

- [ ] 1.1 Create `src/peer/eval/cross_judge.py` with `MetricBand` and `CrossJudgeReport` Pydantic models (both `ConfigDict(extra="forbid")`).
- [ ] 1.2 Implement `compute_variance_bands(reports: list[EvalReport]) -> CrossJudgeReport` per spec.

## 2. EvalRunner judge_client_override

- [ ] 2.1 Add `judge_client_override: Any | None = None` to `EvalRunner.__init__`.
- [ ] 2.2 When set, `_get_client()` returns it directly (skipping `make_client()`).

## 3. CrossJudgeRunner

- [ ] 3.1 `CrossJudgeRunner(reviewer, dataset, judge_models, concurrency=5)` per spec.
- [ ] 3.2 Phase 1: run reviewer once per sample, cache the `Review` per pr_url.
- [ ] 3.3 Phase 2: for each judge_model, construct a per-judge anthropic client + thin wrapper `_CachedReviewer` that returns the cached `Review`; instantiate EvalRunner with both; call `.run()`. Avoid double-billing the reviewer.
- [ ] 3.4 Aggregate into a `CrossJudgeReport` via `compute_variance_bands`.

## 4. Render

- [ ] 4.1 `render_cross_judge_summary(report) -> str` per spec.
- [ ] 4.2 High-variance annotation when `max / min >= 2.0`.

## 5. Dataset split

- [ ] 5.1 Create `src/peer/dataset/split.py` with `load_split(base_path, split)` per spec.
- [ ] 5.2 Allowed splits: `{"dev", "test"}`. Raise `ValueError` on others.
- [ ] 5.3 INFO log on fallback.

## 6. CLI

- [ ] 6.1 Add `--cross-judge` flag to `peer eval` parsing comma-separated model names.
- [ ] 6.2 `_cmd_eval` dispatches to `CrossJudgeRunner` when flag is set.
- [ ] 6.3 Refuse `--cross-judge` + `--baseline` combination (exit 2).

## 7. Exports

- [ ] 7.1 Export `CrossJudgeRunner`, `CrossJudgeReport`, `MetricBand`, `compute_variance_bands`, `render_cross_judge_summary` from `peer.eval`.
- [ ] 7.2 Export `load_split` from `peer.dataset` (or `peer.dataset.split`).

## 8. BDD

- [ ] 8.1 `features/eval_cross_judge.feature` covering all scenarios in the cross-judge requirements.
- [ ] 8.2 `features/dataset_split.feature` covering the 3 split scenarios.
- [ ] 8.3 Step defs with synthetic EvalReports + tmp dataset files.

## 9. Quality gates

- [ ] 9.1 ruff / format / mypy / pytest / behave all clean.
