## 1. Schema

- [ ] 1.1 Add `LinterFinding` Pydantic model to `src/peer/types.py` with the documented fields.
- [ ] 1.2 Extend `CodebaseContext` in `src/peer/types.py` with `linter_findings: list[LinterFinding] = Field(default_factory=list)`.
- [ ] 1.3 Export `LinterFinding` from `src/peer/__init__.py`.

## 2. Linter Protocol + defaults

- [ ] 2.1 Create `src/peer/linters.py` with `Linter` Protocol.
- [ ] 2.2 Implement `RuffLinter`: `shutil.which("ruff")` check; subprocess `ruff check --output-format=json --quiet --no-cache <files>`; parse JSON output; project to `LinterFinding`; default severity_map covers F/E/W/B/S/etc rule prefixes.
- [ ] 2.3 Implement `MypyLinter`: similar pattern; subprocess `mypy --no-error-summary --show-error-codes --show-column-numbers --no-pretty <files>`; parse text output; project to `LinterFinding`.
- [ ] 2.4 Each linter logs one-time WARNING if CLI missing.
- [ ] 2.5 Each linter wraps subprocess call in try/except + 30s timeout; on failure log ERROR and return empty.

## 3. Integration with codebase context

- [ ] 3.1 Update `gather_codebase_context` signature: add `linters: Optional[list[Linter]] = None` parameter.
- [ ] 3.2 For Python modified files, run each linter; collect into `cc.linter_findings`.
- [ ] 3.3 Parallel linter execution via `concurrent.futures.ThreadPoolExecutor` with total 30s timeout.
- [ ] 3.4 Cap findings per file at `max_findings_per_file=50` (configurable); log truncations.
- [ ] 3.5 Update token-budget enforcement: drop order is `related_tests` → `linter_findings` (lowest severity first) → `call_sites`.

## 4. Prompt + agent integration

- [ ] 4.1 Update default system prompt in `src/peer/prompts.py` to name `linter_findings` per Decision 13 + add the "cite linter rule_id, don't re-discover" instruction.
- [ ] 4.2 Update `format_prompt(ctx, cc)` in `src/peer/prompts.py` to render a `## LINTER FINDINGS` section when non-empty, formatted as `[<linter> <rule_id> <severity>] <path>:<line> — <message>` per entry.
- [ ] 4.3 Update `Agent.review` to pass `self.config.enabled_linters()` (or empty list) to `gather_codebase_context`. Depends on `peer-config-v01` Task 4 being landed.

## 5. Config integration (depends on peer-config-v01)

- [ ] 5.1 Add `linters:` section schema to `PeerConfig` in `src/peer/config.py`. Each entry: `name`, `enabled` (default true), `severity_map` (dict).
- [ ] 5.2 Add `PeerConfig.enabled_linters() -> list[Linter]` resolver that returns `[RuffLinter(...)]` if no config OR if config enables ruff; analogous for mypy.
- [ ] 5.3 Default (empty config) enables ruff; not mypy (per design.md Decision 5).

## 6. Tests

- [ ] 6.1 `tests/test_linters.py` — RuffLinter parses fixture JSON output; MypyLinter parses fixture text output; CLI-missing fallback returns empty with WARNING; severity_map override.
- [ ] 6.2 `tests/test_codebase_context.py` (new or existing) — gather with custom Linter fixture populates `cc.linter_findings`; token-budget drops linter_findings before call_sites.
- [ ] 6.3 `tests/test_prompts.py` (new) — format_prompt with non-empty linter_findings renders the section; format_prompt with empty linter_findings omits it.
- [ ] 6.4 `tests/test_agent.py` — Agent with config enabling linters passes them to gather_codebase_context.

## 7. Docs

- [ ] 7.1 Update README's Requirements section: ruff (recommended) + mypy (optional) install instructions.
- [ ] 7.2 Add a section to `docs/framework_overview.md` documenting the Linter Protocol + how to write a custom Linter (e.g., for a private rules engine).

## 8. Verification

- [ ] 8.1 Re-run `peer eval --dataset dataset/reference/django_pydantic_v2.jsonl` with default config (ruff enabled). Save to `data/eval_runs/reference_v2_sonnet46_with_linters.json`. Compare to baseline — expect linter findings to surface in peer's comments at low severity (replacing peer-discovered nits).
- [ ] 8.2 Verify token-budget: gather codebase context with deliberately oversize linter output, assert tests drop first then linter findings; log review.
