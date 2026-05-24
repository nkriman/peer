## ADDED Requirements

### Requirement: Comment schema gains optional `suggestion` field

`Comment` SHALL gain an optional field `suggestion: Optional[str] = None`. When present, it contains the proposed replacement text for the anchored line range. Existing Comments without `suggestion` continue to validate.

#### Scenario: Comment with suggestion validates

- **WHEN** a Comment is constructed with all required fields plus `suggestion="if x is not None:\n    do_thing()"`
- **THEN** the Comment validates and `comment.suggestion` round-trips through `model_dump` / `model_validate`

#### Scenario: Comment without suggestion validates

- **WHEN** a Comment is constructed with no `suggestion` argument
- **THEN** `comment.suggestion is None`

### Requirement: Default system prompt instructs when to include suggestions

The default system prompt SHALL include explicit guidance on when to include a `suggestion`: concrete fixes only, ≤5 lines of replacement, syntactically-valid code, single contiguous range. The prompt SHALL also forbid suggestions for vague / large / cross-file concerns.

#### Scenario: Default prompt contains suggestion guidance

- **WHEN** an Agent is instantiated with no system_prompt override
- **THEN** `agent.system_prompt` contains both the "when to include suggestion" criteria AND the explicit "DO NOT include suggestion for" forbiddances

### Requirement: ClaudeReviewer tool schema includes suggestion field

The Anthropic tool-call schema used by `ClaudeReviewer` SHALL include `suggestion` as an optional nullable string field with description.

#### Scenario: Tool schema includes suggestion

- **WHEN** `ClaudeReviewer` invokes Anthropic's messages API
- **THEN** the tools input_schema for `post_review_comments` includes `suggestion: {"type": ["string", "null"], "description": "..."}`

### Requirement: Comment-validation pass tolerates and warns about misaligned suggestions

`Agent._validate_comments` SHALL accept Comments with `suggestion` regardless of suggestion content but SHALL log a WARNING when the suggestion has more newlines than the surrounding hunk has new-file lines (heuristic for "suggestion is misaligned").

#### Scenario: Well-aligned suggestion accepted

- **WHEN** a Comment has `line=42, suggestion="x = y"` and the hunk for that file at lines 40-44 contains the line being commented on
- **THEN** the comment passes validation; no warning

#### Scenario: Misaligned suggestion warned

- **WHEN** a Comment has a 10-line suggestion but is anchored to a 2-line hunk
- **THEN** a `WARNING peer.agent: suggestion span (10 lines) exceeds hunk new-file lines (2) for <path>:<line>` is logged
- **AND** the comment is still included in the Review (heuristic, not a drop)

### Requirement: CLI renders suggestion as fenced block

`peer review` CLI output SHALL render Comments with a `suggestion` as their normal output followed by a clearly-delimited code block of the suggested replacement.

#### Scenario: CLI suggestion rendering

- **WHEN** `peer review <pr_url>` runs and produces a Comment with `suggestion="x = y"`
- **THEN** the stdout output contains a "--- suggested change ---" delimiter, the suggested text on its own line(s), and a closing "-------------------------" delimiter

#### Scenario: CLI omits delimiter when no suggestion

- **WHEN** a Comment has no suggestion
- **THEN** no "--- suggested change ---" delimiter appears in the output for that Comment

### Requirement: SuggestionRate metric reports applyability

The framework SHALL ship a `SuggestionRate` implementation of `EvalMetric` that reports the fraction of peer comments that include a `suggestion` field, both per-sample and aggregated sum-of-sums.

#### Scenario: SuggestionRate single sample

- **WHEN** peer produces 4 comments on one sample, of which 2 have `suggestion`
- **THEN** the per-sample `MetricResult.value` is `0.5` and `per_sample_detail` includes `n_with_suggestion=2`, `n_total=4`

#### Scenario: SuggestionRate aggregate

- **WHEN** `EvalRunner.run()` completes a run where total peer comments across all samples is 30, of which 18 had `suggestion`
- **THEN** the aggregate `metric_values["suggestion_rate"]` is `0.6`

#### Scenario: SuggestionRate handles no-comments case

- **WHEN** a sample has zero peer comments
- **THEN** the per-sample `MetricResult.value` is `None` with a `notes` field explaining no comments to evaluate

### Requirement: Comment schema gains issue_header field

`Comment` SHALL gain an optional `issue_header: Optional[str] = None` field — a short categorical label (1-3 words, e.g., "Possible Bug", "Performance Concern", "Test Coverage"). Adapted from PR-Agent's KeyIssuesComponentLink schema.

#### Scenario: Comment with issue_header validates

- **WHEN** `Comment(path="a.py", line=1, severity="important", body="x", rationale="y", issue_header="Possible Bug")` is constructed
- **THEN** the comment validates and `comment.issue_header == "Possible Bug"`

#### Scenario: CLI prepends issue_header

- **WHEN** `peer review` outputs a Comment with `issue_header="Possible Bug"`
- **THEN** the rendered line begins with `[Possible Bug]` BEFORE the severity tag (e.g., `[Possible Bug] [IMPORTANT] path:line`)

### Requirement: Comment schema gains end_line for line ranges

`Comment` SHALL gain an optional `end_line: Optional[int] = None`. When present, `end_line` SHALL be ≥ `line` and within the same hunk. Single-line comments leave `end_line=None`; multi-line comments set both.

#### Scenario: Multi-line comment with valid range

- **WHEN** a Comment is constructed with `line=10, end_line=15` and the corresponding hunk has new-file lines 10-15
- **THEN** validation passes; the comment's effective range is lines 10-15 inclusive

#### Scenario: end_line out of hunk fails validation, triggers retry

- **WHEN** a Comment has `line=10, end_line=20` but the hunk only covers lines 10-15
- **THEN** the comment is flagged as invalid; if `retries['output'] > 0`, fed back to the agent for retry; otherwise dropped with WARNING (per `peer-deps-v01` validation-retry pattern)

#### Scenario: end_line backwards fails validation

- **WHEN** `end_line=5` but `line=10`
- **THEN** validation fails (end_line must be ≥ line)

### Requirement: Suggestion validation triggers retry on misalignment

When a Comment has `suggestion` and the newline count exceeds the hunk's new-file lines, the validation pass SHALL flag the Comment as invalid. With `retries['output'] > 0` (per `peer-deps-v01`), the framework SHALL feed the validation error back to the agent for retry. With retry budget exhausted, the suggestion is dropped (the Comment itself is kept) with a WARNING.

#### Scenario: Misaligned suggestion retried

- **GIVEN** Agent has `retries={"output": 1}`
- **WHEN** the reviewer returns a Comment with a 10-line suggestion attached to a 2-line hunk on the first call, and a corrected 2-line suggestion on retry
- **THEN** the final Review contains the Comment with the corrected suggestion; `Review.usage.n_retries == 1`

### Requirement: IssueHeaderDistribution metric

The framework SHALL ship `IssueHeaderDistribution` as a default metric. Returns a dict aggregate of how many peer comments fall under each `issue_header` value across the dataset. Useful for understanding what categories of issues peer flags vs misses.

#### Scenario: Distribution reported

- **WHEN** EvalRunner runs over 10 samples and peer produces 25 comments total — 8 with `issue_header="Possible Bug"`, 12 with "Style Nit", 5 with "Performance"
- **THEN** `metric_values["issue_header_distribution"]` is None but `metric_details["issue_header_distribution"]` contains `{"Possible Bug": 8, "Style Nit": 12, "Performance": 5, "(none)": 0}`

### Requirement: SuggestionRate added to default metric set

`EvalRunner` default metrics SHALL include `SuggestionRate` after the metrics added in `eval-metrics-v01`. Full default order: `[DetectionRate, CommentsPerPR, PrecisionPerSeverity, SuggestionRate, MeanPerPRRecall, NoveltyRate, SeverityCalibration]`.

#### Scenario: Default eval reports SuggestionRate

- **WHEN** `EvalRunner(reviewer, dataset).run()` is called with default metrics
- **THEN** the returned `EvalReport.summary.metric_values` includes the `suggestion_rate` key
