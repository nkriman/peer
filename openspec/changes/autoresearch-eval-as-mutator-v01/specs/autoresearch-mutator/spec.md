## ADDED Requirements

### Requirement: diagnose module extracts structured failure summaries from an EvalReport

The framework SHALL define `peer.autoresearch.diagnose` with the following pure functions, each taking an `EvalReport` and returning a structured Pydantic model:

- `extract_failure_modes(report) -> FailureSummary` — aggregates unmatched_gold across all per-sample results.
- `extract_topic_drift(report) -> TopicDriftSummary` — for samples where peer emitted ≥1 comment AND matched 0 gold, surfaces peer-comment paths/lines vs gold-defect paths/lines.
- `extract_cost_outliers(report, n_top: int = 3) -> CostOutlierSummary` — top-N most-expensive samples.
- `extract_precision_misses(report) -> list[PrecisionMiss]` — peer comments not matched to any gold defect.

Each Pydantic model SHALL use `ConfigDict(extra="forbid")`.

#### Scenario: extract_failure_modes aggregates unmatched_gold by severity

- **GIVEN** an EvalReport with 3 samples where unmatched_gold counts are [{important: 5}, {critical: 1, minor: 2}, {important: 1, nit: 3}]
- **WHEN** `extract_failure_modes(report)` is called
- **THEN** the returned FailureSummary's per-severity totals are critical=1, important=6, minor=2, nit=3
- **AND** `.n_samples_with_misses` equals 3

#### Scenario: extract_topic_drift surfaces samples where peer commented but matched nothing

- **GIVEN** an EvalReport with one sample where peer emitted 3 comments and matched 0 gold defects
- **WHEN** `extract_topic_drift(report)` is called
- **THEN** the returned TopicDriftSummary has 1 sample in `.drift_samples` and each peer-comment vs gold-defect topic pair is included for inspection

#### Scenario: extract_cost_outliers ranks by cost descending

- **GIVEN** an EvalReport whose per-sample costs are [0.02, 0.05, 0.10, 0.03]
- **WHEN** `extract_cost_outliers(report, n_top=2)` is called
- **THEN** the returned CostOutlierSummary's `.top` has the sample at cost 0.10 first, followed by 0.05

#### Scenario: extract_precision_misses returns unmatched peer comments

- **GIVEN** an EvalReport with one sample whose peer emitted 4 comments and matched 1 gold
- **WHEN** `extract_precision_misses(report)` is called
- **THEN** the returned list has length 3 (the 3 unmatched peer comments)

### Requirement: render_markdown produces a structured hypothesis document

The framework SHALL define `peer.autoresearch.diagnose.render_markdown(failure, drift, cost, precision_misses) -> str`. The output SHALL be valid Markdown with sections in this order: `# Hypothesis`, `## Headline`, `## Failure modes by severity`, `## Topic drift`, `## Cost outliers`, `## Precision concerns`, `## Suggested mutation axes`. The "Suggested mutation axes" section SHALL list known mutation dimensions (`system_prompt`, `temperature`, `model`, `retries`, `post_processing.max_comments_per_pr`, `reviewer_dotted_path`, `codebase_context_max_tokens`) as bullet points so the autoresearch agent has a checklist of options.

#### Scenario: render_markdown emits the expected section headers

- **WHEN** `render_markdown(...)` is called on populated inputs
- **THEN** the returned string contains the literal strings `"# Hypothesis"`, `"## Headline"`, `"## Failure modes by severity"`, `"## Topic drift"`, `"## Cost outliers"`, `"## Precision concerns"`, and `"## Suggested mutation axes"`

#### Scenario: render_markdown lists mutation axes deterministically

- **WHEN** `render_markdown(...)` is called twice on identical inputs
- **THEN** the two outputs are byte-equal (no timestamps, no random ordering)

### Requirement: `peer autoresearch diagnose` writes the hypothesis to disk

The CLI SHALL expose `peer autoresearch diagnose [--report PATH] [--out PATH]`. When `--report` is omitted, the command resolves the most-recent EvalReport under `data/eval_runs/` by mtime. When `--out` is omitted, the command writes to `data/autoresearch/<run_tag>/current_hypothesis.md` where `<run_tag>` is derived from the report's `run_id`. The command SHALL exit 0 on success, 2 if no report is found.

#### Scenario: diagnose with explicit --report and --out writes the file

- **GIVEN** a small EvalReport at `tmp/report.json`
- **WHEN** I invoke `peer autoresearch diagnose --report tmp/report.json --out tmp/hyp.md`
- **THEN** the command exits 0
- **AND** `tmp/hyp.md` exists and starts with `"# Hypothesis"`

#### Scenario: diagnose with no report found exits 2

- **GIVEN** an empty `data/eval_runs/` directory (or one with no `.json` files)
- **WHEN** I invoke `peer autoresearch diagnose` (no `--report`)
- **THEN** the command exits 2 and prints an error to stderr

### Requirement: `peer autoresearch loop` auto-writes hypotheses per iteration

The `peer autoresearch loop` command (from `autoresearch-recipe-v01`) SHALL, after each iteration's eval completes, invoke `extract_*` + `render_markdown` against that iteration's EvalReport and write the markdown to `data/autoresearch/<run_tag>/iter-<n>-hypothesis.md`. The loop SHALL also update `data/autoresearch/<run_tag>/current_hypothesis.md` (symlink or copy) to point at the latest iteration's hypothesis.

#### Scenario: loop writes per-iteration hypothesis files

- **GIVEN** a loop run with --max-iters 2
- **WHEN** the loop completes
- **THEN** `data/autoresearch/<run_tag>/iter-1-hypothesis.md` exists
- **AND** `data/autoresearch/<run_tag>/iter-2-hypothesis.md` exists
- **AND** `data/autoresearch/<run_tag>/current_hypothesis.md` exists and matches the content of iter-2's file
