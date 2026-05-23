# Codebase understanding for AI PR review — research synthesis

> Built 2026-05-23. Studies how the leading AI coding/review tools (Aider,
> Cursor, Sourcegraph Cody, Greptile, CodeRabbit, Claude Code, Devin) handle
> codebase understanding, plus the 2026 academic/industry consensus.
> Companion to `docs/scope_research.md`.

## TL;DR — the four findings that shape peer's direction

1. **Hybrid beats pure approach.** No leading tool uses just one technique. Every credible system in 2026 combines multiple methods: structural navigation (AST + graph), semantic retrieval (embeddings, when used), tool-use (grep, file-tree walks), and architectural context (handbook docs, prior PRs).

2. **Pure vector-DB RAG is being demoted.** The 2026 Amazon Science paper showed that keyword search via agentic tool use reaches ~90% of RAG-level performance without a vector database. Claude Code, Cursor, and Devin all moved *away* from vector-DB-only approaches toward grep + AST + file-tree navigation. Cursor still uses embeddings, but as one tool among several, not the foundation.

3. **Long context windows don't replace structure.** The 2026 CodeCompass paper named this the "Navigation Paradox": larger context windows shift the failure mode from retrieval capacity to *navigational salience* — when architecturally critical but semantically distant files are absent from the model's attention, errors still occur. Context budget alone doesn't solve it.

4. **CodeRabbit's principle is the clearest design north star for PR review specifically:** 80–90% of token usage in their reviews goes into context *enrichment*, not the final review itself. They maintain a 1:1 code-to-context ratio in LLM prompts. This is the gap between toy PR reviewers and real ones.

## The five leading systems and what they actually do

### Aider (`aider.chat`) — open source, repo-map approach

- **What:** sends the LLM a structured "map" of the entire repository: file listings + key symbols (classes, functions, methods) with **type signatures** + **defining lines** + frequently-referenced identifiers.
- **How:** tree-sitter for AST parsing across 66+ languages; PageRank-style graph ranking on the file dependency graph identifies the most contextually relevant code; default 1,000-token budget (dynamically expanded when no files are in the active chat).
- **What it explicitly excludes:** complete implementations, less-important identifiers, full file content. The LLM gets "enough to know what to ask for."
- **Why this works:** the map lets the LLM identify which specific files to examine, then it can request them. Much cheaper than embedding everything; structurally aware where pure embeddings aren't.

### Cursor — embeddings + grep + agentic tool-use

- **Approach:** RAG-style indexing for fast semantic retrieval (custom-trained embedding model, syntactic chunking, vector DB) — but the *agent loop* uses grep / read-file / find-references heavily, not just vector lookup.
- **Implementation:** chunks each file syntactically, embeds each chunk, caches in AWS keyed by hash for incremental re-indexing; vector DB (Turbopuffer) returns ranked candidates; metadata-only at the cloud (paths + line ranges); local client resolves to actual code.
- **Insight:** they kept embeddings but added agentic navigation. The shift away from "RAG only" is now public in their blog.

### Sourcegraph Cody — RAG + precise code intelligence

- **Approach:** keyword extraction → embeddings search → **code graph lookup** (precise Find References / Find Definitions via Sourcegraph search) → context reranking → LLM inference.
- **Distinctive:** the code graph lookup uses *precise* code intelligence, not just semantic guesses. References and definitions are deterministic, not statistical.
- **Scale:** integrates with 300,000+ repository customers and 90GB+ monorepos. Multi-repo context retrieval. 1M-token windows supported.

### Greptile — knowledge graph + multi-hop investigation

- **Approach:** index the entire repo, build a **code graph** of how files / functions / services interact; use **multi-hop investigation** to trace dependencies, check git history, and follow leads across files.
- **Claims:** 4× faster merges, 3× more bugs caught vs baseline review; v4 (early 2026) reports 74% increase in addressed comments per PR and 68% increase in positive developer replies.
- **Adaptive learning:** the system learns each team's review standards from accepted/rejected feedback over time.

### CodeRabbit — context engine + LanceDB

- **Architecture:** for every PR: clone repo → analyze diff → construct code graph → pull cross-file/cross-repo references → assemble from semantic index of functions/classes/tests/prior-PRs.
- **Context assembled per review:**
  - Linked issues
  - Architecture standards
  - Custom review instructions
  - Coding conventions
  - Past PRs on the same modules
  - Team-specific learnings
  - Cross-repo usages of modified symbols
  - Tests parallel to the changed code
- **Infrastructure:** LanceDB for vector storage; graph regenerated per review (no stale dependency assumptions).
- **The headline principle:** *"80–90% of token usage goes into context enrichment, not the final review."* Maintain a roughly 1:1 ratio of code-to-context in the LLM prompt.

### Claude Code / Devin — agentic tool-use, mostly no vectors

- **Approach:** the agent uses grep, read-file, ls, find-references-in-text directly. No embedding index. The agent itself navigates.
- **Why this works:** strong models can formulate effective search queries and iteratively narrow focus, mirroring how experienced developers approach unfamiliar codebases.
- **The 2026 trend:** several leading agents moved this direction. Vectors aren't dead, but they're no longer the foundation.

## The 2026 consensus on what to actually do

Synthesizing across all sources:

| Layer | Purpose | Implementations to consider |
|---|---|---|
| **AST symbol extraction** | Know what's defined where, with signatures | tree-sitter (66+ languages, de facto standard) |
| **Repo-map / file ranking** | LLM gets architectural lay of the land cheaply | Aider's graph-PageRank approach |
| **Reference / call-site lookup** | When a symbol changes, find who uses it | Sourcegraph-style precise references, OR tree-sitter call extraction, OR grep + symbol filter |
| **Semantic retrieval** | Find code "related to" the diff that's not obviously connected | Embeddings + vector search; can be deferred — agentic grep gets ~90% of the way |
| **Historical context** | Prior PRs on same files, prior reviewer comments | gh API + simple file-path matching (cheap) |
| **Test file inclusion** | Catch behavioral changes via the tests | Simple convention-based path matching (e.g., `X.py` → `test_X.py`, `tests/test_X.py`) |
| **Team standards / handbook** | Custom rules, coding conventions, architecture docs | Configurable file path (e.g., `.peer/standards.md`) included in prompt |
| **Long context** | Hold a lot in attention | Claude 1M / Gemini 2M; useful but doesn't replace structure |

The **practical baseline for a competitive PR review agent** is roughly:

1. Diff + ±N lines surrounding code per hunk (peer v0.1 baseline)
2. AST-extracted definitions of every symbol *modified* in the diff
3. AST-extracted call sites of every symbol modified (so reviewer sees blast radius)
4. Test files paralleling the changed files
5. Repo-map for architectural orientation (1-2k tokens)
6. Prior comments on the same file (cheap via gh)
7. Optional: team standards file
8. Optional: semantic retrieval for "related but not directly referenced" code

CodeRabbit, Greptile, Cursor all roughly converge on this stack. The 80–90% context ratio they report comes from steps 2–7.

## What this means for peer

The current `agent-v01` design (diff + ±20 surrounding lines + PR description + discussion) is **intentionally shallow** — it's a scaffold that proves the orchestration loop works end-to-end. It will produce *demonstrable but low-quality* reviews. That's fine for v0.1; we shouldn't expand its scope.

The codebase-understanding work is the **most important single v0.2 deliverable** for peer to be competitive rather than toy. It deserves a dedicated OpenSpec change proposal.

### Suggested v0.2 capability spec: `codebase-context`

In rough order of leverage:

**Tier 1 — must-ship for v0.2 (covers the 80% of context value):**
- Tree-sitter AST extraction for symbols modified in the diff (Python first; multi-language as a follow-up).
- Call-site / reference lookup for modified symbols (start with `grep` + symbol-aware filter; can upgrade to tree-sitter queries later).
- Test file inclusion via convention-based path matching.
- Configurable `peer/standards.md` (or `.peer.md`) inclusion for team-specific rules.

**Tier 2 — high-leverage, ship if v0.2 budget allows:**
- Aider-style repo-map (1–2k token architectural summary) for orientation.
- Prior comments on changed files (cheap via existing `gh` integration in `curate.py`).

**Tier 3 — defer to v0.3+:**
- Embeddings / vector search (Amazon Science result: grep + AST gets ~90%; we don't need vectors at v0.2).
- Cross-repo context.
- Linked-issue / Jira / Linear integration.
- Adaptive learning from accepted/rejected reviews (interesting but complex).

### Architectural rule, distilled from the research

> Spend 80% of token budget on context, 20% on the actual review prompt.

If `peer` v0.2 doesn't hit roughly this ratio, the reviews will be shallow.

## Open question this raises for `agent-v01`

Should `agent-v01` (currently proposed, not yet implemented) be **revised** to ship with stronger codebase context now, or **kept as-is** with codebase-understanding as a dedicated v0.2 change?

**Lean: keep as-is.** Reasons:
- The scaffold value of `agent-v01` is proving end-to-end orchestration works. Conflating it with codebase-understanding muddies both.
- v0.2 will be a substantial change deserving its own proposal, design, specs.
- We can be loud in v0.1's README about the known limitation: "v0.1 reviews use only diff + surrounding code; codebase-aware reviews land in v0.2 (`codebase-context` capability)."
- Splitting reduces risk: v0.1 can land and be useful for the *eval-against-history* validation loop even before the agent produces good reviews — the eval will simply show low scores, which is itself diagnostic.

**Alternative (worth considering):** if `peer`'s narrative is built on review quality from day 1, ship v0.1 with at minimum **Tier 1 codebase-context already included**. That means revising `agent-v01` to add a small `codebase-context` capability as part of the same change. Adds maybe 8–12 tasks to the v0.1 implementation but ensures v0.1 demos look competitive.

This is a real call to make. Documented here; resolved in the next OpenSpec change conversation.

---

## Academic literature review — papers from the last ~6 months

Added 2026-05-23 to ground the decision in peer-reviewed work, not just industry blogs.

### The five papers that most directly affect peer's design

#### 1. CodeCompass: Navigating the Navigation Paradox in Agentic Code Intelligence (Feb 2026, arXiv 2602.20048)

**Direct measurement of graph-navigation value.** CodeCompass exposes AST-derived structural dependencies (IMPORTS, INHERITS, INSTANTIATES edges) to Claude Code via an MCP server. On 258 automated trials across 30 benchmark tasks on a production FastAPI repository:

- **99.4% task completion on hidden-dependency tasks**
- vs 76.2% for vanilla agents
- vs 78.2% for BM25 retrieval
- That's a **+23.2 point improvement** over vanilla and +21.2 over BM25

**The catch — the adoption gap finding:** *58% of trials with graph access made zero tool calls.* Agents required explicit prompt engineering to consistently use the structural tool.

**Implication for peer:** graph-based AST navigation is empirically validated, not just hyped. AND — the system prompt has to explicitly instruct the agent to use the structural context, or the agent ignores it. This is a real implementation constraint for our prompt design.

#### 2. Is Grep All You Need? How Agent Harnesses Reshape Agentic Search (May 2026, arXiv 2605.15184)

Amazon Science paper comparing grep vs vector retrieval across multiple harnesses (Chronos, Claude Code, Codex, Gemini CLI).

**Headline finding:** grep generally yields higher accuracy than vector retrieval.

**Critical nuance:** *"overall scores depend strongly on which harness and tool-calling style is used, even when the underlying conversation data are the same."*

**Implication for peer:** strongly supports deferring vector embeddings indefinitely. Grep + AST + structured navigation is empirically sufficient. The framework's investment should be in the *harness and tool-calling design*, not in retrieval infrastructure.

#### 3. AACR-Bench: Evaluating Automatic Code Review with Holistic Repository-Level Context (Jan 2026, arXiv 2601.19494)

First multilingual, repository-level context-aware benchmark for LLM-enabled code review. Empirical evaluation of mainstream LLMs.

**Implication for peer:** this benchmark exists and we should consider running against it as a v0.3 milestone. It's also a useful sanity-check that any agent shipped *without* repository-level context will benchmark poorly, regardless of model strength.

#### 4. A Survey of Code Review Benchmarks and Evaluation Practices in Pre-LLM and LLM Era (Feb 2026, arXiv 2602.13377)

Meta-analysis of 99 papers (58 pre-LLM, 41 LLM-era). Proposes a 5-domain, 18-task taxonomy.

**Findings that matter for peer:**
- "Clear shift toward end-to-end generative peer review" — peer is on the right side of this trend.
- "Majority of benchmarks still treat natural-language human comments as primary ground truth, which introduces challenges due to noise, incompleteness, and variability in human review practices."

**Implication for peer:** our gold-standard approach (mined historical human comments) is the dominant pattern in the literature — *and* it has known limitations the survey calls out. We should be honest about this in our README and eval docs, not pretend it's an unqualified ground truth. The "variability in human review practices" issue is exactly why peer's eval is *per-repo* (each team's standards) rather than universal.

#### 5. Grounded AI for Code Review: Resource-Efficient Large-Model Serving in Enterprise Pipelines (Oct 2025, arXiv 2510.10290)

Production system pairing **static analysis findings + AST-guided context extraction** for PR-native code review.

**Implication for peer:** confirms that the production-grade architecture for code review in 2025–2026 combines static analysis + AST + LLM. Pure-LLM approaches are not where serious production systems landed.

### Supporting papers (less critical but reinforcing)

- **Codified Context: Infrastructure for AI Agents in a Complex Codebase** (Feb 2026, arXiv 2602.20478) — three-component memory architecture: hot-memory constitution + 19 domain-expert agents + cold-memory knowledge base of 34 spec docs. Reinforces the "team standards file" recommendation.

- **Codebase-Memory: Tree-Sitter-Based Knowledge Graphs for LLM Code Exploration via MCP** (Feb 2026, arXiv 2603.27277) — production-quality tree-sitter + KG + MCP implementation. **900+ stars in 4 weeks** of release. Tree-sitter as substrate is validated and growing.

- **Reliable Graph-RAG for Codebases: AST-Derived Graphs vs LLM-Extracted Knowledge Graphs** (Jan 2026, arXiv 2601.08773) — empirical comparison: AST-derived graphs via tree-sitter with bidirectional traversal outperform LLM-extracted KGs on Java codebases.

- **Rethinking Code Review Workflows with LLM Assistance: An Empirical Study** (May 2025, arXiv 2505.16339) — empirically identifies context switching and insufficient contextual information as primary code review pain points. Proposes RAG-based context assembly.

- **A-RAG: Scaling Agentic Retrieval-Augmented Generation via Hierarchical Retrieval Interfaces** (Feb 2026, arXiv 2602.03442) — hierarchical retrieval (keyword + semantic + chunk-read) for multi-hop QA, applied to coding agents.

- **LGTM! Characteristics of Auto-Merged LLM-based Agentic PRs** (MSR 2026 Mining Challenge) — *"AI tools are generating code faster than humans can properly review it; repositories are skipping review and auto-merging agentic PRs."* Direct evidence that the market need for reliable AI PR review is growing urgently.

- **MSR 2026 keynote (Patanamon Thongtanunam, University of Melbourne)** — argues for *"a shift from surface-level text generation toward accountable, goal-driven, agentic review systems that developers can trust."* peer's eval-first thesis is on-keel with this.

- **Context-Augmented Code Generation** (May 2026, arXiv 2605.08112) — 49% improvement in coding-agent decision compliance via product context. Reinforces that team-norms / API conventions matter.

### Revised lean on Path A vs Path B for peer's agent-v01

The academic evidence shifts the calculus from "Path A is the cautious lean" to **"Path B is empirically defensible, with one critical implementation note."**

**Why Path B is now my lean:**
- CodeCompass shows a +23-point improvement from structural graph navigation. That's the difference between a toy and a useful tool.
- AACR-Bench specifically requires repository-level context-aware reviews — a v0.1 without context would benchmark poorly out of the gate.
- The market urgency (LGTM paper, MSR keynote) means *time to a useful v0.1* matters more than ever.
- Path A's main argument (clean separation of concerns) is preserved by adding only Tier 1 codebase-context — the heavy embedding/vector/cross-repo work still defers to v0.3.

**The critical implementation note from CodeCompass:** *if you add structural context but don't explicitly prompt the agent to use it, 58% of runs ignore it.* This means the system prompt design (decision 7 of agent-v01) becomes more important than I weighted it. The default prompt must explicitly direct the agent to consult the extracted symbols, call-sites, and test files for each comment it produces.

**Refined recommendation for v0.1 (Path B-refined):**
- Add **tree-sitter symbol extraction** of modified definitions to v0.1 (most leverage per LOC)
- Add **call-site lookup via grep + AST filter** to v0.1
- Add **test file inclusion by convention** to v0.1
- **Defer** the team-standards file, repo-map (Aider-style), and prior comments retrieval to v0.2
- **Critically**, update the default system prompt to explicitly instruct the agent to use the structural context (per CodeCompass adoption-gap finding)

This is roughly 6–10 additional implementation tasks vs the current agent-v01 proposal. Still feasible as one change. Defensible as v0.1 because it crosses the "demonstrable but useful" threshold rather than shipping a known-toy first cut.

## Sources

- [Aider repo-map](https://aider.chat/docs/repomap.html)
- [Cursor codebase indexing](https://cursor.com/blog/secure-codebase-indexing) · [Cursor semantic search](https://cursor.com/blog/semsearch)
- [Sourcegraph Cody — how it understands your codebase](https://sourcegraph.com/blog/how-cody-understands-your-codebase)
- [Greptile — codebase-aware reviews](https://www.greptile.com/what-is-ai-code-review) · [Anatomy of a review](https://www.greptile.com/docs/code-review/first-pr-review)
- [CodeRabbit context engine](https://www.coderabbit.ai/blog/explainable-reviews-coderabbit-review-context-engine) · [CodeRabbit context engineering](https://www.coderabbit.ai/blog/context-engineering-ai-code-reviews) · [Massive codebases](https://www.coderabbit.ai/blog/how-coderabbit-delivers-accurate-ai-code-reviews-on-massive-codebases) · [LanceDB case study](https://www.lancedb.com/blog/case-study-coderabbit)
- [MindStudio — Why Cursor/Claude/Devin moved away from vector RAG](https://www.mindstudio.ai/blog/is-rag-dead-what-ai-agents-use-instead)
- [Code RAG and large codebases (2026)](https://dasroot.net/posts/2026/04/code-rag-llm-codebase-understanding/)
- [Codebase Intelligence research (Zylos 2026)](https://zylos.ai/research/2026-04-19-codebase-intelligence-repository-understanding-ai-agents)
- [Tree-Sitter knowledge graphs for LLM code exploration (arXiv 2603.27277)](https://arxiv.org/html/2603.27277v1)
- [Meta-RAG on Large Codebases (ICSE AGENT 2026)](https://conf.researchr.org/details/icse-2026/agent-2026-papers/6/Meta-RAG-on-Large-Codebases-Using-Code-Summarization)
- [AI Coding Assistants for Large Codebases (Kilo 2026)](https://blog.kilo.ai/p/ai-coding-assistants-for-large-codebases)

### Academic papers (added 2026-05-23)

- [CodeCompass: Navigating the Navigation Paradox (arXiv 2602.20048, Feb 2026)](https://arxiv.org/abs/2602.20048)
- [Is Grep All You Need? (arXiv 2605.15184, May 2026)](https://arxiv.org/abs/2605.15184)
- [AACR-Bench: Evaluating Automatic Code Review with Holistic Repository-Level Context (arXiv 2601.19494, Jan 2026)](https://arxiv.org/pdf/2601.19494)
- [A Survey of Code Review Benchmarks and Evaluation Practices (arXiv 2602.13377, Feb 2026)](https://arxiv.org/abs/2602.13377)
- [Grounded AI for Code Review (arXiv 2510.10290, Oct 2025)](https://arxiv.org/pdf/2510.10290)
- [Codified Context: Infrastructure for AI Agents in a Complex Codebase (arXiv 2602.20478, Feb 2026)](https://arxiv.org/abs/2602.20478v1)
- [Codebase-Memory: Tree-Sitter-Based KGs for LLM Code Exploration via MCP (arXiv 2603.27277, Feb 2026)](https://arxiv.org/html/2603.27277v1)
- [Reliable Graph-RAG for Codebases (arXiv 2601.08773, Jan 2026)](https://arxiv.org/html/2601.08773)
- [Rethinking Code Review Workflows with LLM Assistance (arXiv 2505.16339, May 2025)](https://arxiv.org/pdf/2505.16339)
- [A-RAG: Scaling Agentic RAG via Hierarchical Retrieval Interfaces (arXiv 2602.03442, Feb 2026)](https://arxiv.org/html/2602.03442v1)
- [LGTM! Characteristics of Auto-Merged LLM-based Agentic PRs (MSR 2026 Mining Challenge)](https://2026.msrconf.org/details/msr-2026-mining-challenge/61/LGTM-Characteristics-of-Auto-Merged-LLM-based-Agentic-PRs)
- [MSR 2026 keynote — Patanamon Thongtanunam](https://2026.msrconf.org/track/msr-2026-keynotes)
- [Context-Augmented Code Generation (arXiv 2605.08112, May 2026)](https://arxiv.org/html/2605.08112v1)
