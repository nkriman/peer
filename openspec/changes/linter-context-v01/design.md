## Context

CodeRabbit's competitive advantage in the Macroscope benchmark comes partly from leveraging 40+ existing linters. We can match that pattern cheaply: ruff covers most Python style + simple-correctness; mypy covers type errors. Both shell out, produce JSON, and run in seconds on the modified files in a typical PR.

Our `agent-v01` Decision 11 (call-site lookup via ast-grep) and Decision 13 (default system prompt explicitly names codebase context fields) set the pattern: pluggable extension points + the agent's prompt explicitly directs it to consult each context source. Linter findings become a new such source with the same architectural treatment.

## Goals / Non-Goals

**Goals:**
- Two Linter implementations (ruff, mypy) ship as defaults; both gracefully degrade if their CLI isn't installed.
- `LinterFinding`s are a first-class field on `CodebaseContext`; appear as their own section in the system prompt with explicit "use these or reference them; don't re-discover" guidance.
- Agent comments reduce duplication with linter output: if ruff flagged it, agent shouldn't re-flag it.
- Linter execution is scoped to the PR's modified files (not the whole repo) — cheap and fast.

**Non-Goals:**
- A general "lint everything in the repo" mode.
- JavaScript/TypeScript linters (deferred; Python-only).
- Bundling ruff/mypy as Python deps (they're already widely-installed CLIs; bundling forces a version pin that's painful for users).
- Linter rule customization at peer level (users configure their own `.ruff.toml` / `pyproject.toml`; peer just runs whatever's configured).
- Applying linter fixes — that's `patch-suggestions-v01`.

## Decisions

### 1. Linter Protocol with two default impls

```python
class Linter(Protocol):
    name: str  # "ruff", "mypy", ...
    def lint(self, repo_path: Path, target_files: list[str]) -> list[LinterFinding]: ...

@dataclass
class LinterFinding:
    linter: str
    path: str
    line: int
    column: Optional[int]
    rule_id: str          # e.g. "E501", "no-redef"
    severity: str         # tool-native; we normalize to nit/minor/important/critical via a per-tool map
    message: str
    fix_suggestion: Optional[str] = None  # only for ruff --fix or mypy errors with suggested code
```

Default implementations: `RuffLinter` and `MypyLinter`. Both shell out via `subprocess.run` to `ruff check --output-format=json <files>` and `mypy --no-error-summary --show-error-codes --show-column-numbers <files>` respectively, parse the output, and project into `LinterFinding`.

**Why Protocol + ducked-typed default impls:** matches the rest of peer's framework shape (`Reviewer`, `RawSampleSource`, `EvalMetric` all follow this pattern).

### 2. Severity normalization is per-linter

Each linter has its own severity model (ruff: rules grouped F/E/W/etc; mypy: error/note). Each default impl includes a per-tool normalization map to peer's severity scale:

- ruff: most rules → `nit` or `minor`; specific rule sets (security: `S*`, bugs: `B*`) → `important`
- mypy: `error` → `important`; `note` → `nit`

The normalization map is exposed on the linter class so users can override:

```python
my_ruff = RuffLinter(severity_map={"S": "critical", "B": "important", ...})
```

**Why per-linter, not global:** linter severity models are deeply different. A global "linter severity" enum would lose information.

### 3. Linter execution is scoped to modified Python files

`gather_codebase_context` already knows the modified files in the PR diff. It runs each Linter on just those files (target_files=[paths]). Repo-wide linting is out of scope.

**Why scoped:** speed. A typical PR has 1-10 modified files; linting them takes <1s. Full-repo lint for Django would be 30+ seconds — too slow for a per-PR review.

**Trade-off:** misses cross-file lint issues (e.g., mypy's "this caller now has the wrong type" when a callee changes). Mitigation: mypy's `--follow-imports=normal` behavior catches some of this automatically; for the rest, deferred.

### 4. Graceful degradation when linter CLI is missing

Each default impl checks `shutil.which("ruff")` / `shutil.which("mypy")` at instantiation. If missing, the linter still instantiates but `lint(...)` logs a one-time WARNING with the install command (`pip install ruff` etc.) and returns `[]`. Mirrors `agent-v01` Decision 14 (graceful degradation for ast-grep).

### 5. Token budget treats linter findings as compressible

Each `LinterFinding` is ~30-50 tokens when serialized. For a PR with 50 lint findings, that's ~2500 tokens — meaningful but tractable. Token-budget enforcement priority order (codebase-context spec Requirement: token budget):

1. `modified_symbols` (always kept)
2. `call_sites`
3. **`linter_findings`** (new; same tier as call_sites; trim oldest/lowest-severity first)
4. `related_tests`

**Why this position:** linter findings are higher signal than call sites for many PR types (especially style-heavy ones). Putting them above tests but below symbols + call sites lands in the middle, which feels right empirically.

### 6. Default system prompt updated

Current prompt (Decision 13 of agent-v01) names `modified_symbols`, `call_sites`, `related_tests`, `untested_files`. Add `linter_findings` to that list with explicit guidance:

> Linter findings (ruff, mypy) are pre-computed for the modified files. Surface them as-is — quote the rule_id and message in your comment, don't re-discover. If a linter already flagged something, don't post a duplicate; cite the linter in your reasoning and move on.

This prevents the agent from "discovering" `E501 line too long` independently and posting it at `minor` severity when ruff is already flagging it.

### 7. Config integration: `.peer.yaml` lists enabled linters

`peer-config-v01`'s `.peer.yaml` gets a `linters:` section:

```yaml
linters:
  - name: ruff
    enabled: true
    severity_map: {S: critical, B: important}
  - name: mypy
    enabled: true
```

Default (no config) enables both. Per-path can disable linters (e.g., docs/* → no mypy). Severity floors/caps from `peer-config-v01` apply equally to linter-sourced comments — they're treated like any other comment for severity bounds.

## Risks / Trade-offs

- **[Risk]** Linter execution slows down review (~1-3s per linter). **Mitigation:** run linters in parallel via `concurrent.futures`; cap total budget at 30s before logging warning + skipping remaining.
- **[Risk]** Linters fight with custom team conventions (e.g., a team disables ruff's f-string rule but the conventions doc says "use f-strings only for plain access"). **Mitigation:** document that linter config is authoritative for what they cover; conventions docs are for what linters don't cover.
- **[Risk]** Mypy is famously slow on large codebases (~10s+ even for one file due to import resolution). **Mitigation:** mypy is disabled in the default `peer-config-v01` if not explicitly enabled; users opt in.
- **[Risk]** Linter output can be enormous (thousands of findings) on legacy codebases. **Mitigation:** cap `findings_per_file=50` default; truncate oldest after cap. Logged as truncation in CodebaseContext.
- **[Risk]** Subprocess shell-out fragility (mypy crashes, ruff config conflicts). **Mitigation:** wrap each subprocess call in try/except; log error, return empty findings, continue review.

## Open Questions

None blocking. Deferred:
- Should we ship a `PylintLinter` / `SemgrepLinter` defaults? Wait for a user to ask.
- Should linter output influence agent severity directly (e.g., ruff B-rule → agent must flag as at-least-important)? Probably no — current "soft suggestion via prompt" is enough; structural enforcement adds rigidity.
- Whole-repo linting for periodic baseline checks. Out of scope for `linter-context-v01`.
