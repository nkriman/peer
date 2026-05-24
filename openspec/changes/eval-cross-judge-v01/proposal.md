## Why

Every detection_rate number peer publishes flows through *one* judge call per (peer_comment, gold_defect) pair, using *one* judge model (Haiku default). The judge has its own bias, its own snapshot drift, and its own noise floor. We're publishing point estimates against a single judge as if they were ground truth.

The architecture sweep just landed a clean finding: narrower context beats wider, opus is worse than sonnet. Both findings are at the same magnitude as the variance we'd likely see if we ran the same recipe with a different judge model. We have no way of telling them apart today.

This change adds a cross-judge variance utility — re-judges the same reviewer outputs against N judge models and reports per-metric variance bands. It's a prerequisite for any defensible benchmark claim. Without it, every published number is "we observed X under our particular Haiku snapshot" — provisional at best.

Also adds a small held-out split convention to `peer.dataset.JSONLStorage` so autoresearch loops can stop accidentally over-fitting their hill-climbing to the same 7-PR dev set.

## What Changes

- New `peer.eval.cross_judge` module:
  - `CrossJudgeRunner(reviewer, dataset, judge_models: list[str])` — drives the eval. Internally runs the reviewer ONCE per sample (caches the `Review`), then re-runs each metric N times with N different judge clients. Avoids spending N× on the expensive reviewer pass.
  - `CrossJudgeReport` Pydantic model with per-metric per-judge values + computed variance bands (`min`, `max`, `median`, `range`).
  - `compute_variance_bands(reports: list[EvalReport]) -> CrossJudgeReport` — pure function over N single-judge EvalReports for the same dataset.
- New `peer.eval.report.render_cross_judge_summary(cross_report) -> str` — markdown rendering with per-metric variance band visualization.
- CLI: `peer eval --cross-judge sonnet,haiku,opus [other-eval-flags]` flag. When set, the runner becomes a `CrossJudgeRunner` and the output report is a `CrossJudgeReport` (saved to `data/eval_runs/cross_judge_<run_id>.json`).
- `peer.dataset.split` helper module:
  - `load_split(base_path: Path, split: str) -> list[GoldSample]` — convention: `base_path = data/foo.jsonl`, `split = "dev"` → reads `data/foo.dev.jsonl`. Falls back to `base_path` itself when no split file exists (back-compat).
  - Documented convention: hand-curated datasets ship as `<name>.dev.jsonl` (for autoresearch) and `<name>.test.jsonl` (held-out, never autoresearched against).
- New peer.eval export of `CrossJudgeRunner`, `CrossJudgeReport`, `compute_variance_bands`, `render_cross_judge_summary`.

## Capabilities

### New Capabilities

- `eval-cross-judge`: cross-judge variance utility (runner + report model + CLI flag + renderer).

### Modified Capabilities

- `eval-runner` (from eval-v01/v02): `EvalRunner` gains an optional `judge_client_override: Any | None = None` parameter so `CrossJudgeRunner` can swap clients per-judge-pass without rebuilding the whole runner.

## Impact

- **Code**: new `src/peer/eval/cross_judge.py`, new `src/peer/dataset/split.py`. Modifications: `src/peer/eval/runner.py` (add judge_client_override kwarg), `src/peer/eval/__init__.py` (export), `src/peer/cli.py` (--cross-judge flag).
- **Dependencies**: none new.
- **Tests**: BDD in `features/eval_cross_judge.feature` + `features/dataset_split.feature`. Synthetic EvalReports for variance computation tests.
- **Schema**: `CrossJudgeReport` is a new top-level Pydantic model. Existing `EvalReport` unchanged.
- **Back-compat**: switch defaults off. `peer eval` without `--cross-judge` behaves identically to today.
- **Out of scope**: rubric-based judge prompts (single binary SAME/DIFFERENT today), human spot-check loops, judge ensembling for production reviews (this is purely an evaluation tool).
- **Performance**: re-judging N times adds N × (number of comments × judge_cost). On the hard subset with N=3 judges, that's roughly 3× judge cost (~$0.05 of haiku calls per run), reviewer cost unchanged.
