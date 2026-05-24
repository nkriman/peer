## ADDED Requirements

### Requirement: PeerConfig is the typed schema for `.peer.yaml`

The framework SHALL define a Pydantic model `PeerConfig` matching the documented schema. The model SHALL reject unknown keys, invalid severities, and empty `paths:` lists with clear error messages.

#### Scenario: Valid config parses cleanly

- **WHEN** `PeerConfig.model_validate({"version": 1, "rules": [{"paths": ["src/**"], "severity_cap": "minor"}]})` is called
- **THEN** the resulting `PeerConfig` has one rule with the matching paths + severity_cap, and no validation errors

#### Scenario: Unknown top-level key rejected

- **WHEN** the YAML contains an unknown top-level key (e.g., `enable: true`)
- **THEN** loading raises a Pydantic validation error naming the unknown key

#### Scenario: Invalid severity rejected

- **WHEN** a rule contains `severity_cap: blocker`
- **THEN** loading raises a Pydantic validation error stating the valid severities

#### Scenario: Empty paths list rejected

- **WHEN** a rule has `paths: []`
- **THEN** loading raises a validation error

### Requirement: load_config finds and loads .peer.yaml

The framework SHALL provide `peer.config.load_config(root: Path) -> PeerConfig` that looks for `.peer.yaml` in the given directory, loads + validates it, logs an INFO message identifying the loaded file, and returns the parsed config. If the file is absent, returns an empty `PeerConfig()` without logging.

#### Scenario: Config present

- **WHEN** `.peer.yaml` exists at `<root>/.peer.yaml` with valid content
- **THEN** `load_config(root)` returns the parsed `PeerConfig` and logs `INFO peer.config: loaded config from <root>/.peer.yaml`

#### Scenario: Config absent

- **WHEN** no `.peer.yaml` exists at `<root>`
- **THEN** `load_config(root)` returns `PeerConfig()` (empty) and emits no log

#### Scenario: Malformed YAML

- **WHEN** `.peer.yaml` exists but has YAML syntax errors
- **THEN** `load_config(root)` raises `PeerConfigInvalid` with the YAML parser's error message

### Requirement: PeerConfig.for_path resolves per-file rules

`PeerConfig.for_path(file_path: str) -> ResolvedRule` SHALL return the first rule in `rules` whose `paths:` globs match the file path. If no rule matches, return `ResolvedRule.empty()`. The returned `ResolvedRule` carries the merged `conventions_file`, `severity_floor`, `severity_cap` for that path.

#### Scenario: Specific path matches specific rule

- **WHEN** the config has a rule with `paths: ["tests/**"]` and a catch-all `paths: ["**"]`, and `for_path("tests/test_foo.py")` is called
- **THEN** the tests rule is returned (first-matching wins)

#### Scenario: Path matches no rule

- **WHEN** the config has only `paths: ["src/**"]` and `for_path("dist/build.py")` is called
- **THEN** an empty `ResolvedRule` is returned (no conventions, no severity overrides)

#### Scenario: Glob with `**` matches recursively

- **WHEN** `paths: ["src/**/*.py"]` and `for_path("src/peer/agent.py")` is called
- **THEN** the rule matches (recursive globbing supported)

### Requirement: Severity floors and caps applied at comment-validation time

`Agent.review` SHALL apply per-path severity floors and caps from the loaded config during comment validation. A `severity_floor` raises severity if the agent's chosen severity is less severe than the floor; a `severity_cap` lowers severity if the agent's chosen severity is more severe than the cap. Each change SHALL be logged at INFO level.

#### Scenario: Cap lowers severity

- **WHEN** the agent emits a `Comment(path="tests/test_foo.py", severity="important", ...)` and the config rule for `tests/**` has `severity_cap: minor`
- **THEN** the comment's severity in the returned `Review` is `"minor"` and an INFO log records the change

#### Scenario: Floor raises severity

- **WHEN** the agent emits a `Comment(path="src/auth/login.py", severity="minor", ...)` and the config rule for `src/auth/**` has `severity_floor: important`
- **THEN** the comment's severity is upgraded to `"important"` with an INFO log

#### Scenario: Both floor and cap allow current severity

- **WHEN** the agent emits a `Comment(severity="important")` and the rule has `severity_floor=minor` and `severity_cap=critical`
- **THEN** the severity is unchanged

### Requirement: Agent loads PeerConfig automatically + accepts explicit override

`Agent.__init__` SHALL call `load_config(Path.cwd())` by default if no `config=` or `config_file=` argument is supplied. Explicit arguments override auto-detection.

#### Scenario: Auto-load from cwd

- **WHEN** `Agent()` is constructed in a cwd containing `.peer.yaml`
- **THEN** the loaded `PeerConfig` is accessible via `agent.config` and an INFO log records the load

#### Scenario: Explicit config argument

- **WHEN** `Agent(config=PeerConfig(rules=[...]))` is called
- **THEN** `agent.config` is the explicit instance; auto-detection is skipped

#### Scenario: Explicit config_file argument

- **WHEN** `Agent(config_file=Path("custom/peer.yaml"))` is called
- **THEN** that file is loaded via `load_config_from(custom_path)`; auto-detection skipped

#### Scenario: team_conventions legacy shortcut still works

- **WHEN** `Agent(team_conventions="some text")` is called
- **THEN** the behavior is identical to a `PeerConfig` with a single rule `paths: ["**"]` whose `conventions_text` is the supplied string

### Requirement: Conventions injection uses the union of matched conventions in the PR

For a PR review, the system prompt SHALL include the union of `conventions_file` contents from all rules whose `paths:` glob matches at least one file in the PR diff. Each conventions section in the system prompt SHALL be labeled with the rule's path patterns so the agent knows which rule applies to which files.

#### Scenario: PR touches files in two different rule scopes

- **WHEN** the PR modifies `src/auth/login.py` and `tests/test_login.py`, and the config has separate rules for `src/auth/**` and `tests/**`
- **THEN** the system prompt includes both conventions files in separate labeled sections (e.g., "## CONVENTIONS for src/auth/**" and "## CONVENTIONS for tests/**")

#### Scenario: Duplicate conventions_file across rules

- **WHEN** two matched rules reference the same conventions file
- **THEN** the conventions content appears only once in the system prompt with both path patterns listed

### Requirement: PeerConfig has extra_instructions field

`PeerConfig` SHALL accept an optional top-level `agent.extra_instructions: str` field (also accessible as `cfg.agent.extra_instructions` after loading). The field is appended to the agent's system prompt as a labeled section. Smaller scope than conventions docs — for short ad-hoc guidance.

#### Scenario: extra_instructions appended to prompt

- **WHEN** `.peer.yaml` contains `agent:\n  extra_instructions: "Focus on security."` and an Agent loads this config
- **THEN** the agent's effective system prompt contains the literal string "Focus on security." in a labeled section

#### Scenario: extra_instructions stacks with conventions

- **WHEN** the config also has per-path conventions for `src/auth/**`
- **THEN** both are included (extra_instructions first as a global note; conventions per-path as their own sections)

### Requirement: ignore section excludes files before context extraction

`PeerConfig` SHALL accept an `ignore:` top-level section with three subfields: `glob: list[str]`, `regex: list[str]`, `generated_code: list[str]` (the latter pre-populated with vendored PR-Agent patterns when no user override is provided). Files matching ANY pattern in any subfield SHALL be excluded from `Context.hunks` BEFORE codebase-context extraction.

#### Scenario: glob exclusion

- **WHEN** `.peer.yaml` has `ignore:\n  glob: ["vendor/**", "build/**"]` and a PR includes a hunk in `vendor/lib.py`
- **THEN** the hunk is filtered out of `Context.hunks` and never reaches the agent or the codebase context extractor; INFO log records the skip

#### Scenario: regex exclusion

- **WHEN** `ignore.regex: [".*\\.min\\.js$"]` and a PR includes a hunk in `static/app.min.js`
- **THEN** the hunk is filtered out

#### Scenario: Default generated_code patterns

- **WHEN** no `ignore.generated_code` is configured and a PR includes a hunk in `proto/foo_pb2.py`
- **THEN** the hunk is filtered out (default patterns include `**/*_pb2.py`)

#### Scenario: Custom generated_code overrides default

- **WHEN** the user explicitly sets `ignore.generated_code: []` (empty list) and a PR includes a hunk in `proto/foo_pb2.py`
- **THEN** the hunk is NOT filtered (user opted out of the default)

### Requirement: PeerConfig integrates with PeerDeps

`PeerConfig` SHALL be set on `PeerDeps.config` (per `peer-deps-v01`) rather than directly on `Agent`. The legacy `Agent(config=...)` and `Agent(config_file=...)` kwargs SHALL continue to work via a `DeprecationWarning` shim that folds the value into `self._default_deps.config`.

#### Scenario: Config passed via PeerDeps

- **WHEN** `Agent(model="anthropic:claude-sonnet-4-6", deps_type=PeerDeps).run(pr_url, deps=PeerDeps(config=cfg))` is called
- **THEN** the agent uses `cfg` for per-path conventions, severity bounds, and ignore filtering

#### Scenario: Legacy config kwarg with deprecation warning

- **WHEN** `Agent(model="...", config=cfg)` is constructed
- **THEN** a `DeprecationWarning` is emitted naming the `deps=PeerDeps(config=cfg)` pattern; the cfg is wrapped into `_default_deps.config` so existing `Agent.review(pr_url)` works

### Requirement: CLI commands accept --config override

`peer review`, `peer eval`, and `peer dataset add` SHALL accept a `--config PATH` flag that overrides auto-detection of `.peer.yaml`.

#### Scenario: Explicit --config flag

- **WHEN** `peer review --config ./team_peer.yaml https://github.com/...` is invoked
- **THEN** the Agent uses the supplied config file; cwd auto-detection is skipped
