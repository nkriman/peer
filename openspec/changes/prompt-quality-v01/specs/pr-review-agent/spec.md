## MODIFIED Requirements

### Requirement: Default system prompt uses PR-Agent-style calibration language

The default system prompt (`DEFAULT_SYSTEM_PROMPT` in `src/peer/prompts.py`) SHALL include two subsections — "Determining what to flag" and "Constructing comments" — adapted from The-PR-Agent/pr-agent's `pr_reviewer_prompts.toml`. The previous flat "Rules:" section is removed; the codebase-context references (`modified_symbols`, `call_sites`, `related_tests`, `untested_files`) and the per-section diff-hunk + invent-file-path defensive instructions are preserved.

#### Scenario: Calibration subsections present

- **WHEN** an `Agent` is instantiated with no `system_prompt` override
- **THEN** `agent.system_prompt` contains both the literal strings "Determining what to flag:" and "Constructing comments:"
- **AND** contains the phrase "do not flag" at least three times (distinct rules in the "Determining what to flag" section)

#### Scenario: Anti-speculation language present

- **WHEN** an `Agent` is instantiated with no system_prompt override
- **THEN** `agent.system_prompt` contains the literal string "If you cannot confidently explain why something is a problem with a concrete scenario, do not flag it"

#### Scenario: Codebase-context references preserved

- **WHEN** an `Agent` is instantiated with no system_prompt override
- **THEN** `agent.system_prompt` contains the literal strings `modified_symbols`, `call_sites`, `related_tests`, and `untested_files` (per `agent-v01` Decision 13 — Decision 13 is not weakened by this change)

### Requirement: Diff section renders using new-hunk and old-hunk sections with new-file line numbers

`format_prompt(ctx, cc)` SHALL render each `ContextHunk` using a labeled `__new hunk__` / `__old hunk__` section format with new-file line numbers prepended to each `__new hunk__` line. The `__old hunk__` section MAY be omitted when the hunk has no removed lines. Line numbers are right-aligned (4-char minimum width). Old-hunk lines do NOT carry line numbers. The `@@ ... @@` header preserves the function-context hint from `git diff`. The full format specification with examples appears in `openspec/changes/prompt-quality-v01/design.md` Decision 1.

#### Scenario: New hunk lines are numbered

- **WHEN** `format_prompt(ctx, cc)` is called on a `Context` with a `ContextHunk` for `src/foo.py` whose `new_start=10` and `new_lines=4`
- **THEN** the rendered output contains the literal `__new hunk__` header
- **AND** the four lines following the header are prefixed with `   10  `, `   11  `, `   12  `, `   13  ` respectively

#### Scenario: Old hunk omitted when no removals

- **WHEN** the hunk's diff_text contains no lines starting with `-`
- **THEN** the rendered output for that hunk does NOT contain the literal `__old hunk__` header

#### Scenario: Hunk header carries function context

- **WHEN** the hunk's diff_text starts with `@@ -10,4 +10,4 @@ def foo():`
- **THEN** the rendered output contains a line beginning with `@@ ... @@ def foo():` (the line ranges normalized to `...`, the function context preserved)

#### Scenario: Numbered format eliminates line-citation drift

- **WHEN** the agent is given a numbered-format diff and produces a comment with a `line` field
- **THEN** for any peer comment that references a specific line in its body, the cited line number SHOULD match the actual line number of the referenced code (no off-by-N drift)
- *(This is a quality expectation, not a hard test — verified empirically via re-eval comparison.)*

### Requirement: Attribution to PR-Agent in the prompts module

The `src/peer/prompts.py` module SHALL include a header docstring or comment crediting The-PR-Agent/pr-agent (Apache 2.0, Qodo) for the adapted prompt language and diff format, with a pointer to the reverse-engineering analysis doc.

#### Scenario: Attribution comment present

- **WHEN** the contents of `src/peer/prompts.py` are read
- **THEN** the file's module docstring contains the literal string "PR-Agent" (or "pr-agent") and the literal string "Apache License 2.0" or "Apache 2.0"
