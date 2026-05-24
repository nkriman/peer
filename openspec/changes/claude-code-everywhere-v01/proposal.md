## Why

`peer` currently makes every model call via the Anthropic SDK, billed against `ANTHROPIC_API_KEY`. The autoresearch session we just ran spent ~$3 over 7 iterations; an overnight loop at 30 iterations would cost ~$15, and bigger sweeps (1000-iter / multi-recipe / full v2 dataset) grow linearly.

We already have `claude` (Claude Code CLI) installed and authenticated via OAuth/keychain — its calls don't bill against the API key. `ClaudeCodeCLIReviewer` (peer-nq7) was a first step that proved the wiring works for the reviewer path. But **every other model call still goes through the SDK**: every `LLMJudge`, `judge_match`, `judge_bug_caught`, `RationaleGrounding`, and the dataset/curation helpers all call `anthropic.Anthropic().messages.create(...)` directly.

This change adds a single switch that routes *every* model call through the `claude` CLI. Implementation strategy is a SDK-shaped *shim*: `ClaudeCodeShimClient` exposes the same `.messages.create(...)` surface as `anthropic.Anthropic`, but each call shells out to `claude --print --output-format json`. Drop the shim in wherever a client is currently constructed and nothing else changes — every Reviewer, judge, and metric keeps working as-is.

This is the "free for us" path the user asked for. Switch on, watch the leaderboard, iterate as long as we like at zero API cost.

## What Changes

- New `peer.claude_code_client` module:
  - `ClaudeCodeShimClient` — a class whose `.messages.create(model=..., messages=..., max_tokens=..., system=..., temperature=..., tools=..., tool_choice=...)` builds an argv, shells out to `claude --print --output-format json`, and returns an SDK-shaped response object (with `.content` blocks and `.usage`).
  - `ClaudeCodeShimResponse` — Pydantic model mirroring the SDK's `Message` shape (`content: list[ContentBlock]`, `usage: Usage`).
  - `ClaudeCodeShimContentBlock` — covers both `type="text"` and `type="tool_use"` returns. For tool_use, we synthesize a block when the user's prompt included `tools=[...]` by parsing the response text against the tool's `input_schema` (best-effort, with the same robust JSON-extraction we already use in `ClaudeCodeCLIReviewer`).
  - `ClaudeCodeShimUsage` — `input_tokens` + `output_tokens` (sourced from the CLI envelope's `usage` field — the CLI reports both real and cache-read input).
  - Module-level `make_client()` factory that returns either `anthropic.Anthropic()` or `ClaudeCodeShimClient()` based on a single env var + Recipe field.
- New env var `PEER_USE_CLAUDE_CODE` (`"1"` / `"0"`, default off). When set to `"1"`, `make_client()` returns the shim. Pull-through to every call site (see Wiring below).
- New `Recipe.use_claude_code: bool = False` field. When true, `apply_to_agent` builds a `ClaudeCodeCLIReviewer` AND the env-var route flips for the duration of the recipe's eval. Recipe wins over env var.
- **Wiring**: every existing `anthropic.Anthropic()` site changes from a direct construction to `peer.claude_code_client.make_client()`. Specifically:
  - `peer.reviewers.ClaudeReviewer.__init__` — uses `make_client()` instead of `anthropic.Anthropic()`. The shim's tool-use synthesis covers the `_COMMENT_TOOL` schema.
  - `peer.eval.runner.EvalRunner._get_client` — uses `make_client()`. All judges (LLMJudge, judge_match, etc.) call through to this.
  - `peer.benchmark.runner.BugBenchmarkRunner` + `peer.benchmark.judge.judge_bug_caught` — same swap.
  - `peer.dataset.classifier.CommentClassifier` + `peer.dataset.enrichment.EnrichmentStep` — same swap.
- `peer autoresearch run --use-claude-code` flag (overrides env var). The autoresearch loop CLI gains the same flag for convenience.
- `peer eval --use-claude-code` flag.
- `peer benchmark run --use-claude-code` flag.
- Docs: `docs/claude_code_everywhere.md` — explains the switch, the cost model, the trade-offs (CLI startup latency adds ~15s per call vs SDK), and known compatibility gaps (the CLI's tool_use synthesis is best-effort — the JSON-from-prose parser handles the common case but won't catch every edge).

## Capabilities

### New Capabilities

- `claude-code-everywhere`: `ClaudeCodeShimClient` + the `make_client` factory + the `PEER_USE_CLAUDE_CODE` switch + per-CLI flags wiring.

### Modified Capabilities

- `pr-review-agent`: `ClaudeReviewer.__init__` accepts an optional `client_factory` kwarg (defaults to `make_client`). Existing default behavior unchanged when `PEER_USE_CLAUDE_CODE` is off.
- `eval-runner` (eval-v01 / v02): `EvalRunner._get_client` honors the switch. Metric `client` kwargs accept the shim transparently.
- `autoresearch-recipe`: `Recipe.use_claude_code: bool` field. Round-trips through YAML.

## Impact

- **Code**: new `src/peer/claude_code_client.py`. Modifications: `src/peer/reviewers.py`, `src/peer/eval/runner.py`, `src/peer/benchmark/runner.py`, `src/peer/benchmark/judge.py`, `src/peer/dataset/classifier.py`, `src/peer/dataset/enrichment.py`, `src/peer/recipe.py`, `src/peer/cli.py`.
- **Dependencies**: none new. Reuses the `claude` binary already installed for Claude Code.
- **Tests**: BDD in `features/claude_code_everywhere.feature`. Step defs patch `subprocess.run` to verify the shim builds the right argv and parses the right shapes — no live CLI invocations in the BDD layer.
- **Schema**: `Recipe` gains one optional field with a default that preserves today's behavior.
- **Back-compat**: switch defaults off. Every existing code path stays identical when the switch is off. Existing tests/scenarios stay green.
- **Out of scope**: model-specific differences (the CLI auto-routes to whatever Claude Code is configured with; we don't override per-call). OpenAI / other-provider backends (orthogonal — they have their own paths). Streaming responses (the shim is request-response only).
- **Performance**: each CLI call adds ~15s of startup overhead vs the SDK. For autoresearch's 7-PR hard subset at concurrency=5, that pushes per-iter wall-clock from ~2min to ~3-4min. Acceptable for "free for us" iteration.
