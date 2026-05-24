## 1. Shim client

- [ ] 1.1 Create `src/peer/claude_code_client.py` with `ClaudeCodeShimClient`, `ClaudeCodeShimResponse`, `ClaudeCodeShimContentBlock`, `ClaudeCodeShimUsage` per spec.
- [ ] 1.2 `messages.create(...)` flattens `messages` into a single user prompt (system content via `--system-prompt`).
- [ ] 1.3 Tool-use synthesis: when `tools=[...]` passed, parse the response's `result` text via the same robust JSON extractor used in `ClaudeCodeCLIReviewer` (direct → fenced ```json → first balanced `{...}`); synthesize a `tool_use` ContentBlock whose `.name` is `tool_choice["name"]` and `.input` is the parsed dict.
- [ ] 1.4 Usage: sum `usage.input_tokens + cache_read_input_tokens + cache_creation_input_tokens` for the response's `.usage.input_tokens` field.

## 2. make_client factory

- [ ] 2.1 `make_client(*, use_claude_code: bool | None = None)` per spec — env var lookup, override precedence.
- [ ] 2.2 Module-level helper `_truthy_env(name)` for `"1"/"true"/"yes"` (case-insensitive).

## 3. Wire ClaudeReviewer

- [ ] 3.1 Update `ClaudeReviewer.__init__` to use `make_client()` instead of `anthropic.Anthropic()`.
- [ ] 3.2 Add an optional `client_factory: Callable[[], Any] | None = None` constructor kwarg for tests to inject custom clients.

## 4. Wire EvalRunner

- [ ] 4.1 Update `EvalRunner._get_client` to call `make_client()`.

## 5. Wire benchmark

- [ ] 5.1 Update `BugBenchmarkRunner` + the CLI's `_cmd_benchmark_run` to construct the judge client via `make_client()`.

## 6. Wire dataset helpers

- [ ] 6.1 Update `CommentClassifier.client` lazy-init to use `make_client()`.
- [ ] 6.2 Update `EnrichmentStep.client` lazy-init to use `make_client()`.

## 7. Recipe field

- [ ] 7.1 Add `use_claude_code: bool = False` to `Recipe`.
- [ ] 7.2 `Recipe.apply_to_agent` sets `os.environ["PEER_USE_CLAUDE_CODE"] = "1"` when the field is true; constructs `ClaudeCodeCLIReviewer` instead of falling through to the default reviewer.

## 8. CLI flags

- [ ] 8.1 Add `--use-claude-code` to `peer eval`. In `_cmd_eval`, set the env var before constructing the runner.
- [ ] 8.2 Add `--use-claude-code` to `peer autoresearch run` + `peer autoresearch loop`. In `_cmd_autoresearch_run` + `_cmd_autoresearch_loop`, set the env var before delegating.
- [ ] 8.3 Add `--use-claude-code` to `peer benchmark run`. Same pattern.

## 9. BDD

- [ ] 9.1 Create `features/claude_code_everywhere.feature` covering all scenarios from the spec.
- [ ] 9.2 Step defs in `features/steps/claude_code_everywhere_steps.py`. Patch `subprocess.run` to return canned envelopes — no live CLI invocations.

## 10. Docs

- [ ] 10.1 `docs/claude_code_everywhere.md` — switch, cost model, latency caveat, tool-use compatibility notes.

## 11. Verification

- [ ] 11.1 Run one `peer autoresearch run --use-claude-code` iteration on the hard subset, confirm it completes without `ANTHROPIC_API_KEY` set, and compare its detection_rate to the SDK baseline (acceptable if within ~30% — CLI uses cached prompts differently).
