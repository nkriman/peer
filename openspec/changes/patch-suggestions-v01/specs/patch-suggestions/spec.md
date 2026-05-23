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

### Requirement: SuggestionRate added to default metric set

`EvalRunner` default metrics SHALL include `SuggestionRate` after the metrics added in `eval-metrics-v01`. Full default order: `[DetectionRate, CommentsPerPR, PrecisionPerSeverity, SuggestionRate, MeanPerPRRecall, NoveltyRate, SeverityCalibration]`.

#### Scenario: Default eval reports SuggestionRate

- **WHEN** `EvalRunner(reviewer, dataset).run()` is called with default metrics
- **THEN** the returned `EvalReport.summary.metric_values` includes the `suggestion_rate` key
