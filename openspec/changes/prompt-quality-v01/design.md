## Context

Two prompt-only edits, both lifted from PR-Agent (Apache 2.0 → MIT compatible). The reverse-engineering analysis in `docs/pr_agent_reverse_engineering.md` describes them as "PROMPT-WIN-1" and "PROMPT-WIN-2".

## Goals / Non-Goals

**Goals:**
- Diff format that makes line references mechanically correct.
- Calibration prompt that reduces speculative flags + over-severing.
- Foundation for downstream eval comparisons (everything from this point forward compares against this improved prompt baseline).

**Non-Goals:**
- Other PR-Agent patterns (those go in their respective changes).
- Jinja2 templating refactor (deferred).
- Schema changes.

## Decisions

### 1. Diff format: PR-Agent's `__new hunk__` / `__old hunk__` with numbered new-file lines

For each diff hunk, render as:

```
## File: 'path/to/file.py'

@@ ... @@ def func1():
__new hunk__
11  unchanged code line0
12  unchanged code line1
13 +new code line2 added
14  unchanged code line3
__old hunk__
 unchanged code line0
 unchanged code line1
-old code line2 removed
 unchanged code line3
```

Key properties:
- Each line in `__new hunk__` is prepended with its NEW-FILE line number (right-aligned to 4 chars, then space).
- `__old hunk__` lines are NOT numbered (no useful line numbers in the diff for deleted lines).
- The `@@ ... @@` header is preserved (the function-context hint from `git diff` is valuable).
- If a hunk has no removed lines, the `__old hunk__` section is omitted entirely.
- Surrounding code (the ±N lines peer fetches separately via `context._add_surrounding_code`) is folded into the `__new hunk__` numbering — the surrounding lines get their actual file line numbers.

Implementation: parse the unified diff hunk into (op, line) tuples, then render the two sections. The `unidiff` library already gives us this structure via `Hunk.source_lines()` / `target_lines()`.

### 2. Calibration prompt language: lift from PR-Agent's `pr_reviewer_prompts.toml`

Replace peer's current "Rules:" section in `DEFAULT_SYSTEM_PROMPT` with two new subsections borrowed near-verbatim from PR-Agent:

**Determining what to flag:**
> - For clear bugs and security issues, be thorough. Do not skip a genuine problem just because the trigger scenario is narrow.
> - For lower-severity concerns, be certain before flagging. If you cannot confidently explain why something is a problem with a concrete scenario, do not flag it.
> - Each issue must be discrete and actionable, not a vague concern about the codebase in general.
> - Do not speculate that a change might break other code unless you can identify the specific affected code path from the diff context.
> - Do not flag intentional design choices or stylistic preferences unless they introduce a clear defect.
> - When confidence is limited but the potential impact is high (e.g., data loss, security), report it with an explicit note on what remains uncertain. Otherwise, prefer not reporting over guessing.

**Constructing comments:**
> - Be direct about why something is a problem and the realistic scenario where it manifests.
> - Communicate severity accurately. Do not overstate impact. If an issue only arises under specific inputs or environments, say so upfront.
> - Keep each issue description concise. Write so the reader grasps the point immediately without close reading.
> - Use a matter-of-fact, helpful tone. Avoid accusatory language, excessive praise, or filler phrases like 'Great job', 'Thanks for'.

Keep peer's existing references to codebase context fields (`modified_symbols`, `call_sites`, `related_tests`, `untested_files`) — those are peer-specific and orthogonal. Also keep the "do NOT comment on lines outside the diff hunks" + "do NOT invent file paths" guardrails — they're peer-specific defensive instructions PR-Agent doesn't need.

### 3. Attribution

Add a header comment to `src/peer/prompts.py`:

```python
"""...
Portions of DEFAULT_SYSTEM_PROMPT and the diff-format renderer are
adapted from The-PR-Agent/pr-agent (Apache License 2.0, copyright Qodo).
See docs/pr_agent_reverse_engineering.md for the reverse-engineering
analysis and rationale.
"""
```

### 4. Validate by re-running eval

After landing this change, re-run `peer eval --dataset dataset/reference/django_pydantic_v2.jsonl` and compare against `data/eval_runs/reference_v2_sonnet46.json`. Save the new baseline as `data/eval_runs/reference_v2_sonnet46_prompt_quality_v01.json`. Document the delta in `data/eval_runs/prompt_quality_v01_comparison.md`.

This new baseline becomes the reference point for `eval-metrics-v01`, `peer-config-v01`, and downstream changes.

## Risks / Trade-offs

- **[Risk]** New diff format may confuse models trained on raw unified diffs. **Mitigation:** PR-Agent has shipped this format to 11.3k stars worth of users on the same Claude/OpenAI/etc. models peer uses; empirical evidence is strong. Re-eval validates.
- **[Risk]** The calibration prompt may suppress real flags peer was catching. **Mitigation:** the eval re-run will surface this; if recall drops materially we can rebalance. The risk is asymmetric — fewer high-quality comments is better than more noisy ones for user adoption.
- **[Risk]** The numbered-line format adds prompt tokens. **Mitigation:** at ~5 chars per line + ~50 lines per typical hunk, the overhead is ~250 tokens per file. On a small PR with 3-4 files, that's ~1k tokens — well within budget.

## Open Questions

None.
