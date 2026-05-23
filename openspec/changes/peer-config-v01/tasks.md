## 1. Schema + loader

- [ ] 1.1 Add `PyYAML>=6.0` to `pyproject.toml` dependencies.
- [ ] 1.2 Create `src/peer/config.py` with Pydantic models: `PeerConfig`, `AgentConfigSection`, `Rule`, `ResolvedRule`. Strict mode: forbid unknown keys, validate severity strings.
- [ ] 1.3 Define exception `PeerConfigInvalid` in `src/peer/exceptions.py`.
- [ ] 1.4 Implement `load_config(root: Path) -> PeerConfig` and `load_config_from(path: Path) -> PeerConfig`. Use PyYAML safe loader. INFO log on successful load.

## 2. Path resolver

- [ ] 2.1 Implement `PeerConfig.for_path(file_path: str) -> ResolvedRule` using `fnmatch.fnmatch` + manual `**`-aware globbing (Python's `pathlib.Path.match` doesn't quite do `**` correctly across Python versions). Use `pathlib.PurePath.full_match` if available (Python 3.13+); fall back to a small hand-rolled matcher otherwise.
- [ ] 2.2 First-matching-glob wins; empty `ResolvedRule.empty()` returned if no rule matches.
- [ ] 2.3 Unit tests in `tests/test_config.py`: simple match, glob with `**`, multiple rules ordered, no-match returns empty, severity-only rule, conventions-only rule.

## 3. Severity floor/cap enforcement

- [ ] 3.1 Define ordinal map `_SEVERITY_ORDINAL = {"critical": 0, "important": 1, "minor": 2, "nit": 3}` (lower number = more severe).
- [ ] 3.2 Helper `apply_severity_bounds(comment: Comment, rule: ResolvedRule) -> Comment` — returns a possibly-updated copy of the comment with severity clamped to `[floor, cap]`. Logs INFO when severity changes.
- [ ] 3.3 In `Agent.review`, after `_validate_comments`, apply `apply_severity_bounds` to every surviving comment using the comment's path to look up the rule.

## 4. Agent integration

- [ ] 4.1 Update `Agent.__init__` signature: add `config: Optional[PeerConfig] = None`, `config_file: Optional[Path] = None`. Reject mutually-exclusive combinations (config + config_file + team_conventions).
- [ ] 4.2 If no config supplied, call `load_config(Path.cwd())`.
- [ ] 4.3 If `team_conventions` supplied (legacy), construct an equivalent `PeerConfig` with one catch-all rule.
- [ ] 4.4 Store on `self.config`.
- [ ] 4.5 Update `Agent.review` to assemble the union of conventions text from all rules matching at least one path in the PR diff. Inject into the system prompt with labeled sections per rule.

## 5. CLI

- [ ] 5.1 Add `--config PATH` flag to `peer review`, `peer eval`, `peer dataset add` in `src/peer/cli.py`. When specified, the loaded `PeerConfig` is passed into the constructed `Agent`.

## 6. Example + docs

- [ ] 6.1 Ship `dataset/reference/peer.yaml.example` — a worked example showing per-path rules for a hypothetical Django repo (covers tests/, docs/, security paths, catch-all). Include inline comments explaining each section.
- [ ] 6.2 Update README to mention `.peer.yaml` auto-detection + link to the example.

## 7. Tests

- [ ] 7.1 `tests/test_config.py` — schema validation (unknown keys, bad severities, empty paths), load_config (present, absent, malformed YAML).
- [ ] 7.2 `tests/test_config.py` — path resolver (simple, glob, multiple rules, no match).
- [ ] 7.3 `tests/test_config.py` — severity bounds helper (floor, cap, both, no-op).
- [ ] 7.4 `tests/test_agent.py` (new or existing) — Agent with config: severity overrides applied in review output; team_conventions shortcut produces equivalent config; explicit config arg overrides auto-detection.
- [ ] 7.5 `tests/test_cli.py` — `--config` flag plumbing for review / eval / dataset subcommands.

## 8. Re-run conventions experiment with config

- [ ] 8.1 Create `.peer.yaml.django` and `.peer.yaml.pydantic` (or a single file with multiple paths) demonstrating per-path conventions + severity caps from `dataset/reference/conventions/django.md` and `dataset/reference/conventions/pydantic.md`.
- [ ] 8.2 Re-run `scripts/eval_with_conventions.py` (or a new variant) against the v2 dataset using the config files, save to `data/eval_runs/reference_v2_sonnet46_config_v1.json`.
- [ ] 8.3 Compare against `reference_v2_sonnet46_with_conventions.json` (the global-conventions baseline) — expect severity calibration to recover (no more -0.33 under-severing) while keeping the recall lift.
