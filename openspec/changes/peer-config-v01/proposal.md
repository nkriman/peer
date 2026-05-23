## Why

Every competitive AI-code-review tool ships a repo-root config file (CodeRabbit's `.coderabbit.yaml`, Macroscope's `.macroscope/*.md`, Greptile's natural-language instructions per team). The pattern is universal because:

1. **Per-path scoping matters.** Style rules for `tests/` are different from `src/auth/`. Without per-path scoping, conventions either over-apply or under-apply.
2. **Severity floors/caps per path** prevent the calibration-flip we saw in the conventions experiment (a single global "treat style as nit or minor" instruction over-corrected globally).
3. **Configuration in the repo, not in client code** lets teams version-control their reviewer setup, share it across machines, and review changes via PR.

`agent-v01` Decision 3 deferred this to "a future change once we see what parameters users actually want exposed declaratively." The conventions experiment + competitive landscape research surfaced the need clearly.

## What Changes

- Add `.peer.yaml` config file format (root-level in a repo) with conventions, severity floors/caps, and reviewer-model overrides per-path-glob.
- Add `peer.config.PeerConfig` Pydantic schema for the file.
- Add `peer.config.load_config(repo_path)` that finds + parses `.peer.yaml` (or returns a default empty config if absent).
- Add resolver `PeerConfig.for_path(path)` that returns the merged config for a given file path, applying per-path glob overrides on top of global defaults.
- Extend `Agent.__init__` to optionally accept `config: PeerConfig` or `config_file: Path`, with conventions loaded automatically per-PR file paths.
- Severity floor/cap enforcement: a Comment whose path matches a glob with `severity_cap=nit` gets its severity capped at `nit`; analogous for floors. Applied in the same comment-validation pass that already drops out-of-hunk comments.
- Document the `.peer.yaml` format with a worked example.

## Capabilities

### New Capabilities

- `peer-config`: `.peer.yaml` loading, schema validation, per-path resolution, and per-path severity floor/cap enforcement.

### Modified Capabilities

- `pr-review-agent` (from `agent-v01`): `Agent.__init__` accepts an optional `PeerConfig`. When configured, per-PR file paths are checked against the config's per-path glob rules and the matching conventions / severity rules are applied. No change to the `Reviewer` Protocol.

## Impact

- **Code**: new `src/peer/config.py` (PeerConfig schema + loader + path resolver). Updates to `src/peer/agent.py` (accept config; apply severity floors/caps during validation). New `tests/test_config.py`.
- **Dependencies**: `PyYAML` (add to `pyproject.toml`). It's lightweight and standard.
- **CLI**: no flag changes; `peer review` and `peer eval` auto-detect `.peer.yaml` in the cwd when invoked. `--config` flag added to all three top-level subcommands for explicit override.
- **Existing `Agent(team_conventions=)` keeps working** — it's now a single-rule equivalent of a config file with one global `path: "**"` entry. Both paths share the same prompt-injection logic.
- **Out of scope**: discovering `.peer.yaml` from a remote repo's HEAD (only local `.peer.yaml` in cwd). Plugin/hook config. Custom-tool config (linters land in `linter-context-v01`). Per-reviewer-backend config (could be added later if needed).
