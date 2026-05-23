## 1. Schema extension

- [ ] 1.1 Add `suggestion: Optional[str] = None` to `Comment` in `src/peer/types.py`.
- [ ] 1.2 Update `src/peer/__init__.py` if export shape changes (likely no change — Comment already exported).

## 2. Reviewer tool schema

- [ ] 2.1 Update `_COMMENT_TOOL` schema in `src/peer/reviewers.py` to include `suggestion` as optional nullable string with description.
- [ ] 2.2 Parse `suggestion` field from tool-call output in `ClaudeReviewer.review`.
- [ ] 2.3 (OpenAIReviewer is deferred per agent-v01 task 3.3 — when implemented, mirror this schema.)

## 3. Default system prompt

- [ ] 3.1 Update `DEFAULT_SYSTEM_PROMPT` in `src/peer/prompts.py` to add a section explaining when to include a `suggestion` and when NOT to. Use the criteria from design.md Decision 2.

## 4. Prompt format helper

- [ ] 4.1 Update `format_prompt(ctx, cc)` in `src/peer/prompts.py` to document the `suggestion` field in the input-schema description so the agent knows it's available.

## 5. Validation

- [ ] 5.1 Add heuristic check in `Agent._validate_comments`: if comment has `suggestion` and the newline count in `suggestion` exceeds the new-file line span of the matching hunk, log WARNING (don't drop).

## 6. CLI rendering

- [ ] 6.1 Update `_cmd_review` in `src/peer/cli.py` to render Comments with `suggestion` as their normal output followed by a delimited block:
      ```
      --- suggested change ---
      <suggestion>
      -------------------------
      ```

## 7. New metric

- [ ] 7.1 Implement `SuggestionRate` in `src/peer/eval/metrics.py` — per-sample `value = n_with_suggestion / n_total` (None when `n_total == 0`); aggregate sum-of-sums.
- [ ] 7.2 Export `SuggestionRate` from `src/peer/eval/__init__.py`.
- [ ] 7.3 Add `SuggestionRate()` to the default metric list in `EvalRunner.__init__` after the metrics introduced by `eval-metrics-v01`.

## 8. Reporting

- [ ] 8.1 Update `render_summary` in `src/peer/eval/report.py` to render `suggestion_rate` in the Headline section alongside `comments_per_pr` (suggestion rate is a noise-vs-applyability indicator).

## 9. Tests

- [ ] 9.1 `tests/test_types.py` (new or existing) — Comment with suggestion round-trips; Comment without suggestion has `suggestion is None`.
- [ ] 9.2 `tests/test_reviewers.py` (new or existing) — mock Anthropic response with tool-call output containing `suggestion`; verify parsed into the Comment.
- [ ] 9.3 `tests/test_agent.py` — validation logs WARNING when suggestion exceeds hunk lines; doesn't drop the comment.
- [ ] 9.4 `tests/test_cli.py` — `peer review` output contains suggestion delimiter when present; omits when absent. Use captured output.
- [ ] 9.5 `tests/test_metrics_v2.py` — SuggestionRate per-sample + aggregate fixtures.
- [ ] 9.6 `tests/test_report.py` — render_summary headline section includes `suggestion_rate`.

## 10. Verification

- [ ] 10.1 Re-run `peer eval --dataset dataset/reference/django_pydantic_v2.jsonl` with patch suggestions enabled (default after this change). Save to `data/eval_runs/reference_v2_sonnet46_with_suggestions.json`. Report SuggestionRate alongside the other metrics; show CLI output for one PR with a real `--- suggested change ---` block to validate end-to-end.
