## Why

Every peer Reviewer today is single-pass: build context once, ship to LLM, parse output. Real senior reviewers iterate — they grep for symbol usage, read related files, run mypy, check git blame. The Reviewer that lets the model decide *when* to fetch more context is fundamentally different.

We already noted the framework support is in place (`peer.strategies` registry, the Reviewer Protocol, the CLI shim). The actual implementation needs only one design decision: where do the tools come from?

The original design assumption was "build a peer-defined tool catalog." That's a few hundred lines of glue + spec churn. The simpler realization: **claude code already has a curated tool ecosystem** (Read, Grep, Glob, Bash, etc.). Routing through the CLI with `--allowedTools "Read,Grep,Glob"` lets the model use them natively. We don't have to build a tool registry — we just have to flip the flag we currently use to *disable* those tools.

So this change is small: a new `AgenticReviewer` that's the CLI reviewer with tools ENABLED + a turn cap + the same robust JSON-from-prose extractor. Ships as a `peer.strategies` entry so recipes can wire it via `reviewer_dotted_path: agentic`.

Honest acknowledgment per the noise-floor finding: we should NOT claim AgenticReviewer "beats baseline" until we've measured it via the new multi-run primitive. This change ships the Reviewer; the measurement is a separate followup.

## What Changes

- New `peer.strategies.AgenticReviewer` class — Reviewer Protocol implementation.
  - Shells out to `claude --print --output-format json` with `--allowedTools "Read,Grep,Glob"` (default set, configurable).
  - Bounded by `max_turns` constructor arg (default 15) — passed via the CLI's existing `--max-turns` flag (or equivalent; the CLI exposes turn bounding).
  - System prompt frames the model as "an iterative code reviewer; use the available tools to investigate before finalizing your review."
  - User prompt = same PR-Agent diff format + `_CLI_INSTRUCTIONS_SUFFIX` (return JSON).
  - Parses `structured_output` first, then falls back to `_extract_comments_payload` over the result text.
  - NO `--disallowedTools` flag (the whole point is to ENABLE tool use).
- Registry registration: `peer.strategies` registers it under the short name `"agentic"`.
- Recipe wiring is transparent — `reviewer_dotted_path: "agentic"` + `reviewer_kwargs: {max_turns: 15, allowed_tools: ["Read", "Grep", "Glob"]}` already works through the existing `_resolve_dotted` + `_resolved_reviewer_kwargs` machinery.
- New BDD `features/agentic_reviewer.feature` covers: argv construction (correct flags), tool list passes through, response parsing (structured_output and prose fallback), Recipe wiring.

## Capabilities

### New Capabilities

- `agentic-reviewer`: `AgenticReviewer` strategy that delegates to the `claude` CLI with tools enabled.

### Modified Capabilities

- `autoresearch-strategies` (from autoresearch-strategies-v01): registry gains the `"agentic"` short name. Existing strategy resolution unchanged.

## Impact

- **Code**: new `src/peer/strategies/agentic.py` (~150 LOC). Modifications: `src/peer/strategies/__init__.py` (export + registry registration).
- **Dependencies**: none new. Reuses the `claude` binary + the JSON-from-prose extractor already in `peer.reviewers`.
- **Tests**: BDD in `features/agentic_reviewer.feature`. Step defs patch `subprocess.run` — no live CLI invocations.
- **Schema**: no Pydantic model changes.
- **Back-compat**: opt-in via Recipe. Default `Recipe()` doesn't use AgenticReviewer.
- **Out of scope**: SDK-path AgenticReviewer (would require a peer-defined tool catalog — that's a real future build). Per-tool result caching across reviews. Cost/latency caps beyond `max_turns`. Tool security boundaries beyond what claude code already enforces (the model can grep/read but not Bash by default).
- **Performance**: per-PR latency depends on how many tool turns the model takes. With max_turns=15 and ~3s per CLI call within a turn, a PR could take 30s-5min. Substantially slower than static-context — that's the tradeoff.
- **Cost**: $0 under CLI subscription, same as the other CLI-routed reviewers.
