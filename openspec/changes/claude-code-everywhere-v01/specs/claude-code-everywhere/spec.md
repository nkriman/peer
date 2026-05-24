## ADDED Requirements

### Requirement: ClaudeCodeShimClient exposes an SDK-shaped `.messages.create(...)` surface

The framework SHALL define `peer.claude_code_client.ClaudeCodeShimClient`. The class SHALL expose a `messages` attribute whose `.create(**kwargs)` method accepts at minimum these keyword arguments: `model`, `messages` (list of `{"role", "content"}` dicts), `max_tokens`, `system` (optional), `temperature` (optional), `tools` (optional), `tool_choice` (optional). It SHALL return an object whose attributes match the relevant subset of Anthropic's `Message` shape: `.content` (list of content blocks with `.type` and either `.text` or `.input`+`.name` attributes) and `.usage` (with `.input_tokens` and `.output_tokens` int attributes).

The implementation SHALL build an argv invoking `claude --print --output-format json --model <id> --system-prompt <system> --disable-slash-commands --disallowedTools Bash Edit Write Read Grep Glob WebFetch WebSearch`, with the user's `messages` flattened into a single prompt string. The CLI's `result` field is parsed into either:

- a `text`-type ContentBlock (default), or
- a `tool_use`-type ContentBlock — synthesized when the caller passed `tools=[...]` — by extracting JSON matching the tool's `input_schema` via the same robust parser used in `ClaudeCodeCLIReviewer`.

`.usage.input_tokens` SHALL be sourced from the CLI envelope's `usage.input_tokens` plus `cache_read_input_tokens` plus `cache_creation_input_tokens` (so cost-attribution code that reads `.usage.input_tokens` sees a representative number, not just the small uncached delta).

#### Scenario: shim returns a text content block when no tools are passed

- **GIVEN** the `claude` binary is stubbed to return `{"result": "hello world", "usage": {"input_tokens": 5, "output_tokens": 2}}`
- **WHEN** `ClaudeCodeShimClient().messages.create(model="sonnet", messages=[{"role": "user", "content": "hi"}], max_tokens=50)` is called
- **THEN** the returned response's `.content[0].type` equals `"text"`
- **AND** `.content[0].text` equals `"hello world"`
- **AND** `.usage.input_tokens` equals 5
- **AND** `.usage.output_tokens` equals 2

#### Scenario: shim synthesizes a tool_use content block when tools are passed

- **GIVEN** the `claude` binary is stubbed to return JSON `{"comments": [{"path": "src/foo.py", "line": 10, "severity": "minor", "body": "b", "rationale": "r"}]}` wrapped in prose
- **WHEN** `ClaudeCodeShimClient().messages.create(model="sonnet", messages=[...], max_tokens=8192, tools=[<peer's _COMMENT_TOOL>], tool_choice={"type": "tool", "name": "post_review_comments"})` is called
- **THEN** the returned response has at least one content block with `.type == "tool_use"`
- **AND** that block's `.name` equals `"post_review_comments"`
- **AND** `.input["comments"][0]["path"]` equals `"src/foo.py"`

#### Scenario: shim builds the expected argv

- **GIVEN** the `claude` binary is stubbed to return a minimal valid envelope
- **WHEN** `ClaudeCodeShimClient().messages.create(model="sonnet", system="be brief", messages=[{"role": "user", "content": "hi"}], max_tokens=10)` is called
- **THEN** the recorded argv contains `"--print"`, `"--output-format"`, `"json"`, `"--model"`, `"sonnet"`, `"--system-prompt"`, `"be brief"`, `"--disable-slash-commands"`

### Requirement: make_client factory picks the shim based on env or override

The framework SHALL define `peer.claude_code_client.make_client(*, use_claude_code: bool | None = None) -> object`. The function SHALL return an `anthropic.Anthropic()` instance OR a `ClaudeCodeShimClient()` instance based on:

1. If `use_claude_code` is `True`, return the shim.
2. If `use_claude_code` is `False`, return the SDK client.
3. If `use_claude_code` is `None`, consult the `PEER_USE_CLAUDE_CODE` env var: `"1"` / `"true"` / `"yes"` (case-insensitive) → shim; anything else → SDK.

#### Scenario: env var "1" routes to the shim

- **GIVEN** `os.environ["PEER_USE_CLAUDE_CODE"] = "1"`
- **WHEN** `make_client()` is called
- **THEN** the returned object is a `ClaudeCodeShimClient` instance

#### Scenario: explicit False overrides the env var

- **GIVEN** `os.environ["PEER_USE_CLAUDE_CODE"] = "1"`
- **WHEN** `make_client(use_claude_code=False)` is called
- **THEN** the returned object is NOT a `ClaudeCodeShimClient` (it is an `anthropic.Anthropic` or compatible)

#### Scenario: env var unset and no override returns the SDK client

- **GIVEN** `PEER_USE_CLAUDE_CODE` is unset
- **WHEN** `make_client()` is called
- **THEN** the returned object is NOT a `ClaudeCodeShimClient`

### Requirement: ClaudeReviewer constructs its client via make_client

The framework SHALL update `peer.reviewers.ClaudeReviewer.__init__` to construct its `self.client` via `peer.claude_code_client.make_client()` instead of `anthropic.Anthropic()` directly. The reviewer SHALL otherwise behave identically — same `_call_with_backoff`, same retry logic, same response parsing.

#### Scenario: ClaudeReviewer routes through the shim when env var is set

- **GIVEN** `os.environ["PEER_USE_CLAUDE_CODE"] = "1"`
- **WHEN** `ClaudeReviewer(model="anthropic:claude-sonnet-4-6")` is constructed
- **THEN** `reviewer.client` is a `ClaudeCodeShimClient` instance

### Requirement: EvalRunner constructs its judge client via make_client

The framework SHALL update `peer.eval.runner.EvalRunner._get_client` to construct its lazy client via `make_client()`. All judges that receive `client=runner._get_client()` SHALL transparently route through the shim when enabled.

#### Scenario: EvalRunner._get_client honors the env var

- **GIVEN** `os.environ["PEER_USE_CLAUDE_CODE"] = "1"`
- **WHEN** `EvalRunner(reviewer=TestReviewer(), dataset=[]).run()` invokes `_get_client()`
- **THEN** the returned client is a `ClaudeCodeShimClient` instance

### Requirement: Recipe.use_claude_code flips the switch for that run

The `Recipe` Pydantic model SHALL gain `use_claude_code: bool = False`. When true, the recipe's `apply_to_agent` SHALL set `os.environ["PEER_USE_CLAUDE_CODE"] = "1"` for the duration of the run AND construct a `ClaudeCodeCLIReviewer` instance (instead of the default `ClaudeReviewer`-via-shim). When false, behavior is unchanged.

#### Scenario: Recipe.use_claude_code=True yields a CLI-routed agent

- **GIVEN** `Recipe(use_claude_code=True)`
- **WHEN** the recipe is applied to a fresh Agent
- **THEN** `agent.reviewer` is a `ClaudeCodeCLIReviewer` instance
- **AND** `os.environ.get("PEER_USE_CLAUDE_CODE")` equals `"1"`

### Requirement: peer eval / autoresearch run / benchmark run gain --use-claude-code flags

The CLI SHALL expose `--use-claude-code` (store_true) on each of:

- `peer eval`
- `peer autoresearch run`
- `peer autoresearch loop`
- `peer benchmark run`

When set, the command SHALL set `os.environ["PEER_USE_CLAUDE_CODE"] = "1"` before constructing any client.

#### Scenario: `peer eval --use-claude-code` sets the env var

- **WHEN** `peer eval --dataset x.jsonl --use-claude-code` is parsed and dispatched (with the runner stubbed before client construction)
- **THEN** `os.environ.get("PEER_USE_CLAUDE_CODE")` equals `"1"` at the point of client construction
