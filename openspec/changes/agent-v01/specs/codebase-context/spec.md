## ADDED Requirements

### Requirement: Extract definitions of modified symbols via tree-sitter
The framework SHALL parse each modified source file in the PR diff using tree-sitter and extract the definitions (functions, methods, classes) whose source spans overlap with any diff hunk. Each extracted definition is exposed as a `Symbol` with `name`, `path`, `kind` (`function` / `method` / `class`), `signature`, `start_line`, `end_line`, and `enclosing_qualifier` (e.g., the class name for a method).

#### Scenario: Function modified in a Python file
- **WHEN** a PR modifies lines inside the body of `def foo(x: int) -> str:` in `src/foo.py`
- **THEN** the resulting `CodebaseContext` includes a `Symbol` with `name="foo"`, `kind="function"`, `path="src/foo.py"`, the full signature, and the start/end lines

#### Scenario: Method inside a class is modified
- **WHEN** a PR modifies lines inside `class Bar: def baz(self): ...`
- **THEN** the resulting `Symbol` has `kind="method"`, `enclosing_qualifier="Bar"`

#### Scenario: Class definition itself modified (signature change)
- **WHEN** a PR modifies the `class Bar(Base):` line (e.g., changes the base class)
- **THEN** the resulting `Symbol` has `kind="class"` and `signature` captures the new declaration

#### Scenario: Newly added function
- **WHEN** a PR adds a brand-new function `def new_thing(): ...` to a file
- **THEN** that function appears as a `Symbol` in the codebase context with its definition

#### Scenario: Function deleted in the PR
- **WHEN** a PR removes a function that previously existed
- **THEN** that removal is captured as a `Symbol` entry with `kind="function"` and `deleted=True`, sourced from the parent commit's version of the file

#### Scenario: Unsupported language file
- **WHEN** a PR modifies a `.ts` or `.go` file (no tree-sitter grammar shipped in v0.1)
- **THEN** the file is recorded as `language_unsupported` in `CodebaseContext.unsupported_files` without aborting the review; the LLM still sees the raw diff for the file

#### Scenario: Tree-sitter parse failure (syntax error in the file)
- **WHEN** tree-sitter cannot parse a supported-language file (e.g., genuinely malformed code)
- **THEN** the file is logged as a parse failure, added to `CodebaseContext.parse_failures`, and skipped for symbol extraction; the review still proceeds

### Requirement: Find call sites of modified symbols across the repository
For each modified `Symbol`, the framework SHALL locate call sites elsewhere in the repository and return them as `CallSite` records with `symbol_name`, `path`, `line`, and a short snippet (default ±3 lines).

#### Scenario: External caller exists
- **WHEN** function `foo` in `src/foo.py` is modified and `src/bar.py` contains `result = foo(42)`
- **THEN** `CodebaseContext.call_sites` includes a `CallSite` referencing `src/bar.py` at the matching line, with the surrounding ±3 lines

#### Scenario: No callers found
- **WHEN** a modified symbol has zero call sites found in the repository
- **THEN** the symbol is annotated with `call_sites_found=0` (useful signal for the agent: dead code or new code)

#### Scenario: Symbol name collides with unrelated identifiers
- **WHEN** a symbol's name matches text in unrelated contexts (e.g., a string literal or a comment)
- **THEN** the framework filters out false positives via AST-aware matching; the returned `CallSite` records refer only to actual call expressions on the symbol

#### Scenario: Call-site engine fallback chain
- **WHEN** the primary call-site engine is unavailable on the host (e.g., `ast-grep` not installed) and a fallback engine is available (`ripgrep`, then pure-Python scan)
- **THEN** the framework transparently uses the next available engine, logs a one-time `WARNING` per fallback rung, and produces functionally identical `CallSite` results (only speed differs)

#### Scenario: Cap on call sites per symbol
- **WHEN** a modified symbol has more than `max_call_sites_per_symbol` call sites (default 5)
- **THEN** the framework includes the first N (in stable repo-order), records the truncation count, and adds a `truncated=True` flag

### Requirement: Discover related test files by path convention
The framework SHALL identify test files related to modified source files using configurable path conventions and include each found test file's content (capped) in the `CodebaseContext`.

#### Scenario: Default Python pytest convention
- **WHEN** the modified file is `src/foo.py`
- **THEN** the framework looks (in order) for `tests/test_foo.py`, `src/test_foo.py`, `tests/foo_test.py`, `test_foo.py`; the first existing match is included as a `TestFile`

#### Scenario: User-supplied custom convention
- **WHEN** the user configures `test_path_conventions=["spec/{stem}_spec.py"]`
- **THEN** the framework uses that pattern (with `{stem}`, `{name}`, `{path}` substitutions) instead of defaults

#### Scenario: No matching test file
- **WHEN** no convention match exists for a modified source file
- **THEN** the source file is recorded under `CodebaseContext.untested_files` (signal to the agent: the change has no parallel tests)

#### Scenario: Test file exceeds character cap
- **WHEN** a matched test file exceeds `max_test_file_chars` (default 5000)
- **THEN** the file is truncated to the cap with a trailing `... (truncated, N chars)` marker; `truncated=True` is flagged

### Requirement: Assemble a typed CodebaseContext object
The framework SHALL produce a `CodebaseContext` Pydantic object with the following fields:

- `modified_symbols: list[Symbol]`
- `call_sites: list[CallSite]`
- `related_tests: list[TestFile]`
- `untested_files: list[str]`
- `unsupported_files: list[str]`
- `parse_failures: list[str]`
- `token_estimate: int`
- `truncations: dict[str, int]` (which categories had items dropped or truncated)

#### Scenario: Well-typed output
- **WHEN** `gather_codebase_context(pr_context)` is called for any PR
- **THEN** the returned `CodebaseContext` validates against the Pydantic schema with all fields populated (possibly with empty lists)

### Requirement: Respect a token budget for the assembled context
The `CodebaseContext` SHALL fit within a configurable token budget (default `30_000` tokens, separate from and additive to the existing PR-context budget). When the estimated total exceeds the budget, the framework SHALL drop the lowest-priority items first.

**Priority order (highest to lowest):**
1. `modified_symbols` (always kept; if these alone exceed budget, raise `CodebaseContextTooLarge`)
2. `call_sites` for modified symbols (drop excess by symbol-distance / repo-order)
3. `related_tests` (truncate file content first, then drop entire files)

#### Scenario: Within budget, nothing dropped
- **WHEN** the assembled `CodebaseContext` is under the configured `max_tokens`
- **THEN** all extracted items are returned unmodified; `truncations` is empty

#### Scenario: Budget exceeded — call sites and tests trimmed
- **WHEN** the assembled context exceeds the budget but `modified_symbols` alone do not
- **THEN** lower-priority items (call sites first, then tests) are dropped to fit; `truncations` records counts (e.g., `{"call_sites": 12, "related_tests_truncated": 3}`)

#### Scenario: Even modified symbols exceed budget
- **WHEN** the modified-symbols list alone exceeds the budget (e.g., very large refactor PR)
- **THEN** the framework raises `CodebaseContextTooLarge` with the measured size and the configured limit

### Requirement: Language coverage starts with Python with explicit extension seam
v0.1 SHALL ship with the tree-sitter Python grammar wired in. The architecture SHALL expose a `LanguageGrammar` registry so additional languages (TypeScript, Go, Rust, etc.) can be added in a single change without modifying the extraction pipeline.

#### Scenario: Python file is parsed
- **WHEN** a PR modifies a `.py` file
- **THEN** the Python tree-sitter grammar is used to extract symbols

#### Scenario: New language registration
- **WHEN** a future change registers a `LanguageGrammar` for TypeScript (`.ts`, `.tsx`)
- **THEN** TypeScript files in PRs begin being parsed without modification to the call-site / test-discovery / budgeting logic

### Requirement: Graceful degradation on missing optional dependencies
The codebase-context capability SHALL detect missing optional dependencies and degrade rather than fail.

#### Scenario: tree-sitter Python grammar missing
- **WHEN** `tree-sitter-python` cannot be imported at runtime (e.g., install issue)
- **THEN** the framework logs an `ERROR` with the install fix and returns a `CodebaseContext` with empty `modified_symbols`/`call_sites`; the review still proceeds with PR context only

#### Scenario: Primary call-site engine missing, fallbacks available
- **WHEN** the primary call-site engine is unavailable (e.g., `ast-grep` not installed) but at least one fallback engine is (`ripgrep` and/or Python-only)
- **THEN** call-site lookup uses the next available engine with a one-time `WARNING`; functionality is preserved
