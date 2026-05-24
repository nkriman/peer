## 1. AgenticReviewer

- [ ] 1.1 Create `src/peer/strategies/agentic.py` with `AgenticReviewer` per spec.
- [ ] 1.2 Reuse `_extract_comments_payload` from `peer.reviewers` for the prose-fallback path.
- [ ] 1.3 Reuse `format_prompt` + `_CLI_INSTRUCTIONS_SUFFIX` from existing reviewer surface.
- [ ] 1.4 Argv: `--allowedTools=<comma-list>` (= form to pin nargs), `--max-turns <N>`, NO `--disallowedTools`.
- [ ] 1.5 Honor ALLOW_LLM_CALLS gate.
- [ ] 1.6 Usage: sum cache_read + cache_creation + input_tokens for representative count.

## 2. Registry

- [ ] 2.1 Update `peer.strategies.__init__` to import AgenticReviewer + register under `"agentic"`.
- [ ] 2.2 Export `AgenticReviewer` from `peer.strategies`.

## 3. BDD

- [ ] 3.1 `features/agentic_reviewer.feature` covering: argv flags, structured_output parse, prose fallback parse, ALLOW_LLM_CALLS gate, registry short-name resolution, Recipe wiring.
- [ ] 3.2 Step defs patch subprocess.run — no live CLI invocations.

## 4. Gates

- [ ] 4.1 ruff / format / mypy / pytest / behave all clean.
