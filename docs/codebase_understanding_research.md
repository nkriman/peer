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
