# OSS components — what to leverage vs build

> Built 2026-05-23. For each component in `peer`'s v0.1 (and a forward look at
> v0.2), what existing OSS to use, what to build, what to actively avoid.
> Companion to `docs/codebase_understanding_research.md`.

## Decision matrix for v0.1

| Component | Verdict | Choice | Notes |
|---|---|---|---|
| Diff parsing | **Borrow** | [`unidiff`](https://github.com/matiasb/python-unidiff) | PatchSet → PatchedFile → Hunk hierarchy fits our needs exactly |
| Tree-sitter bindings | **Borrow** | [`tree-sitter`](https://github.com/tree-sitter/py-tree-sitter) + [`tree-sitter-python`](https://github.com/tree-sitter/tree-sitter-python) | Mature (1.4k stars, v0.25.2 Sep 2025), per-language pip packages |
| Multi-language tree-sitter bundle | **Skip for v0.1** | (`tree-sitter-language-pack` later) | 306 languages, but overkill for Python-only v0.1; reconsider for v0.2 |
| Symbol extraction queries | **Build** | Custom tree-sitter queries | Small; no library does exactly our PR-shape extraction |
| **Call-site lookup** | **Reconsider — see below** | TBD: `ast-grep` vs ripgrep+tree-sitter filter | Material decision; recommendation included |
| Test-file discovery | **Build** | Trivial path-convention matcher | No library needed |
| GitHub data fetching | **Borrow** | `gh` CLI subprocess (already chosen) | Consistent with `curate.py` |
| LLM SDKs | **Borrow** | `anthropic` + `openai` (official) | Standard; structured-output features used |
| Pydantic schemas | **Borrow** | `pydantic` v2 | Standard |
| Token estimation | **Borrow** | `tiktoken` (OpenAI's) | Fast, accurate enough for budget enforcement |
| Logging | **Stdlib** | `logging` module | No third-party needed for v0.1 |
| CLI | **Stdlib** | `argparse` | Per scope research: skip `typer`/`click` for v0.1 |

## The decision worth re-opening: `ast-grep` instead of ripgrep + tree-sitter filter

Current agent-v01 design (Decision 11): two-stage call-site lookup — ripgrep for candidates, then tree-sitter re-parse to confirm matches are real call expressions.

Discovered in this research: [**`ast-grep`**](https://github.com/ast-grep/ast-grep) (14.1k stars, very active, written in Rust) does *exactly* the combined operation in one tool. Its pattern syntax (`$VAR.foo($ARGS)`) is AST-aware structural matching out of the box — no need to write a tree-sitter post-filter ourselves.

### Side-by-side

| | Current plan (ripgrep + tree-sitter filter) | `ast-grep` |
|---|---|---|
| Dependencies | `rg` (system binary) + `tree-sitter` Python lib | `ast-grep-cli` (single binary) OR Python API |
| Lines of code we'd write | ~80–120 (candidate gen + filter + edge cases) | ~20–30 (subprocess + parse output) |
| Speed | Fast (rg) + Python AST parse per candidate | Fast (Rust, AST-native) |
| Multi-language | Same approach repeated per language | Built-in multi-language support (uses tree-sitter under the hood) |
| Maintenance | Two moving parts (rg + tree-sitter versions) | One tool |
| False-positive rate | Good (we filter post-hoc) | Equal-or-better (AST-native, never sees string literals as candidates) |
| Footprint | rg often already installed; tree-sitter via pip | Need to install ast-grep (CLI subprocess) or ast-grep-py (Python API) |
| Risk | We're reinventing what ast-grep already does | Adds a dep + a learning curve for ast-grep's query language |

### Recommendation

**Switch to `ast-grep` for call-site lookup in v0.1.** Reasons:

1. **Less code to write and maintain.** Two-stage candidate-generation-then-filter is exactly the problem ast-grep solves; doing it ourselves is reinventing the wheel.
2. **Lower false-positive rate by construction.** AST-native matching never produces false positives from string literals or comments.
3. **Active project (14.1k stars, 4,102 commits, 176 releases).** More maintained than our handwritten alternative would be.
4. **Multi-language scaling.** When v0.2 adds TypeScript/Go/Rust, ast-grep already supports them — we just change the pattern.
5. **Falls back gracefully.** If ast-grep isn't installed, we can keep the ripgrep+filter approach as a fallback (Decision 14 already specifies graceful degradation for ripgrep).

**Implication for the spec:** Decision 11 in `design.md` should be revised. The `codebase-context` spec's call-site requirements stay the same semantically, but the implementation switches. Tasks 8.5–8.7 in `tasks.md` collapse.

### One caveat

The ast-grep Python API exists (`pip install ast-grep-py` per ast-grep.github.io) but the CLI is the primary surface. Subprocess invocation is simple but adds a system binary as a hard requirement. If we want a pure-Python library option, the bindings are usable but less documented than the CLI. **Lean: use the Python API (`ast-grep-py`) so we stay in-process; fall back to CLI subprocess if Python bindings have install issues.**

## Components to avoid

| Component | Why avoid |
|---|---|
| `grep-ast` (Aider's, paul-gauthier) | Stuck on tree-sitter 0.21 because `py-tree-sitter-languages` (its dep) is unmaintained. Active issue [#7](https://github.com/Aider-AI/grep-ast/issues/7). Don't pull this in to a new project. |
| `py-tree-sitter-languages` | Unmaintained for months. Stuck on old tree-sitter version. Use `tree-sitter-python` directly instead. |
| `PR-Agent` source code (vendoring/forking) | Per Qodo PR-Agent README analysis: "tightly coupled hybrid" — designed as an end-to-end tool, not a library. No public API for programmatic use. Limited library reusability per their own positioning. Take *inspiration* (their feature set), not *code*. |

## v0.2 / v0.3 forward look — what's already built we might use later

These don't apply to v0.1 (deferred per scope), but worth knowing exists when proposing v0.2:

### Aider's `repomap.py` — for v0.2 repo-map

**Repo:** [Aider-AI/aider](https://github.com/Aider-AI/aider), file `aider/repomap.py`
**License:** Apache 2.0 (compatible with peer's MIT)
**Size:** ~867 LOC (~693 real code)
**Architecture:**
- Tree-sitter + NetworkX PageRank to rank file importance
- Binary-search token-budget fitting
- LRU caching with SQLite (diskcache)
- Uses grep_ast for code-snippet rendering — note: this is the deprecated library above

**Vendoring feasibility:** "moderately favorable" — self-contained but tightly coupled to tree-sitter ecosystem and NetworkX. For v0.2, **adapt the algorithm, don't vendor the file** (the grep_ast dependency is poison; we'd need to replace it).

### Codebase-Memory (DeusData/codebase-memory-mcp)

**Repo:** [DeusData/codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp)
**900+ stars in 4 weeks of release (Feb 25, 2026).** v0.5.0 is now C-based (rewritten from Go), with all 64 language grammars vendored.

**What it is:** MCP server that exposes a persistent code knowledge graph. Sub-millisecond queries. 99% fewer tokens than feeding the LLM raw code.

**For peer:** can't be used *as a Python library* (it's an MCP server). But for v0.3+ if peer adds MCP integration, this would be a strong upstream dependency rather than something to rebuild. Also valuable as a reference architecture.

### CodeCompass (tpaip607/research-codecompass)

**Repo:** [tpaip607/research-codecompass](https://github.com/tpaip607/research-codecompass)
**What it is:** MCP server with Neo4j backend, exposing IMPORTS/INHERITS/INSTANTIATES edges extracted via static AST analysis.

**For peer:** research-grade, less production-polished. Same situation as Codebase-Memory — reference architecture, not a Python library, MCP-only integration path.

### `tree-sitter-language-pack` (Goldziher)

**Repo:** [Goldziher/tree-sitter-language-pack](https://github.com/Goldziher/tree-sitter-language-pack)
**306 languages bundled.** Polyglot API.

**For peer:** overkill for v0.1 (Python only). For v0.2 when we add TS/Go/Rust, *evaluate vs individual grammar packages*. Trade-off: heavier single dependency vs N pinned grammar packages.

## Net implications for agent-v01 (the current proposal)

If we adopt the recommendations above, the following changes to `agent-v01` are warranted before implementation begins:

1. **Add `unidiff` to `pyproject.toml` dependencies.** Use it in `src/peer/context.py` for diff hunk parsing instead of writing a hand-rolled parser (was implied in tasks 2.4 and 8.3).

2. **Switch call-site lookup to `ast-grep` (with ripgrep+filter as fallback).** Update `design.md` Decision 11 and collapse tasks 8.5–8.7 in `tasks.md`. Add `ast-grep-py` (or `ast-grep-cli` as subprocess) to dependencies. Keep ripgrep fallback per Decision 14 (graceful degradation).

3. **Add `tiktoken` to dependencies** for token-budget estimation (better than char-count/4 heuristic). Used in tasks 2.7 and 8.10.

4. **No change** to: GitHub access (gh CLI), LLM SDKs (anthropic, openai), Pydantic, logging, CLI — all already chosen correctly.

5. **Defer**: Aider repo-map adaptation (v0.2 `codebase-context` extension), MCP integration with Codebase-Memory / CodeCompass (v0.3+), `tree-sitter-language-pack` (when multi-language lands).

These are small, surgical revisions. The change still validates with the same overall shape; we just swap implementation primitives for off-the-shelf tools where ones already exist.

## Open question for the user

Adopt the three concrete revisions above? Specifically:

1. **`unidiff` for diff parsing** — uncontroversial, recommend yes
2. **`ast-grep` for call-site lookup (replacing ripgrep + tree-sitter filter)** — bigger call, recommend yes but flag for review
3. **`tiktoken` for token estimation** — uncontroversial, recommend yes

If yes to all, I'll update `agent-v01` (proposal/design/tasks) accordingly before any code lands.

## Sources

- [py-tree-sitter (tree-sitter/py-tree-sitter)](https://github.com/tree-sitter/py-tree-sitter) — 1.4k stars, v0.25.2 Sep 2025
- [tree-sitter-language-pack (Goldziher)](https://github.com/Goldziher/tree-sitter-language-pack) — 361 stars, 306 languages
- [ast-grep (ast-grep/ast-grep)](https://github.com/ast-grep/ast-grep) — 14.1k stars, Rust, AST-native search
- [ast-grep Python API docs](https://ast-grep.github.io/guide/api-usage/py-api.html)
- [Aider repomap.py source](https://github.com/Aider-AI/aider/blob/main/aider/repomap.py)
- [grep-ast (Aider-AI/grep-ast)](https://github.com/Aider-AI/grep-ast) — stale, avoid
- [PR-Agent (qodo-ai/pr-agent)](https://github.com/qodo-ai/pr-agent) — Apache 2.0, tightly coupled, not a library
- [Codebase-Memory MCP (DeusData)](https://github.com/DeusData/codebase-memory-mcp) — 900+ stars in 4 weeks, MCP server
- [CodeCompass (tpaip607/research-codecompass)](https://github.com/tpaip607/research-codecompass) — Neo4j-backed MCP graph
- [unidiff (matiasb/python-unidiff)](https://github.com/matiasb/python-unidiff) — PatchSet hierarchical diff parser
- [whatthepatch (cscorley/whatthepatch)](https://github.com/cscorley/whatthepatch) — alternative diff parser, flatter shape
