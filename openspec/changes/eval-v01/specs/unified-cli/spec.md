## ADDED Requirements

### Requirement: Unified `peer` CLI entry point with subcommands

The framework SHALL provide a single `peer` console entry point with argparse subparsers for `review`, `eval`, and `dataset` subcommands. `peer --help` SHALL list all subcommands; each subcommand SHALL accept `--help` for its own usage.

#### Scenario: Top-level help

- **WHEN** `peer --help` is invoked
- **THEN** the output lists at minimum: `review`, `eval`, `dataset` as available subcommands

#### Scenario: Subcommand help

- **WHEN** `peer review --help` is invoked
- **THEN** the output shows `review`'s own flags (`--model`, `--system-prompt-file`, `-v`) and positional `pr_url`

### Requirement: `peer review` is the unified review subcommand

The framework SHALL implement `peer review <pr_url>` with the same behavior as the existing `python -m peer.review <pr_url>`: gather context, run the configured `Agent`, print a human-readable severity-grouped summary.

#### Scenario: Equivalent to legacy entry point

- **WHEN** `peer review https://github.com/owner/repo/pull/N` is invoked
- **THEN** the output matches what `python -m peer.review https://github.com/owner/repo/pull/N` produces (the legacy entry point is a thin alias forwarder)

### Requirement: `peer eval` runs eval with configured defaults

The framework SHALL implement `peer eval --dataset PATH [--model M] [--baseline RUN_ID] [--out PATH]` that:

1. Loads a dataset from PATH (defaults to `dataset/reference/django_pydantic_v1.jsonl` if PATH is omitted)
2. Builds an `Agent` with the given model (defaults to `claude-sonnet-4-6`)
3. Runs the default `EvalRunner(Agent, dataset)` with default metrics
4. Saves the report to `--out` (default `data/eval_runs/<run_id>.json`)
5. Prints the CLI summary
6. If `--baseline` is provided, also prints the A/B diff

#### Scenario: Default eval run

- **WHEN** `peer eval` is invoked with no arguments
- **THEN** the default reference dataset is loaded, the default agent is built, the runner executes, and a CLI summary is printed

#### Scenario: Eval with baseline

- **WHEN** `peer eval --baseline data/eval_runs/abc123.json` is invoked
- **THEN** after the new run, the CLI prints a column-wise diff vs the baseline report

### Requirement: `peer dataset add` ingests a PR into the dataset

The framework SHALL implement `peer dataset add <pr_url> [--dataset PATH] [--auto-accept]` that runs the `Curator` pipeline on the given PR URL and writes the resulting `GoldSample` to the dataset at PATH. Without `--auto-accept`, the operator is shown the proposed `GoldSample` and prompted to accept/reject/edit.

#### Scenario: Interactive add

- **WHEN** `peer dataset add https://github.com/owner/repo/pull/N --dataset my_dataset.jsonl` is invoked
- **THEN** the CLI prints the classified comments and proposed gold defects, prompts the operator to confirm, and on confirmation writes to `my_dataset.jsonl`

#### Scenario: Auto-accept add

- **WHEN** the same invocation includes `--auto-accept`
- **THEN** the sample is written directly without prompting; the stored sample's `metadata.spot_checked` is `False`

### Requirement: `peer dataset list` shows dataset contents

The framework SHALL implement `peer dataset list [--dataset PATH] [--show-classifications]` that prints a one-line-per-sample summary of the dataset (pr_url, defect count, spot-checked status, curation date).

#### Scenario: List summary

- **WHEN** `peer dataset list --dataset my_dataset.jsonl` is invoked on a dataset with 3 samples
- **THEN** the output is 3 lines (one per sample) with summary fields, plus a header / footer count

#### Scenario: List with classifications

- **WHEN** `peer dataset list --show-classifications` is added
- **THEN** each sample's line is followed by indented per-defect lines showing path, severity, category, and a truncated description

### Requirement: `peer dataset show` prints one full sample

The framework SHALL implement `peer dataset show <pr_url> [--dataset PATH]` that prints the full `GoldSample` record (all defects, all metadata, full descriptions).

#### Scenario: Show known sample

- **WHEN** `peer dataset show https://github.com/owner/repo/pull/N --dataset my_dataset.jsonl` is invoked for a sample in the dataset
- **THEN** the full record is printed (or JSON-pretty-printed) to stdout

#### Scenario: Show missing sample

- **WHEN** the PR URL is not in the dataset
- **THEN** the CLI exits non-zero with a clear "not found" message

### Requirement: Legacy entry point stays functional

The framework SHALL keep `python -m peer.review <pr_url>` working as a thin forwarder to `peer review <pr_url>` so existing scripts and documentation don't break.

#### Scenario: Legacy forward

- **WHEN** `python -m peer.review https://github.com/owner/repo/pull/N` is invoked
- **THEN** the behavior is identical to `peer review https://github.com/owner/repo/pull/N`

### Requirement: CLI errors map to non-zero exit codes

All CLI subcommands SHALL exit non-zero (1 for usage errors, 2 for runtime failures) on any error condition, with the error message printed to stderr.

#### Scenario: Invalid PR URL

- **WHEN** `peer review not-a-url` is invoked
- **THEN** the CLI prints an `InvalidPRURL` error to stderr and exits with code 2

#### Scenario: Missing required argument

- **WHEN** `peer eval --baseline path-without-dataset` would attempt to eval without a default dataset and PATH is also unreadable
- **THEN** the CLI prints a usage error to stderr and exits with code 1
