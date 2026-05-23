# Scope research — lessons from successful (and failed) OSS AI frameworks

> Built 2026-05-23 to inform `peer`'s scope decisions before significant
> code lands. Studies seven OSS frameworks across the agent / eval / coding
> / structured-output / general-purpose space.

## What we studied

| Framework | Stars | Scope |
|---|---|---|
| Aider | 45.2k | CLI coding agent (general-purpose) |
| DSPy (Stanford) | 34.6k | Programmatic prompting / self-improvement |
| Pydantic AI | 17.2k | Type-safe agent framework |
| DeepEval | 15.7k | LLM eval framework (general) |
| Instructor | 13.0k | Structured output extraction ONLY |
| PR-Agent (Qodo OSS) | 11.3k | Multi-tool PR review |
| LangChain | huge | Everything (canonical over-abstraction example) |

## Patterns of success — what to copy

1. **Narrow scope is the feature, not a limitation.** Instructor (13k stars, 3M monthly downloads) explicitly does *one* thing: "extract structured data from a single LLM call." Its README contrasts itself with Pydantic AI: "Use Instructor for fast extraction, reach for Pydantic AI when you need agents." The clarity is the product.

2. **"Like X for Y" positioning is potent.** Pydantic AI: *"FastAPI feeling for GenAI."* DeepEval: *"Pytest-style for LLM apps."* Aider: *"AI pair programming in your terminal."* Easy to grasp, easy to position against alternatives.

3. **Multi-LLM / no vendor lock-in is table stakes.** Every successful framework (Aider, Instructor, Pydantic AI, DeepEval) explicitly supports multiple providers. None couples to one.

4. **Pydantic-typed throughout = developer trust.** Pydantic AI's whole position is built on this. Instructor's value is Pydantic-based. Type safety in 2026 is non-negotiable for Python AI tooling.

5. **Pluggable / composable architecture.** DeepEval supports OpenAI, LangChain, LangGraph, Pydantic AI, CrewAI, Anthropic, AWS AgentCore, LlamaIndex out of the box. Adapters > monoliths.

6. **Pytest-style developer experience for evals.** DeepEval's `assert_test()` + `LLMTestCase` pattern is widely loved. Familiar tools win.

7. **Clear "we don't do X" statement.** Successful frameworks declare non-goals loudly. Instructor: "not an agent framework." Pydantic AI: "not multi-agent at scale." Clarity about non-scope is the feature.

## Patterns of failure — LangChain's critiques

The 2025–2026 community consensus on LangChain is damning and worth internalizing:

- **Over-abstraction.** "Wrapping everything in Runnable / LCEL / BaseChatModel / BaseRetriever makes the code hard to read, hard to debug, and hard to explain to teammates."
- **"150 lines of LangChain to do what 30 lines of direct API calls would do."**
- **Hidden behavior.** "Similar inputs produce different outcomes depending on which chain or agent is used."
- **Doing everything = doing nothing well.** The ecosystem itself fragmented (LangGraph, LlamaIndex split off) because the monolith couldn't specialize.

The 2026 consensus quote, from the comparison research: *"RAG is no longer a framework decision—it is a layer decision, with production teams typically using LlamaIndex underneath the retrieval layer and a different framework for orchestration, which is the field correctly scoping its tools."* Specialization beats generalization.

## Applied to peer — IN scope

- **PR review agent abstraction** — specifically the PR review shape, not general code review.
- **Context gathering for PR review** — diff, surrounding code snippets, PR description, prior discussion.
- **Eval harness using repo's own historical reviews as gold standard** — the core differentiator.
- **Severity-tagged comment output** — critical / important / minor / nit (taxonomy may evolve).
- **Pluggable `Reviewer` interface** — BYO model adapter (Claude, OpenAI, local). Eventually BYO commercial reviewer adapter (Greptile, CodeRabbit) for benchmarking in v0.3.
- **Multi-LLM by default** — Claude, OpenAI day one; local models via adapter.
- **GitHub integration** — first and only initially.
- **Pydantic-typed throughout** — types are first-class.
- **Pytest-style eval surface** — `eval.against_history(agent, repo, ...)` familiar shape; deep DeepEval interop later.

## Applied to peer — explicitly OUT of scope

These are the "we don't do X" decisions to declare loudly:

- **General-purpose agent framework.** Use Pydantic AI.
- **Multi-agent orchestration.** Use CrewAI / LangGraph.
- **RAG primitives / vector databases / retrieval layer.** Use LlamaIndex.
- **General coding agent / code generation / refactoring.** Use Aider / OpenHands / Cursor.
- **IDE integration / interactive coding session.** Use Cursor / Continue / Aider.
- **Observability platform.** Integrate with Logfire / Langfuse / Phoenix, don't build our own.
- **LLM training / fine-tuning.** Out of scope, period.
- **Custom inference server.** Use the model providers' APIs.
- **Web UI.** CLI / Python API only.
- **Non-Python ecosystem.** Python-first; bindings can come later if there's pull.
- **Self-hosted vector DB.** Out of scope.
- **Generic CI/CD workflow runner.** GitHub `gh-aw` covers that.
- **Auto-merge / auto-fix / auto-rewrite.** `peer` is a *reviewer*, not a fixer. Reviewer outputs comments; humans (or other agents) decide what to do.
- **PR description generation / commit message generation / changelog generation / issue triage / question-answering on code.** PR-Agent has all of these. They are deliberately not peer's scope. Each one dilutes the focus.
- **Issue / Linear / Jira integration.** Not now.
- **Severity calibration per-repo.** v0.1 ships a fixed taxonomy; per-repo calibration is a v2 question.

## Watch for scope creep — defer to v0.2+

Things that *could* be in scope but should explicitly wait until v0.1 ships:

- GitLab / Bitbucket / Azure DevOps integration. (GitHub first.)
- Webhook / GitHub Action wrapper. (Manual triggering / library use first.)
- Side-by-side commercial-reviewer benchmarking. (Per roadmap, v0.3.)
- Multiple review *modes* (security audit, performance audit, accessibility audit). (One general review first.)
- Auto-tuning of agent prompts based on eval feedback. (Manual iteration first; auto-tune is a meaty research direction.)

## Architectural rules carried over from this research

1. **If a feature can be implemented in 30 lines of direct code, don't wrap it in 5 base classes.** Per LangChain's failure mode.
2. **Pydantic-typed surfaces everywhere.** No untyped dicts at API boundaries.
3. **Every public function should be debuggable in one read.** No deep inheritance chains.
4. **Examples in the README must run as-is.** Per the developer-trust patterns.
5. **Multi-LLM by default, not as an afterthought.** Single-vendor frameworks die.
6. **Eval surface is a first-class component, not a side library.** That's the differentiator.
7. **Public design choices live in `docs/design.md`.** Per Aider's open dev culture.

## Where peer differs from the closest competitor (PR-Agent / Qodo)

PR-Agent has six tools — `/describe`, `/review`, `/improve`, `/ask`, `/help_docs`, `/update_changelog`. It's a Swiss Army knife for PR-shape tasks across GitHub, GitLab, Bitbucket, Azure DevOps, Gitea, with multiple deployment paths (CLI, GH Action, Docker, webhooks, self-hosted).

`peer`'s differentiation:

- **Scope:** review only. No describe, improve, ask, changelog. Single tool, done well.
- **Eval:** PR-Agent has no eval methodology surfaced. `peer`'s eval-against-history is the headline.
- **Deployment:** Python library first. GH Action / Docker as wrappers later if demand exists.
- **Shape:** PR-Agent ships an opinionated agent. `peer` is a framework you build your agent inside.

The right positioning: *"PR-Agent is a multi-tool reviewer you install. peer is the framework you build your team's reviewer inside, with the eval to know it works."*

## Sources

- [Instructor](https://github.com/jxnl/instructor) — 13k stars, structured-output narrow scope
- [Pydantic AI](https://github.com/pydantic/pydantic-ai) — 17.2k stars, type-safe agent framework
- [DSPy](https://github.com/stanfordnlp/dspy) — 34.6k stars, programmatic prompting
- [DeepEval](https://github.com/confident-ai/deepeval) — 15.7k stars, pytest-style LLM eval
- [Aider](https://github.com/Aider-AI/aider) — 45.2k stars, CLI coding agent
- [PR-Agent](https://github.com/qodo-ai/pr-agent) — 11.3k stars, multi-tool PR helper (closest competitor)
- LangChain critique synthesis: HN, community discussions on over-abstraction, Designveloper / BSWEN / NeurlCreators analyses.
