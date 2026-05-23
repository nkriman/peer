## 1. Diff format rewrite

- [ ] 1.1 Implement `_render_hunk_pragent_format(hunk: ContextHunk) -> str` in `src/peer/prompts.py`. Parses `hunk.diff_text` into a list of (op, content, new_line_no_or_None) tuples; renders the `__new hunk__` section with right-aligned new-file line numbers; renders `__old hunk__` if any removals exist; preserves the `@@ ... @@` context header.
- [ ] 1.2 Replace the current diff rendering inside `format_prompt` (the section that emits the `### {h.path}` header followed by the `\`\`\`diff ... \`\`\`` block) with the new format.
- [ ] 1.3 Keep the `Surrounding code from <path> at head:` block as-is — it's complementary, not redundant, and the agent uses it to reason about pre-existing code structure.

## 2. Calibration prompt update

- [ ] 2.1 Update `DEFAULT_SYSTEM_PROMPT` in `src/peer/prompts.py`. Replace the current "Rules:" section with two new subsections — "Determining what to flag:" and "Constructing comments:" — using the exact wording from `openspec/changes/prompt-quality-v01/design.md` Decision 2.
- [ ] 2.2 Preserve the codebase-context references (per `agent-v01` Decision 13) — the new sections augment, not replace, the codebase-context guidance.
- [ ] 2.3 Preserve the existing "Do NOT comment on lines outside the diff hunks. Do NOT invent file paths" guardrails — these are peer-specific and orthogonal to PR-Agent's calibration language.

## 3. Attribution

- [ ] 3.1 Update the `src/peer/prompts.py` module docstring to credit The-PR-Agent/pr-agent (Apache License 2.0, Qodo) for the adapted prompt language and diff format. Include pointer to `docs/pr_agent_reverse_engineering.md`.

## 4. Verification

- [ ] 4.1 Run `pytest tests/` — all existing tests should still pass (prompt content isn't unit-tested; existing tests mock LLM responses).
- [ ] 4.2 Re-run `peer eval --dataset dataset/reference/django_pydantic_v2.jsonl --out data/eval_runs/reference_v2_sonnet46_prompt_quality_v01.json`.
- [ ] 4.3 Compare against `data/eval_runs/reference_v2_sonnet46.json` baseline. Write `data/eval_runs/prompt_quality_v01_comparison.md` documenting deltas.
- [ ] 4.4 Spot-check one or two PRs (especially PR 7677 — the line-442/444 case) to verify the diff format change actually surfaces correct line numbers in peer's reasoning. Document in the comparison doc.
