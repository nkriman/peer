## Why

Reverse-engineering The-PR-Agent/pr-agent (`docs/pr_agent_reverse_engineering.md`) surfaced two prompt-only changes that should land *before* the other 5 in-flight changes — because they affect every downstream eval number:

1. **Diff format with numbered new-file lines.** peer currently passes raw unified-diff hunks. The agent counts line numbers by hand and gets them wrong (verified empirically: PR 7677 reasoning cited "line 442" when ground truth was line 444). PR-Agent's `__new hunk__` / `__old hunk__` format with prepended new-file line numbers makes this mechanically impossible.

2. **Calibration prompt language.** PR-Agent's "Determining what to flag" + "Constructing comments" sections are materially better-engineered than peer's. They directly address the failure modes we measured: hallucinated rationale, speculative low-confidence flags, severity over-statement (+0.75 mean delta in peer's last run).

Landing this change first means subsequent eval comparisons (eval-metrics-v01 baselines, conventions experiments, benchmark-v01 numbers) are all against the improved prompt, not the current one. Ordering matters.

## What Changes

- Replace peer's `format_prompt` diff rendering with PR-Agent's `__new hunk__` / `__old hunk__` format with prepended new-file line numbers.
- Lift PR-Agent's two calibration sections into `DEFAULT_SYSTEM_PROMPT`, adapted to peer's Comment schema (peer's `body` + `rationale` fields replace PR-Agent's `issue_content`).
- Cite Apache 2.0 attribution to PR-Agent in the prompt file header.
- Re-run eval against the v2 reference dataset to establish the new baseline.

## Capabilities

### Modified Capabilities

- `pr-review-agent` (from `agent-v01`): `format_prompt` diff section rewritten; `DEFAULT_SYSTEM_PROMPT` adds two new calibration subsections. No Protocol/schema changes.

### New Capabilities

None.

## Impact

- **Code**: changes to `src/peer/prompts.py` only. ~80 LOC total (40 LOC for diff format, 40 LOC for prompt language).
- **No new dependencies.** No new tests required (existing tests use mocked LLM responses; the prompt content isn't exercised by unit tests). Manual verification via eval re-run.
- **No schema changes.** Reports and dataset format are unchanged.
- **Expected eval deltas vs v2 baseline:**
  - `severity_calibration`: closer to 0 (less over-severing)
  - Hallucinated line-number rate: should drop to ~0 (the diff format prevents it)
  - Comments per PR: may decrease (calibration prompt discourages low-confidence flags)
  - Detection rate / precision: should be neutral or up
- **Out of scope**: every other PR-Agent borrow (those land in their respective changes per `docs/pr_agent_reverse_engineering.md`).
