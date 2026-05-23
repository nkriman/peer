## Context

Patch-suggestion output is one of the consistent usability differentiators identified in `docs/competitive_landscape_research.md` — CodeRabbit's 68.3% applyable-diff rate is a real adoption advantage. The implementation surface is small: add an optional field to `Comment`, update the tool schema, update the prompt, update the renderer. The bigger design question is *when* and *how confidently* the agent should produce suggestions.

## Goals / Non-Goals

**Goals:**
- `Comment.suggestion` is an optional field; agents that produce it get the benefit, agents that don't (existing custom Reviewer impls) keep working.
- Default prompt instructs the agent to use `suggestion` for small, concrete, confident fixes — not for vague suggestions ("consider refactoring") or large rewrites.
- CLI rendering presents suggestions as code blocks the user can copy/paste.
- Validation prevents suggestions whose proposed replacement is grossly misaligned with the diff (line spans, etc.).
- Eval metric (`SuggestionRate`) tracks the rate so framework users can A/B prompt changes intended to increase applyability.

**Non-Goals:**
- Auto-apply suggestions / open PRs / push commits (peer stays read-only).
- Multi-file suggestions (atomic single-hunk patches only).
- Live validation (running tests / type-check on the suggested code). Macroscope's closed-loop fix-and-validate is its differentiator; matching it is its own change.
- Markdown-comment suggestions for `peer review` CLI output (we just render as fenced code; not GitHub-API integrated yet).

## Decisions

### 1. Field shape: optional string, no metadata

`Comment.suggestion: Optional[str] = None`. The string IS the proposed replacement for the comment's anchored line range. No `start_line / end_line` metadata — the comment's `line` (and implicit hunk context) define the anchor. Match GitHub's `\`\`\`suggestion` block semantics: replaces N consecutive lines starting at `line`.

**Why not a structured `Suggestion` model?:** the string is what GitHub renders directly. Adding structure inside (e.g., `Suggestion(replacement_text, lines_replaced)`) doesn't help because the agent's natural output is just the replacement text.

**Single-line vs multi-line:** the field is just a string; both work. The convention is one line by default; multi-line for blocks. GitHub's `\`\`\`suggestion` block can span up to ~50 lines comfortably.

### 2. Prompt-level "when to include" guidance

The default system prompt's `suggestion` instructions:

> Include a `suggestion` field when ALL of the following are true:
> 1. The fix is concrete (not "consider X" but specific replacement code).
> 2. The fix is small (≤5 lines of replacement, typically 1-3).
> 3. You are confident the suggested code is syntactically valid and consistent with the file's style.
> 4. The fix replaces a single contiguous range, not scattered edits across the file.
>
> DO NOT include `suggestion` for:
> - Vague concerns ("consider refactoring this", "should be cleaner")
> - Large rewrites
> - Cross-file changes
> - Concerns where the right fix is "discuss with the team"

**Why constraints rather than encouragement:** the failure mode for suggestions is "agent generates a plausible-looking diff that breaks the code." Better to underuse `suggestion` than overuse it.

### 3. Tool schema update

The Anthropic tool schema for `post_review_comments` gains:

```json
"suggestion": {"type": ["string", "null"], "description": "Optional ```suggestion``` block: the proposed replacement code for the anchored lines. Single contiguous block; null if no concrete suggestion."}
```

OpenAI structured-output schema gets the analogous field. Existing Comments without `suggestion` still validate (optional field).

### 4. Validation: suggestion in hunk only

`Agent._validate_comments` (existing pass) already drops Comments whose `path` is unknown or whose `line` is outside any hunk. Add: if `suggestion` is present, the number of newlines in the suggestion SHOULD NOT exceed the number of new-file lines in the surrounding hunk (warning, not drop). Reason: a multi-line suggestion can't reasonably replace more lines than the hunk contains; if it does, something is off.

**Why warning not drop:** the heuristic is loose. The comment + reasoning is still valuable even if the suggestion is rejected by the user.

### 5. CLI rendering: suggestion as fenced block

`peer review` CLI output today shows:

```
[CRITICAL] path:line
  body text
  -- rationale
```

With suggestion, append:

```
[CRITICAL] path:line
  body text
  -- rationale
  --- suggested change ---
  <code block>
  -------------------------
```

Plain text formatting; no GitHub-specific markdown. Users who want to copy/paste into a GitHub review can do so manually.

### 6. New eval metric: SuggestionRate

`SuggestionRate` reports: of peer comments produced, what fraction included a `suggestion` field. Per-PR detail; sum-of-sums aggregate. Lightweight metric; helps A/B test prompt changes targeting applyability.

**Why include in default metric set:** matches CodeRabbit's `applyable-diff%` headline number, which the framework should be able to report so users can position their peer-built reviewer in the landscape.

### 7. Per-severity suggestion breakdown is opt-in

`PrecisionPerSeverity` (added in `eval-metrics-v01`) gets an optional `breakdown_by_suggestion: bool = False` parameter. When true, the per-tier output also splits by `has_suggestion` → useful for analysis but noisy by default.

## Risks / Trade-offs

- **[Risk]** Agents generate plausible-looking diffs that introduce subtle bugs (wrong indentation, missed edge case, breaks adjacent code). **Mitigation:** prompt constraints + validation warning when suggestion shape is wrong. Don't auto-apply; user reviews before committing. Reserve closed-loop fix-and-validate for a future change.
- **[Risk]** Token cost increase — every suggestion adds ~50-200 output tokens. **Mitigation:** the prompt caps suggestions at small concrete fixes; large rewrites are forbidden. Net token delta is modest (estimated +5-15% per PR with suggestions).
- **[Risk]** Suggestion field breaks custom Reviewer implementations that built `Comment` from a dict. **Mitigation:** field is optional with default `None`; backward compat preserved. Document in release notes.
- **[Risk]** Multi-line suggestions misalign with hunk line ranges (off-by-one in newline counts). **Mitigation:** validation logs WARNING when count seems off; don't auto-correct (the agent's intent isn't always derivable).

## Open Questions

None blocking. Deferred:
- GitHub API integration (post suggestions as actual review comments via `gh pr review`) — would need a `peer post-review` CLI subcommand; deferred.
- Closed-loop validation (run tests on suggestion) — matches Macroscope's differentiator; meaningful new change.
- Multi-file atomic suggestions (e.g., "rename foo to bar in 3 files") — would need a different Comment shape; deferred.
