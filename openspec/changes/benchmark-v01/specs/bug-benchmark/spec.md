## ADDED Requirements

### Requirement: BugSample is the typed unit of a runtime-bug benchmark dataset

The framework SHALL define a `BugSample` Pydantic model with: `bug_id`, `repo_url`, `pr_url` (optional), `commit_sha`, `bug_paths: list[BugLocation]`, `root_cause` (str), `suggested_fix` (optional), `severity`, `language`, `bug_category` (optional), `metadata` (dict). `BugLocation` carries `path`, `start_line`, `end_line`.

#### Scenario: Round-trip via JSONL

- **WHEN** a `BugSample` is written to a JSONL line and read back via the dataset loader
- **THEN** all fields preserve content and validate against the Pydantic schema

#### Scenario: Validation rejects malformed bug

- **WHEN** a JSONL line is missing required field `root_cause`
- **THEN** loading raises `InvalidBugSample` with line number and field name

### Requirement: MacroscopeLoader reads the vendored snapshot

The framework SHALL provide `peer.benchmark.MacroscopeLoader().load(repo_path: Optional[Path] = None) -> list[BugSample]` that reads `dataset/benchmark/macroscope_v1.jsonl` (vendored) by default, or a user-supplied path. SHALL filter to Python-only samples by default in v0.1; SHALL accept `language=None` to load all.

#### Scenario: Default load returns Python-only samples

- **WHEN** `MacroscopeLoader().load()` is called with default arguments
- **THEN** the returned list contains only `BugSample`s whose `language == "python"`

#### Scenario: All-languages load

- **WHEN** `MacroscopeLoader().load(language=None)` is called
- **THEN** the returned list contains all 118 (or N) bugs in the vendored dataset

### Requirement: BugBenchmarkRunner runs a reviewer against a BugDataset and scores detection

The framework SHALL provide `BugBenchmarkRunner(reviewer, dataset, judge_model="claude-haiku-4-5-20251001")` that for each bug: invokes the reviewer on the bug's repo/SHA, scores whether any peer comment caught the bug (path overlap + line proximity ≤10 + Haiku judge), and produces a `BenchmarkReport`.

#### Scenario: Bug caught

- **WHEN** the reviewer produces a comment with `path` matching one of the bug's `bug_paths[*].path` AND `line` within `[bug.start_line - 10, bug.end_line + 10]` AND the bug-detection judge returns CAUGHT
- **THEN** the bug is marked as caught in the per-bug breakdown and counted in `n_bugs_caught`

#### Scenario: Bug missed (no proximity)

- **WHEN** the reviewer produces no comments within the proximity range of the bug
- **THEN** the bug is marked as missed with reason "no comments in proximity"

#### Scenario: Bug missed (judge rejected)

- **WHEN** the reviewer produces comments in proximity but the judge returns NOT_CAUGHT for all of them
- **THEN** the bug is marked as missed with reason "judge rejected — comments did not identify root cause"

### Requirement: Bug-detection judge is distinct from gold-match judge

The bug-detection judge prompt SHALL ask "Did this reviewer comment identify the bug?" given the bug's root cause + the reviewer comment text. SHALL return CAUGHT or NOT_CAUGHT in a single LLM call per (bug, peer-comment) pair. SHALL be a separate function from `eval/judging.py:judge_match`.

#### Scenario: Judge correctly identifies caught bug

- **WHEN** the bug's root cause is "the loop iterates one more time than expected (off-by-one)" and the peer comment body says "the upper bound of this range is wrong — should be `n` not `n + 1`"
- **THEN** the judge returns CAUGHT

#### Scenario: Judge correctly rejects unrelated comment

- **WHEN** the bug's root cause is about a SQL injection vulnerability and the peer comment is about a missing docstring
- **THEN** the judge returns NOT_CAUGHT

### Requirement: BenchmarkReport schema

The framework SHALL produce a `BenchmarkReport` Pydantic model containing: `report_schema_version`, `run_id`, `timestamp`, `agent_config`, `dataset_id`, `dataset_size`, `n_bugs_caught`, `n_bugs_total`, `detection_rate`, `comments_per_pr`, `cost_usd_total`, `latency_p50_seconds`, `per_bug: list[BugBenchmarkResult]`, `published_baselines: dict`.

#### Scenario: Report serialization

- **WHEN** a `BenchmarkReport` is created and `report.to_json(path)` is called, then `BenchmarkReport.from_json(path)` is called on the same path
- **THEN** the loaded report has identical content

### Requirement: Published-baselines comparison rendered

The CLI / report renderer for `BenchmarkReport` SHALL include a `published_baselines` section showing peer's number side-by-side with the published baselines (Macroscope, CodeRabbit, Cursor BugBot, Greptile, Graphite Diamond). Baseline data SHALL be hand-maintained in `src/peer/benchmark/baselines.py`.

#### Scenario: Baselines section in CLI output

- **WHEN** `peer benchmark --dataset macroscope` completes
- **THEN** the rendered output includes a section labeled "Published baselines" with at least 5 rows showing each tool's detection rate + comments/PR + source citation

### Requirement: `peer benchmark` CLI subcommand

The framework SHALL add a `peer benchmark --dataset <name-or-path> [--out PATH] [--yes]` subcommand that:

1. Loads the named dataset (default: `macroscope` → vendored snapshot)
2. Estimates cost; prompts confirmation unless `--yes`
3. Runs `BugBenchmarkRunner` with the default agent (configurable via `--model`)
4. Saves report to `--out` (default: `data/benchmark_runs/<run_id>.json`)
5. Prints the leaderboard-style summary

#### Scenario: Default benchmark run

- **WHEN** `peer benchmark --yes` is invoked with default args
- **THEN** the Macroscope vendored dataset loads, the runner executes against the default agent, a report is saved, and the leaderboard summary prints to stdout

#### Scenario: Custom dataset

- **WHEN** `peer benchmark --dataset path/to/my_bugs.jsonl --yes` is invoked
- **THEN** the custom JSONL is loaded as `BugSample` records and run

#### Scenario: Cost guardrail prompts when over $5

- **WHEN** `peer benchmark` is invoked without `--yes` and the estimated cost is > $5.00
- **THEN** the user is prompted "Estimated cost: $7.40. Proceed? [y/N]" and the run aborts on N

### Requirement: Vendored dataset with provenance

The repository SHALL include `dataset/benchmark/macroscope_v1.jsonl` (vendored snapshot) and `dataset/benchmark/MACROSCOPE_PROVENANCE.md` documenting upstream source URL, commit SHA at time of vendoring, fetch date, license (MIT), and the schema-mapping notes.

#### Scenario: Provenance file readable

- **WHEN** a user opens `dataset/benchmark/MACROSCOPE_PROVENANCE.md`
- **THEN** they see the upstream commit SHA, fetch date, license, and a clear statement of how the upstream data was mapped to peer's `BugSample` schema

### Requirement: Update-dataset helper for refreshing the vendored snapshot

The CLI SHALL include `peer benchmark update-dataset --source <upstream> [--apply]` that fetches the upstream dataset, diffs against the vendored copy, and (with `--apply`) overwrites the vendored copy + updates provenance.

#### Scenario: Diff without apply

- **WHEN** `peer benchmark update-dataset --source github.com/vlad-ko/pr-review-bench` is invoked without `--apply`
- **THEN** the helper prints a summary of added / removed / changed bugs vs the vendored copy and exits without modifying files

#### Scenario: Diff with apply

- **WHEN** the same is invoked with `--apply`
- **THEN** the vendored JSONL + provenance file are updated to reflect the upstream
