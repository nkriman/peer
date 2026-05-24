## Context

Following the competitive landscape research and the conventions experiment, the framework needs a first-class repo-root config file. This is the universal pattern in the space, and our `team_conventions=` constructor argument is too crude — it applies a single conventions blob to every file in every PR.

## Goals / Non-Goals

**Goals:**
- `.peer.yaml` config file is the single source of truth for per-team customization.
- Per-path globs let teams target different rules at different parts of the codebase.
- Severity floors/caps prevent prompt-induced calibration flips by structurally enforcing severity bounds per-path.
- Backward compatible: `Agent(team_conventions=...)` keeps working as a single-rule shortcut.
- Schema is strict (Pydantic-validated) so malformed configs fail loudly rather than silently misbehaving.

**Non-Goals:**
- Discovering `.peer.yaml` from the remote PR head (would require a second `gh api` call per review; deferred).
- Per-reviewer-backend config (mixing Claude for code, Haiku for nits — interesting but premature).
- Plugin / hook framework — `peer-config` is data, not code.
- Linter config (lives in `linter-context-v01`).

## Decisions

### 1. `.peer.yaml` at repo root is the canonical location

Discovered from the **caller's cwd** (or explicit `--config` flag). Not auto-fetched from PR head. Users running `peer review <pr_url>` from a different repo's cwd get that cwd's config, which may be empty or inappropriate — that's user error, surfaced via a INFO log telling the user which `.peer.yaml` was loaded.

**Why cwd:** `peer review` already requires `gh` auth and a local checkout for codebase context (the cached clone). The cwd is where the user is iterating; loading config from there matches every other dev tool's behavior (pyproject.toml, .gitignore, etc.).

**Alternative considered:** auto-fetch `.peer.yaml` from the PR head SHA via `gh api repos/.../contents/.peer.yaml?ref=<sha>`. Rejected for v0.1 — adds a network call per review and the failure modes (file doesn't exist on that branch, etc.) need their own handling.

### 2. Schema is strict + Pydantic-validated

The schema:

```yaml
# .peer.yaml
version: 1

# Global agent settings (override defaults)
agent:
  model: claude-sonnet-4-6      # optional; defaults to peer's default
  system_prompt_file: ...       # optional

# Per-path rules; first-matching-glob wins (order matters)
rules:
  - paths: ["src/auth/**", "src/security/**"]
    conventions_file: docs/security_conventions.md
    severity_floor: important   # all peer comments on these paths upgraded to at least 'important'

  - paths: ["tests/**", "**/test_*.py"]
    conventions_file: docs/test_conventions.md
    severity_cap: minor          # peer comments on test files capped at 'minor' max

  - paths: ["docs/**", "*.md", "*.rst"]
    severity_cap: nit            # docs nits stay nits

  - paths: ["**"]                # catch-all global rule
    conventions_file: docs/general_conventions.md
```

Pydantic schema validation rejects unknown keys, invalid glob patterns, severities not in `{critical, important, minor, nit}`, etc. The "version: 1" header lets us evolve the schema later without ambiguity.

**Why first-matching-glob wins for CONVENTIONS (not best-matching):** simpler mental model; users put more-specific rules first. Matches the pattern from `.gitignore`, `.gitattributes`, CodeRabbit's `.coderabbit.yaml` `path_instructions` list.

**EXCEPTION for severity bounds (per adversarial review 2.4):** severity `floor`/`cap` rules use "most-restrictive across all matching rules" semantics, NOT first-match. A file matching both `tests/**` (severity_cap=minor) AND `**` (severity_floor=important) gets the cap applied (minor wins — the more-restrictive bound). User mental model is "more specific rules tighten the constraint." Separated from conventions matching because the failure modes are different: a missed convention is a quality regression; a missed severity bound is a calibration regression. The order of evaluation: collect all matching rules' floors → pick the most restrictive (highest floor); collect all matching rules' caps → pick the most restrictive (lowest cap); apply floor first, then cap.

### 3. Severity floors/caps applied at comment-validation time

Currently `Agent.review` runs `_validate_comments(...)` to drop comments with unknown paths or out-of-hunk lines. Add a third pass: for each surviving comment, look up the matching rule via `config.for_path(comment.path)` and apply `severity_floor` (upgrade if below floor) / `severity_cap` (downgrade if above cap).

**Why at validation time, not prompt time:** prompt-level enforcement was the source of the calibration flip — telling the LLM "treat as nit or minor" caused over-correction. Structural enforcement (clamp after the fact) is more reliable and doesn't burn prompt tokens.

**Severity ordinal:** `critical < important < minor < nit` (lower number = more severe). Floor: `severity = max(current_ordinal, floor_ordinal)` interpreted as "no less severe than floor" — actually, since lower ordinal = more severe, floor of `important` means *at least* important, so promote critical/important to themselves and demote less-severe → important. Let's be explicit in code: `severity_floor=important` means "if peer chose `minor` or `nit`, upgrade to `important`; if peer chose `critical` or `important`, leave alone".

### 4. Conventions merging: per-path takes effect for files in that path

For each comment, the config provides the matched rule's `conventions_file` content. But conventions are injected into the system prompt before the agent generates comments — and we don't know in advance which files the agent will comment on. So the prompt-injection happens for the **union of conventions across all paths in the PR diff**.

E.g., a PR that modifies both `src/auth/foo.py` and `tests/test_foo.py` has its prompt augmented with both `security_conventions.md` and `test_conventions.md`. The agent gets all relevant guidance; the path-scoping then only affects severity post-hoc.

**Why union of conventions in prompt + per-path floors/caps for severity:** keeps the agent informed about everything; lets structural caps prevent over-application.

### 5. Auto-detect `.peer.yaml`, but allow explicit override

`Agent()` (no config arg) calls `load_config(Path.cwd())` which looks for `.peer.yaml` in cwd. If not present, returns a default empty `PeerConfig()` (no rules). If present, loads + validates + logs `INFO: loaded peer config from <path>`.

`Agent(config=PeerConfig(...))` — accept a programmatic config.
`Agent(config_file=Path(...))` — load from explicit path.
`Agent(team_conventions=...)` — legacy shortcut, equivalent to a single-rule config with `paths: ["**"]`.

CLI commands accept `--config PATH` for explicit override at the CLI layer.

### 6. Empty / missing config is the safe default

A repo without `.peer.yaml` runs peer with no rules, no severity bounds, the default reviewer model and the default system prompt. Identical behavior to peer v0.1. The config file is **purely additive**.

### 6b. Consolidate conventions-injection mechanisms (per adversarial review 5.6)

Before this change there were FOUR places conventions/instructions text could be injected into the system prompt: (1) `Agent.system_prompt` (full replace), (2) `Agent.team_conventions` (legacy single blob), (3) `PeerConfig.agent.extra_instructions`, (4) `PeerConfig.rules[*].conventions_file` (per-path).

**Resolved (this change locks in):**

- `Agent.system_prompt` — full prompt override (existing). KEEPS.
- `Agent.team_conventions` — legacy, emits DeprecationWarning, equivalent to a single-rule PeerConfig. KEEPS for back-compat; removal in v1.0.
- `PeerConfig.agent.extra_instructions` — NEW, short ad-hoc tweak. KEEPS.
- `PeerConfig.rules[*].conventions_file` — per-path conventions docs. KEEPS.

There are now THREE viable mechanisms (system_prompt as full replace, extra_instructions as short global addition, per-path conventions for path-scoped additions) + 1 deprecated path (team_conventions). The CLI's `peer config validate` (future) will warn when a user combines `system_prompt` (full replace) with conventions (additive) — semantically these are independent levels, but in practice combining them is confusing. Documentation makes the precedence clear: `system_prompt` (if set) REPLACES the default; `extra_instructions` + `conventions_file` are APPENDED. Same prompt-construction order: `[system_prompt OR default] + extra_instructions + conventions for matched paths`.

### 7. PyYAML is the right dep

Stdlib-only YAML is not great. PyYAML is the de facto standard, small footprint, MIT-compatible. We could use `tomllib` (stdlib, but the syntax is awkward for nested lists). YAML is closer to what users expect for config files in this space.

## Risks / Trade-offs

- **[Risk]** Path globs are easy to get wrong. **Mitigation:** Pydantic validator rejects empty `paths:` lists; `peer config validate` CLI command (deferred to future) would let users dry-run a path against the config. For v0.1, document common gotchas in README.
- **[Risk]** Conventions text inflates the system prompt — N conventions docs across a multi-area PR multiply context cost. **Mitigation:** dedupe identical file references; budget guidance in docs (recommend keeping conventions files small, ~500 lines each).
- **[Risk]** Severity floor/cap can mask real signal from the agent (e.g., agent says "critical, this is a security bug" and a `severity_cap=minor` masks it). **Mitigation:** log INFO whenever a cap/floor changes a comment's severity, so users see when the config is overriding agent judgment. Add docstring guidance: don't use caps to silence signal you don't want to hear.
- **[Risk]** First-matching-glob wins is surprising for users who expect best-matching. **Mitigation:** documentation up front; example file with comments showing the order.
- **[Risk]** YAML's whitespace sensitivity bites first-time users. **Mitigation:** ship a `dataset/reference/peer.yaml.example` as a worked template.

## Open Questions

None blocking. The deferred questions:
- Should `.peer.yaml` support multiple files (`.peer.d/*.yaml`)? Defer until a user asks.
- Should config support inline-conventions text instead of always pointing at a file? Defer; file-only is cleaner for now.
- Should the agent receive the matched rule for each PR file, e.g., so it can self-cite the convention by name? Worth exploring in a follow-on once we see how the v0.1 plays out.
