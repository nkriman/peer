## Why

CodeRabbit's 68.3% applyable-diff rate (independent dev.to study) is a major usability advantage. When a reviewer can post `\`\`\`suggestion ...\`\`\`` blocks that GitHub renders as one-click "commit suggestion" buttons, the friction of acting on feedback drops dramatically. peer currently only describes concerns; the author has to read the comment, mentally translate it to a code change, and edit manually.

This change adds an optional `suggestion` field to `Comment` so the agent can include a patch block when the fix is concrete + small + safe. Macroscope is differentiated by closed-loop fix-and-validate; we don't aim for that here, but we do match CodeRabbit's "include the diff" pattern.

## What Changes

- Extend `Comment` schema with `suggestion: Optional[str] = None` — when present, contains the proposed replacement text for the lines being commented on (typically a single contiguous block; can be multi-line).
- Update the default system prompt to instruct the agent to include a `suggestion` when (a) the fix is small (≤5 lines), (b) the fix is concrete (not "consider refactoring"), and (c) the agent is confident the suggested code compiles / passes type checks.
- Update the Anthropic tool schema to optionally accept the `suggestion` field.
- Update `format_prompt` to label the `suggestion` field in the agent's input schema documentation.
- Update CLI `peer review` rendering to display suggestions as fenced code blocks beneath each comment.
- Update eval metrics:
  - Add `SuggestionRate` metric: % of peer comments that include a suggestion.
  - Extend `PrecisionPerSeverity` reporting to also break down by `has_suggestion` (informational).
- Update validation: a `suggestion` cannot reference lines outside the diff hunk it's attached to.

## Capabilities

### Modified Capabilities

- `pr-review-agent` (from `agent-v01`): `Comment` schema gains optional `suggestion: Optional[str]`; default system prompt updated; tool schema includes `suggestion`; comment-validation rejects suggestions that span outside the hunk.
- `eval-runner` (from `eval-v01`): adds `SuggestionRate` to default metric set; existing `EvalSampleResult.review_summary` includes suggestion count.

## Impact

- **Code**: updates to `src/peer/types.py` (extend Comment), `src/peer/reviewers.py` (extend tool schema), `src/peer/prompts.py` (default prompt + format_prompt), `src/peer/agent.py` (validate suggestion in-hunk), `src/peer/cli.py` (render suggestions in `peer review` output), `src/peer/eval/metrics.py` (new SuggestionRate), `src/peer/eval/runner.py` (add to default metric set).
- **Schema bump:** `Comment` gains an optional field. Old `Review` JSON dumps still load; field defaults to `None`. `EvalReport.report_schema_version` stays at `1.0`.
- **No new deps.**
- **Out of scope**: actually applying suggestions / opening commits (peer remains read-only). Multi-file suggestions (single-hunk only for v0.1). Suggestion validation via running tests / type-checker (deferred; could fit into a future "closed loop" change inspired by Macroscope).
