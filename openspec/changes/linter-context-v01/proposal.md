## Why

CodeRabbit's Macroscope-benchmark detection (46%) comes partly from its **40+ integrated linters** (ESLint, Semgrep, ruff, mypy, etc.) feeding signal into the LLM. peer currently feeds only tree-sitter-extracted symbols and ast-grep call sites into its context. Adding linter output gives the agent broad mechanical coverage cheaply — the linters are already authoritative on style, naming, simple correctness — and lets the agent focus its LLM reasoning on the genuinely-LLM-shaped issues.

The cost is low: ruff and mypy run in seconds, are widely installed, and produce structured output. Most importantly: a defect like "missing trailing comma" should NEVER cost a Claude call to flag — it should be a linter line that gets surfaced as-is.

## What Changes

- Add `Linter` Protocol with `lint(repo_path: Path, target_files: list[str]) -> list[LinterFinding]`.
- Ship two default implementations: `RuffLinter` (general Python linting) and `MypyLinter` (type checking). Both shell out to the tool when on `PATH`; degrade gracefully when absent.
- Extend `CodebaseContext` to include a `linter_findings: list[LinterFinding]` field, populated per modified Python file by the configured Linters.
- Update `gather_codebase_context` to run the configured linters on the modified Python files.
- Extend the prompt formatter to include a labeled `## LINTER FINDINGS` section so the agent sees the linter output explicitly.
- Update the default system prompt (Decision 13 of agent-v01) to direct the agent to *consult* linter findings — prefer surfacing linter-flagged issues as-is over re-discovering them — and to suppress its own duplicate flags for issues a linter already caught.
- Linters are configured via `.peer.yaml` (per `peer-config-v01`): default-enabled list at the top of the config, can be disabled per-path.

## Capabilities

### New Capabilities

- `linter-context`: pluggable `Linter` Protocol + `RuffLinter` / `MypyLinter` defaults. Output is included in `CodebaseContext.linter_findings` and surfaced in the agent's prompt.

### Modified Capabilities

- `codebase-context` (from `agent-v01`): adds `linter_findings` field to `CodebaseContext`. The Protocol surface (`gather_codebase_context`) gains an optional `linters: list[Linter]` argument; defaults to `[]` so existing callers get no change.
- `pr-review-agent` (from `agent-v01`): default system prompt updated to reference linter findings as a context section. Agent's prompt-formatter renders the `## LINTER FINDINGS` section. No `Reviewer` Protocol change.

## Impact

- **Code**: new `src/peer/linters.py` (Linter Protocol + RuffLinter + MypyLinter). Updates to `src/peer/types.py` (add `LinterFinding`, extend `CodebaseContext`), `src/peer/codebase_context.py` (run linters in `gather_codebase_context`), `src/peer/prompts.py` (render linter section + update default prompt), `src/peer/config.py` (add `linters:` config section). New `tests/test_linters.py`.
- **Dependencies**: no new pip deps — ruff and mypy are shell-outs; if not installed, the linter logs a one-time WARNING and returns empty findings. Recommended in README's Requirements section.
- **Token budget**: linter findings add to `CodebaseContext` token budget (default 30,000). Tier-priority drops (per agent-v01 Decision 14 Token budget priority order) put linter findings BELOW `modified_symbols` and `call_sites` but ABOVE `related_tests` — they're highly compressed (each finding ~30 tokens) so usually fit.
- **Out of scope**: JavaScript/TypeScript linters (ESLint, etc.) — Python-only for v0.1. Multi-language linter framework comes in a follow-on. Auto-fix application from linter output (deferred; covered partly by `patch-suggestions-v01`).
