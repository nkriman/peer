# Pydantic AI's design philosophy — what peer should learn

**Source:** [pydantic.dev/docs/ai](https://pydantic.dev/docs/ai/) (the agent framework from the Pydantic team — same folks who built Pydantic itself).

## The one-line pitch

> "FastAPI revolutionized web development … Pydantic AI brings that FastAPI feeling to GenAI app and agent development."

That comparison is the design philosophy. FastAPI is decorators + type hints + Pydantic models + dependency injection + great testing story. Pydantic AI is the same pattern applied to LLM apps.

Concretely: **type-safe everything**, **dependency injection as a first-class concept**, **structured outputs validated by Pydantic with auto-retry on validation failures**, **TestModel for offline testing**, **multi-provider via string identifiers**.

## Core abstractions

### Agent

```python
from pydantic_ai import Agent

agent = Agent(
    'anthropic:claude-sonnet-4-6',     # provider:model string
    deps_type=PeerDeps,                 # what context tools receive
    output_type=Review,                 # Pydantic model validated automatically
    instructions='You review PRs.',     # regenerated per-run
    retries={'output': 3},              # validation retry budget
)

result = agent.run_sync('review this PR', deps=peer_deps)
print(result.output)  # type: Review
```

Five run modes: `run()` (async), `run_sync()`, `run_stream()` (streaming structured output), `run_stream_events()` (raw events), `iter()` (graph-level).

### Tools via decorator + RunContext

```python
@agent.tool
async def fetch_call_sites(ctx: RunContext[PeerDeps], symbol: str) -> list[str]:
    return await ctx.deps.codebase.find_callers(symbol)
```

Tools receive `ctx: RunContext[PeerDeps]` as first param — typed access to deps. Docstring becomes the tool's LLM-visible description.

### Dependency injection (the big idea)

```python
@dataclass
class PeerDeps:
    github_token: str
    repo_cache: Path
    classifier: CommentClassifier
    config: PeerConfig

agent = Agent('anthropic:claude-sonnet-4-6', deps_type=PeerDeps, ...)
result = agent.run_sync('...', deps=PeerDeps(github_token=..., repo_cache=..., ...))
```

The framework rationale:

> "Data and services to your agent's system prompts, tools and output validators … type-safe, understandable, easier to test, and ultimately easier to deploy in production — rather than obscure 'magic'."

The "rather than obscure magic" is the key tell. Pydantic AI sees the alternative as "global variables and singletons" (i.e. how most LangChain-style frameworks work) and explicitly rejects it.

### Output validation with retries

If the LLM's response fails Pydantic validation, the framework gives the model the error and asks it to fix. Bounded by `retries={'output': N}`. **The agent self-corrects bad output.**

peer currently DROPS comments that fail validation (wrong path, wrong line, etc.). Pydantic AI's pattern is strictly better — give the agent a chance to fix it before dropping.

### Testing — first-class

```python
from pydantic_ai import models, capture_run_messages
from pydantic_ai.models.test import TestModel

models.ALLOW_MODEL_REQUESTS = False   # raises if any real LLM call attempted

with agent.override(model=TestModel()):
    result = await agent.run('review this PR', deps=mock_peer_deps)

with capture_run_messages() as msgs:
    result = await agent.run('...', deps=...)
# msgs is the full prompt + response history for assertions
```

Four primitives:
- **`TestModel`** — generates valid output from `output_type` schema. No LLM call. Free, fast, deterministic.
- **`FunctionModel`** — custom logic for sophisticated cases.
- **`agent.override(model=..., deps=...)`** — context manager swaps without touching code.
- **`ALLOW_MODEL_REQUESTS=False`** — global panic switch for CI.
- **`capture_run_messages()`** — full message history for assertions.

This is what good testing looks like for LLM apps. peer has none of it yet.

### System prompt vs instructions

```python
@agent.system_prompt    # persists in message_history across runs
def name_user(ctx): ...

@agent.instructions     # regenerated per-run, NOT in message_history
def add_date(): ...
```

The recommendation: **prefer `instructions`** for multi-agent workflows, because `system_prompt` persists when you pass `message_history` between agents.

### Multi-provider via string identifiers

```python
Agent('openai:gpt-5.2', ...)
Agent('anthropic:claude-sonnet-4-6', ...)
Agent('google:gemini-2.0-flash', ...)
Agent('local:llama-3-70b', ...)
```

Provider-prefixed model strings. The framework abstracts SDK differences. Custom providers implementable.

peer currently does prefix-matching (`model.startswith('claude')` → ClaudeReviewer). Pydantic AI's `provider:model` format is cleaner and unambiguous.

### Composable capabilities

```python
agent = Agent(..., capabilities=[Thinking(), WebSearch()])
```

First-class concept for bolting on cross-cutting features. peer's `team_conventions=` and `linters=` are headed in this direction but not formalized as capabilities.

### Observability via Logfire

Built-in tracing for every agent run. Spans, events, latency, token costs, tool calls — all captured by default. peer has none.

## What peer should adopt (and what NOT to)

### Adopt directly (small, high-impact changes)

1. **`provider:model` string format.** Change peer's model parsing from `model.startswith('claude')` to `model.split(':', 1)` returning `(provider, model_id)`. Cleaner, unambiguous, supports `local:llama-3` if a user adds a local backend later.

2. **`Agent.override()` context manager.** ~20 LOC. Lets tests + the eval framework swap reviewer/config/deps without touching the Agent. Critical for testing.

3. **`TestReviewer`** — peer's equivalent of `TestModel`. Generates deterministic Comments based on input shape, no LLM call. ~30 LOC. Foundational for offline unit tests + cheap eval-pipeline tests.

4. **`ALLOW_LLM_CALLS = True` global flag.** When False, any Reviewer that tries to call the LLM raises `LLMCallsDisabled`. Cheap, prevents accidental cost in CI. ~5 LOC.

5. **Output validation with retries.** Currently peer's `_validate_comments` drops comments with bad path/line. Better: capture the validation errors, feed them back to the agent, give it `retries=N` chances to self-correct. ~30 LOC. Materially better recall for borderline cases.

6. **`capture_run_messages()` equivalent.** Currently `Review.usage` carries token counts but the actual prompt + response aren't captured. For eval forensics this matters: when a comment is wrong, we want to see the exact prompt the LLM saw. Add `Review.messages: Optional[list[Message]]` (opt-in via `Agent(capture_messages=True)`). ~20 LOC.

### Adopt with adaptation (architectural shifts)

7. **`deps_type` / `RunContext` pattern.** This is the biggest design idea. Currently peer's `Agent` constructor takes a flat list of kwargs (`model`, `system_prompt`, `team_conventions`, `team_conventions_file`, `config`, `config_file`). As we add `extra_instructions`, `linters`, `enrichment`, etc. this gets unwieldy.

   Better:
   ```python
   @dataclass
   class PeerDeps:
       config: PeerConfig
       linters: list[Linter]
       enrichment: EnrichmentStep
       # ... and so on
   
   agent = Agent(model='anthropic:claude-sonnet-4-6', deps_type=PeerDeps)
   review = agent.run_sync(pr_url, deps=PeerDeps(...))
   ```

   This is a bigger refactor — affects `Agent.__init__`, the Reviewer Protocol, the eval framework. Probably its own change (`peer-deps-v01`). Worth doing before `peer-config-v01` lands, because it changes the shape of how config is injected.

8. **Decorator-based tool registration.** If peer ever adds user-extensible tools (e.g., "let the agent look up symbols via tree-sitter", "let the agent run a linter on demand"), `@agent.tool` is the right shape. Currently peer's tools are hardcoded as part of the prompt (Comment schema). When/if we add multi-turn agent flows, this matters.

9. **`instructions` vs `system_prompt` distinction.** Currently peer treats them as one. Pydantic AI's pattern lets you build multi-agent workflows where one agent's instructions don't leak into another's context. Probably premature for v0.1 but worth knowing for v0.3+.

### Do NOT adopt

10. **Don't make peer depend on Pydantic AI.** Adding ~MB of dep + locking users to PA's design + adding a framework-of-frameworks layer is wrong. We borrow PATTERNS, not the implementation.

11. **Don't adopt the full graph / capabilities system.** Cool but over-engineered for peer's reviewer-first scope.

12. **Don't adopt Logfire as the observability layer.** Tying observability to a single vendor is wrong for an OSS framework. Use stdlib logging + structured event emission; let users plug their own backend.

13. **Don't adopt `agent.iter()` / streaming.** PR review isn't a streaming use case (the human doesn't read along as the comments emerge). Adds complexity for no user benefit.

## Should we offer `PydanticAIReviewer` as an optional Reviewer impl?

**Yes, but later.** Pydantic AI users would love to plug their existing Agent into peer's eval framework. The `Reviewer` Protocol is exactly the right seam:

```python
class PydanticAIReviewer:
    def __init__(self, pydantic_agent: pydantic_ai.Agent[..., Review]):
        self.agent = pydantic_agent
    def review(self, context, codebase_context=None):
        result = self.agent.run_sync(...)
        return result.output.comments, {'usage': ...}
```

~30 LOC. Ship in a `peer-pydantic-ai-v01` change after the v0.2 wave lands. Optional dep (`pip install peer[pydantic-ai]`).

## Net implication for the in-flight changes

Of the 6 changes currently in flight (`prompt-quality-v01` just landed, plus `eval-metrics-v01` / `peer-config-v01` / `linter-context-v01` / `patch-suggestions-v01` / `benchmark-v01`):

- **`peer-config-v01`**: should likely be restructured to use the `deps_type` pattern. Currently the design has `Agent(config=..., config_file=...)`. With `deps_type=PeerDeps`, config becomes one field on the deps dataclass. Cleaner constructor, easier extension. Worth pausing peer-config-v01 implementation to do `peer-deps-v01` FIRST.

- **`linter-context-v01`**: same — linters become a field on `PeerDeps`, not a separate Agent constructor kwarg.

- **`patch-suggestions-v01`**: validation-retry pattern from Pydantic AI fits perfectly here. Currently the design says "log WARNING when suggestion is misaligned." Better: let the agent retry to produce a well-aligned suggestion.

- **`benchmark-v01`**: `agent.override(model=...)` would simplify how benchmark runs swap models for the same agent config. Currently the design has `RepoAwareAgent` doing per-repo agent construction. Override-pattern is cleaner.

- **`eval-metrics-v01`**: no change. Pydantic AI doesn't have direct guidance on eval metrics; their `pydantic-evals` package is its own thing we should research separately (next).

## Recommended next sequence

1. **Implement `prompt-quality-v01`** (already done — committed).
2. **Implement `eval-metrics-v01`** (already started, mostly done).
3. **Write `peer-deps-v01` OpenSpec change** to introduce `PeerDeps` + `agent.override()` + `TestReviewer` + `ALLOW_LLM_CALLS`. This is foundational for the rest.
4. **Implement `peer-deps-v01`** — refactor Agent.__init__ to use deps_type pattern. Re-eval.
5. **Resume `peer-config-v01`** — now slots cleanly into PeerDeps.
6. **`linter-context-v01`** — linters as PeerDeps field.
7. **`patch-suggestions-v01`** — with validation-retry pattern from Pydantic AI.
8. **`benchmark-v01`** — uses override pattern.
9. **Later: `peer-pydantic-ai-v01`** — optional adapter for Pydantic AI users.

This adds one new change (`peer-deps-v01`) and reshuffles the order so it lands early. The downstream changes get cleaner.

## Sources

- [Pydantic AI Overview](https://pydantic.dev/docs/ai/overview/)
- [Agent](https://pydantic.dev/docs/ai/core-concepts/agent/) — Agent class, system_prompt vs instructions, run modes
- [Dependencies](https://pydantic.dev/docs/ai/core-concepts/dependencies/) — deps_type, RunContext, override
- [Testing](https://pydantic.dev/docs/ai/guides/testing/) — TestModel, FunctionModel, ALLOW_MODEL_REQUESTS, capture_run_messages
