## ADDED Requirements

### Requirement: Linter Protocol with one default Python implementation

The framework SHALL define a `Linter` Protocol with `lint(repo_path: Path, target_files: list[str]) -> list[LinterFinding]` and provide ONE default implementation: `RuffLinter`. It SHALL shell out to the `ruff` CLI, parse JSON output, project into `LinterFinding` records. A second example impl (`MypyLinter`) ships in `examples/mypy_linter.py` (NOT in the default-shipped path) per adversarial review 5.3 — mypy needs per-project config to be useful and shouldn't be a silent default.

#### Scenario: Ruff produces findings for modified files

- **WHEN** `RuffLinter().lint(repo_path, ["src/foo.py"])` is called and ruff finds two issues (one `E501 line too long`, one `F401 unused import`)
- **THEN** the returned list contains two `LinterFinding` records with `linter="ruff"`, the correct `rule_id`, `path`, `line`, `severity` (normalized), and message

#### Scenario: Example MypyLinter (in examples/, not default)

- **GIVEN** the user has copied `examples/mypy_linter.py` into their project and configured it for their codebase
- **WHEN** `MypyLinter().lint(repo_path, ["src/foo.py"])` is called and mypy reports one type error
- **THEN** the returned list contains a `LinterFinding` with `linter="mypy"`, the error code, path/line/column, `severity="important"`, and the type-error message — and this only works because the user has set up mypy's project config correctly

#### Scenario: Custom Linter satisfies Protocol

- **WHEN** a user defines `class MyLinter: name = "mylinter"; def lint(self, repo_path, target_files): return [LinterFinding(...)]`
- **THEN** the class satisfies the `Linter` Protocol and can be passed into `gather_codebase_context(..., linters=[MyLinter()])`

### Requirement: LinterFinding has typed schema

The framework SHALL define a `LinterFinding` Pydantic model with: `linter: str`, `path: str`, `line: int`, `column: Optional[int]`, `rule_id: str`, `severity: Severity`, `message: str`, `fix_suggestion: Optional[str]`.

#### Scenario: Round-trip via Pydantic

- **WHEN** a `LinterFinding` is created with all required fields, then serialized via `model_dump_json` and reparsed via `model_validate_json`
- **THEN** the round-trip preserves all field values

### Requirement: CodebaseContext extended with linter_findings

The `CodebaseContext` Pydantic model SHALL gain a `linter_findings: list[LinterFinding] = Field(default_factory=list)` field. The field is populated by `gather_codebase_context` when linters are configured.

#### Scenario: Empty by default when no linters configured

- **WHEN** `gather_codebase_context(pr_context)` is called with no `linters=` argument
- **THEN** the returned `CodebaseContext.linter_findings` is an empty list

#### Scenario: Populated when linters supplied

- **WHEN** `gather_codebase_context(pr_context, linters=[RuffLinter(), MypyLinter()])` is called on a PR modifying Python files
- **THEN** the returned `linter_findings` contains all `LinterFinding`s produced by both linters across the modified Python files

### Requirement: Linter execution scoped to modified Python files

`gather_codebase_context` SHALL pass only the PR's modified `.py` files as `target_files` to each linter; non-Python modified files are excluded from linter execution.

#### Scenario: Non-Python file in PR

- **WHEN** a PR modifies `docs/api.md` (Markdown) and `src/foo.py` (Python)
- **THEN** linters are invoked only with `target_files=["src/foo.py"]`

### Requirement: Graceful degradation when linter CLI missing

Each default Linter implementation SHALL check for the presence of its CLI on `PATH` (via `shutil.which`) on first `lint(...)` call. If missing, the linter logs a one-time WARNING with the install command and returns an empty list; subsequent calls return empty silently.

#### Scenario: Ruff not installed

- **WHEN** `RuffLinter().lint(...)` is called and `ruff` is not on `PATH`
- **THEN** the returned list is empty, and a `WARNING peer.linters.ruff: ruff not found on PATH; install with 'pip install ruff'` is logged exactly once per process

### Requirement: Per-linter severity normalization

Each default Linter implementation SHALL map tool-native severities to peer's severity scale (`critical/important/minor/nit`). The mapping SHALL be overridable via a `severity_map=` constructor argument.

#### Scenario: Ruff default mapping

- **WHEN** ruff produces an `E501` finding (style)
- **THEN** `RuffLinter().lint(...)` returns a `LinterFinding` with `severity="nit"`

#### Scenario: Ruff S-rule maps to important by default

- **WHEN** ruff produces an `S101` finding (security: assert usage)
- **THEN** the default `RuffLinter` returns `severity="important"`

#### Scenario: Custom severity map override

- **WHEN** `RuffLinter(severity_map={"S": "critical"}).lint(...)` is called and ruff produces an `S101` finding
- **THEN** the returned `LinterFinding` has `severity="critical"`

### Requirement: Token budget treats linter findings as priority-3

The token-budget enforcement in `gather_codebase_context` SHALL apply this drop order when over budget: drop `related_tests` first, then trim `linter_findings`, then trim `call_sites`. `modified_symbols` is always kept.

#### Scenario: Over budget, tests dropped first

- **WHEN** the assembled CodebaseContext exceeds `max_tokens` and tests can be removed to fit
- **THEN** tests are removed before any `linter_findings` are dropped

#### Scenario: Over budget, linter findings trimmed before call sites

- **WHEN** dropping tests is insufficient to fit budget
- **THEN** linter findings are trimmed (lowest-severity first) before call_sites are trimmed

### Requirement: System prompt directs agent to consult linter findings

The default system prompt (per `agent-v01` Decision 13) SHALL be updated to name `linter_findings` alongside the existing `modified_symbols / call_sites / related_tests / untested_files`. The prompt SHALL also direct the agent to surface linter-pre-flagged issues as-is (quoting the `rule_id` + `message`) rather than re-discovering and posting duplicates.

#### Scenario: Default prompt includes linter_findings reference

- **WHEN** an `Agent` is instantiated with no `system_prompt` override
- **THEN** `agent.system_prompt` contains the string `linter_findings` and an instruction to "cite the linter rule_id when surfacing a linter-flagged issue; don't post duplicate comments for issues a linter already caught"

### Requirement: Prompt formatter renders linter findings section

The `format_prompt(context, codebase_context)` helper SHALL render a `## LINTER FINDINGS` section when `codebase_context.linter_findings` is non-empty.

#### Scenario: Linter findings rendered

- **WHEN** `codebase_context.linter_findings` contains 2 ruff findings and 1 mypy finding
- **THEN** the rendered prompt contains a `## LINTER FINDINGS` header followed by 3 entries each formatted as `[<linter> <rule_id> <severity>] <path>:<line> — <message>`

#### Scenario: Section omitted when empty

- **WHEN** `codebase_context.linter_findings` is empty
- **THEN** the rendered prompt does NOT contain a `## LINTER FINDINGS` section

### Requirement: PeerDeps.linters is the single source of truth for active linters

Per adversarial review 3.4 — `PeerDeps.linters` SHALL be the SOLE source of truth for which linters run. `.peer.yaml`'s `linters:` section is a HELPER that, when an Agent auto-loads config (per peer-config-v01), populates `_default_deps.linters` with the resolved instances. Users passing `PeerDeps(linters=[...])` explicitly SHALL always bypass config-derived linters entirely. There SHALL NOT be a separate `PeerConfig.enabled_linters()` accessor that returns linters independently of `PeerDeps.linters`.

`.peer.yaml` SHALL accept a `linters:` top-level section that lists which linters are enabled and per-linter overrides (severity_map, etc.). The resolver builds a `list[Linter]` of instances and assigns to `_default_deps.linters`.

#### Scenario: Linters configured in .peer.yaml

- **WHEN** `.peer.yaml` contains `linters: [{name: ruff, enabled: true}, {name: mypy, enabled: false}]`
- **THEN** the Agent runs reviews with only `RuffLinter` enabled

#### Scenario: Default (no config) enables ruff only

- **WHEN** no `.peer.yaml` is present
- **THEN** `RuffLinter` is enabled by default; `MypyLinter` is NOT enabled (per Decision 5 of design.md — mypy too slow for default)

### Requirement: Linters flow through PeerDeps

`Linter` instances SHALL be passed to `gather_codebase_context` via `PeerDeps.linters` (per `peer-deps-v01`). The Agent SHALL extract `deps.linters` from the supplied `PeerDeps` and pass them into `gather_codebase_context(..., linters=deps.linters)`. Users may pass linters directly via `PeerDeps(linters=[MyLinter()])` for ad-hoc / test scenarios, bypassing `.peer.yaml`.

#### Scenario: Linters from PeerDeps

- **WHEN** `Agent(...).run(pr_url, deps=PeerDeps(linters=[RuffLinter()]))` is called
- **THEN** `gather_codebase_context` receives `linters=[RuffLinter()]` and runs ruff on the modified Python files

#### Scenario: Empty PeerDeps.linters runs no linters

- **WHEN** `Agent(...).run(pr_url, deps=PeerDeps(linters=[]))`
- **THEN** no linter is run; `cc.linter_findings` is empty

#### Scenario: Config and explicit linters: explicit wins

- **WHEN** `PeerDeps(config=cfg_with_mypy_enabled, linters=[RuffLinter()])` is passed
- **THEN** only RuffLinter runs (explicit linters argument takes precedence over config-derived defaults)
