## ADDED Requirements

### Requirement: Recipe is a single Pydantic model covering the reviewer mutation surface

The framework SHALL define `peer.recipe.Recipe` as a Pydantic v2 model with `ConfigDict(extra="forbid")` and the following fields, each with a default that reproduces today's `Agent()` behavior:

- `model: str = "anthropic:claude-sonnet-4-6"`
- `temperature: float = 0.0`
- `max_tokens: int = 8192`
- `system_prompt_path: Path = Path("prompts/default_system_prompt.md")`
- `team_conventions_path: Path | None = None`
- `retries: dict[str, int] = {"output": 1}`
- `codebase_context_max_tokens: int = 30000`
- `codebase_context_max_call_sites_per_symbol: int = 5`
- `codebase_context_max_test_file_chars: int = 5000`
- `post_processing_max_comments_per_pr: int | None = None`
- `post_processing_severity_floor: Literal["critical","important","minor","nit"] | None = None`
- `post_processing_drop_paths: list[str] = []`

Additional fields MAY land in future autoresearch changes; new fields MUST have defaults that preserve today's behavior. The model SHALL provide `to_yaml() -> str` and `Recipe.from_yaml(text: str) -> Recipe` for round-tripping `recipe.yaml`.

#### Scenario: Default Recipe construction matches today's Agent

- **WHEN** `Recipe()` is constructed with no arguments
- **THEN** all fields take their defaults, and applying the recipe to `Agent()` produces a reviewer indistinguishable from `Agent(model="anthropic:claude-sonnet-4-6")` (same model, same system prompt, same retries)

#### Scenario: Recipe round-trips through YAML

- **WHEN** a populated `Recipe` is dumped via `to_yaml()` and then re-parsed via `Recipe.from_yaml(...)`
- **THEN** the resulting Recipe is field-by-field equal to the original

#### Scenario: Recipe rejects unknown fields

- **WHEN** YAML contains a top-level field not declared on `Recipe` (e.g. `unknown_field: 42`)
- **THEN** `Recipe.from_yaml(...)` raises a Pydantic `ValidationError`

### Requirement: Recipe applies cleanly to an Agent

The framework SHALL define `recipe.apply_to_agent(agent: Agent) -> Agent` that mutates the agent in place: sets `agent.system_prompt` (loaded from `system_prompt_path`), `agent.retries`, and rebuilds `agent.reviewer` with the recipe's model + temperature + max_tokens. After application, calling `agent.run(...)` SHALL use the recipe's settings end-to-end.

The framework SHALL also support `Agent(recipe=Recipe(...))` as a one-step constructor.

#### Scenario: Recipe wins over explicit Agent kwargs on conflict

- **GIVEN** `Agent(model="anthropic:claude-opus-4-7", recipe=Recipe(model="anthropic:claude-sonnet-4-6"))`
- **WHEN** the agent is constructed
- **THEN** `agent.model` equals `"anthropic:claude-sonnet-4-6"` (recipe wins)

### Requirement: The default system prompt lives in a file under prompts/

The framework SHALL maintain the canonical text of `DEFAULT_SYSTEM_PROMPT` at `prompts/default_system_prompt.md` (project-root-relative). The `peer.prompts` module SHALL load this file at import time and expose its content as `DEFAULT_SYSTEM_PROMPT: str`. The file SHALL be the single source of truth — editing it changes peer's default reviewer behavior on next import.

#### Scenario: editing the prompt file changes DEFAULT_SYSTEM_PROMPT

- **GIVEN** an edit to `prompts/default_system_prompt.md` adding a line "EXTRA"
- **WHEN** Python re-imports `peer.prompts`
- **THEN** `peer.prompts.DEFAULT_SYSTEM_PROMPT` contains "EXTRA"

#### Scenario: missing prompt file raises a clear error at import

- **WHEN** `prompts/default_system_prompt.md` does not exist at import time
- **THEN** importing `peer.prompts` raises `FileNotFoundError` with a message pointing at the expected path

### Requirement: ClaudeReviewer honors a temperature setting

The `ClaudeReviewer` SHALL accept a `temperature: float = 0.0` constructor argument and pass it through to `client.messages.create(temperature=...)`. The default of `0.0` SHALL apply when neither the Recipe nor explicit Agent kwargs set it. This eliminates the stochastic-noise floor that drowns out small recipe deltas in autoresearch evaluation.

#### Scenario: default temperature is 0.0

- **GIVEN** `ClaudeReviewer(model="anthropic:claude-sonnet-4-6")` constructed with no temperature
- **WHEN** review is invoked and the SDK call is inspected
- **THEN** the kwargs passed to `client.messages.create` include `temperature=0.0`

### Requirement: `peer autoresearch run` invokes one eval iteration and appends a leaderboard row

The CLI SHALL expose `peer autoresearch run --recipe <path> [--dataset <path>] [--leaderboard <path>] [--description STR]`. The command SHALL: load the Recipe, construct an Agent from it, run an EvalRunner on the dataset (default `dataset/reference/django_pydantic_v2_hard.jsonl`), and atomically append a tab-separated row to the leaderboard file (default `data/eval_runs/leaderboard.tsv`) with columns:

`commit_sha\trecipe_hash\tutility\tdetection_rate\tprecision_minor\tprecision_important\tprecision_critical\tcost_usd\tn_comments_total\tstatus\tdescription`

`commit_sha` SHALL be the current `HEAD` short hash. `recipe_hash` SHALL be the first 8 hex chars of SHA-256 over the recipe's canonical YAML. `utility` SHALL be computed from the scalar utility formula in `program.md` (parsed at run-time; if `program.md` is missing or unparseable, defaults to `detection_rate`). `status` SHALL be `"ok"` on a successful run, `"crash"` when the EvalRunner raised.

#### Scenario: `peer autoresearch run` writes one leaderboard row per invocation

- **GIVEN** a Recipe at `tmp/recipe.yaml` and a small dataset at `tmp/ds.jsonl`
- **WHEN** I invoke `peer autoresearch run --recipe tmp/recipe.yaml --dataset tmp/ds.jsonl --leaderboard tmp/board.tsv --description "baseline"`
- **THEN** the command exits 0
- **AND** `tmp/board.tsv` exists and ends with one new row whose `status` column is `"ok"` and whose `description` column is `"baseline"`

#### Scenario: `peer autoresearch run` records a crash without raising

- **GIVEN** a Recipe with `model="nonsense:nothing"` (will fail at Agent construction)
- **WHEN** I invoke `peer autoresearch run --recipe ... --leaderboard tmp/board.tsv`
- **THEN** the command exits non-zero
- **AND** the leaderboard's last row has `status="crash"` (the row is still appended for forensic visibility)

### Requirement: `peer autoresearch loop` is the autonomous mode

The CLI SHALL expose `peer autoresearch loop --recipe <path> [--dataset <path>] [--max-iters N] [--budget-usd X] [--mutator <dotted-path>]`. The loop SHALL:

1. Read the current Recipe (baseline).
2. Run one iteration against the dataset, score it via the utility formula, record baseline in the TSV.
3. LOOP: call the mutator hook (default: no-op — the user-driven agent is expected to mutate `recipe.yaml` + the linked prompt file outside the loop process between iterations); run one iteration; if `utility_new > utility_best`, `git commit` the recipe + prompt files and update `utility_best`; otherwise `git reset --hard` the working tree to drop the failed mutation.
4. Halt when `--max-iters` or `--budget-usd` is exceeded.

The loop SHALL log each iteration to the same TSV. On every keep-decision the loop SHALL `git commit` with a message including the new utility and a one-line description from the mutator's stdout (or `"autoresearch iter <n>"` as fallback).

#### Scenario: loop terminates at max-iters

- **GIVEN** `peer autoresearch loop --max-iters 3` with a no-op mutator
- **WHEN** the loop runs
- **THEN** exactly 4 TSV rows are appended (1 baseline + 3 iterations) and the loop exits 0

#### Scenario: loop terminates at budget-usd

- **GIVEN** `peer autoresearch loop --budget-usd 0.01` (effectively zero) with a no-op mutator and a fake-cost reviewer that reports cost=0.005 per iter
- **WHEN** the loop runs
- **THEN** the loop exits after at most 3 iterations (baseline + 2 = 0.015 > 0.01) and prints a "budget exceeded" message

#### Scenario: regression triggers git reset

- **GIVEN** an initial Recipe (baseline utility = 0.06) and a mutator that mutates the recipe to drop detection_rate to 0.02
- **WHEN** the loop runs one mutating iteration
- **THEN** the working tree is reset (`git status --porcelain` is empty after the iteration)
- **AND** the TSV row's `status` is `"discard"`

### Requirement: program.md exists at the repo root and encodes the keep rule

The repository SHALL contain `program.md` at its root, defining: (1) the branch convention (`autoresearch/<tag>`), (2) the set of files under mutation (`recipe.yaml` + whichever prompt file the recipe points at), (3) the eval command, (4) the keep/discard rule + scalar utility formula, (5) the leaderboard schema, (6) "never stop" loop semantics for the agent running it. The loop SHALL parse the utility formula from a fenced ```python``` block under a `## Utility` section.

#### Scenario: loop reads the utility formula from program.md

- **GIVEN** a `program.md` with a `## Utility` section containing the formula `score = detection_rate`
- **WHEN** the loop runs one iteration with detection_rate=0.05
- **THEN** the TSV row's `utility` column equals `0.05`

#### Scenario: missing program.md falls back to detection_rate as the utility

- **GIVEN** no `program.md` at the repo root
- **WHEN** the loop runs one iteration with detection_rate=0.04
- **THEN** the TSV row's `utility` column equals `0.04`
