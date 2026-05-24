## Why

Today's loop is blind: the agent mutates `recipe.yaml` based on intuition, runs an eval, sees a number, decides keep/discard. It never reads the *failure modes* that produced the number. autoresearch's val_bpb has no failure modes to read; peer's eval does — `per_sample.metrics.mean_per_pr_recall.per_sample_detail.unmatched_gold` is the structured list of gold defects peer missed, including the gold defect's path/line/severity/description and (where the run captured it) which peer comments lived nearby but the judge rejected.

This change closes the diagnostic loop. After each iteration, a `peer autoresearch diagnose` step reads the latest `EvalReport`, produces a human-readable diagnostic markdown summarizing what was missed and where, and writes it to `data/autoresearch/<run_tag>/current_hypothesis.md`. The autoresearch agent (via instructions added to `program.md`) is expected to read this file before proposing the next mutation — so the agent's mutations are grounded in concrete failure modes, not vibes.

The framework win: this turns peer's eval surface into the *teacher signal* for autoresearch, in the same way `val_bpb` is the teacher signal for autoresearch's training loop — except much richer, because peer's eval surfaces structured failure cases the agent can specifically address.

## What Changes

- New `peer.autoresearch.diagnose` module — pure functions over an `EvalReport`:
  - `extract_failure_modes(report) -> FailureSummary` — aggregates unmatched_gold across all per-sample results; clusters by repo, by severity tier, by gold-defect category-keyword (extracted from description text).
  - `extract_topic_drift(report) -> TopicDriftSummary` — for samples where peer emitted comments BUT none matched, surface the peer-comment topics vs the gold-defect topics. This is the "talked about the wrong things" signal we saw in the v0.2 verification run.
  - `extract_cost_outliers(report) -> CostOutlierSummary` — top 3 most-expensive samples; what made them expensive.
  - `extract_precision_misses(report) -> list[PrecisionMiss]` — peer comments that DON'T match any gold; flagged for review (high-precision strategies want zero of these).
- New `peer.autoresearch.diagnose.render_markdown(failure, drift, cost, precision_misses) -> str` — produces a structured markdown document with sections: Headline, Failure modes by severity, Topic drift, Cost outliers, Precision concerns, Suggested mutation axes. The last section is template text — the autoresearch agent reads it and synthesizes a concrete mutation.
- New `peer autoresearch diagnose [--report <path>] [--out <path>]` CLI — runs the extractors on the latest (or specified) EvalReport, renders the markdown, writes it to `data/autoresearch/<run_tag>/current_hypothesis.md` (or `--out`).
- Update `peer autoresearch loop` — after each iteration, automatically invoke `diagnose` against the just-completed run's report. Write to `data/autoresearch/<run_tag>/iter-<n>-hypothesis.md`. Update `current_hypothesis.md` to point at the latest. The default no-op mutator doesn't read the file, but the human-driven agent loop does.
- Update `program.md` — add a "Before mutating, read `current_hypothesis.md`" instruction. The autoresearch agent's prompt MUST cite specific failure modes from the hypothesis when describing the proposed mutation.

## Capabilities

### New Capabilities

- `autoresearch-mutator`: the `diagnose` module + CLI subcommand + per-iteration hypothesis artifacts.

### Modified Capabilities

- `autoresearch-recipe` (from `autoresearch-recipe-v01`): `peer autoresearch loop` writes a per-iteration hypothesis markdown alongside its TSV row.

## Impact

- **Code**: new `src/peer/autoresearch/diagnose.py`. Modify `src/peer/cli.py` (add `diagnose` subcommand) and `src/peer/autoresearch/loop.py` (invoke diagnose after each iter).
- **Tests**: BDD in `features/autoresearch_diagnose.feature` over synthetic EvalReport fixtures.
- **Dependencies**: none new (markdown rendering is pure-Python; clustering is simple keyword matching).
- **Out of scope**: LLM-powered diagnostic synthesis (the markdown is structured / deterministic; the agent that READS the markdown is the LLM); cross-iteration regression detection ("this mutation undid the gains of iter 3"); auto-applied mutations (the agent still hand-authors the next recipe).
- **Back-compat**: opt-in. `peer autoresearch run` does not auto-diagnose. Only `peer autoresearch loop` does (and only when the markdown directory exists / is creatable).
