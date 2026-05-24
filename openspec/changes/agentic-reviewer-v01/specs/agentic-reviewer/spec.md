## ADDED Requirements

### Requirement: AgenticReviewer routes through the CLI with tools enabled

The framework SHALL define `peer.strategies.AgenticReviewer` as a Reviewer-Protocol-shaped class. It SHALL accept these constructor arguments:

- `model: str = "claude-code:sonnet"` — display name for the model
- `model_id: str = "sonnet"` — the CLI's `--model` value
- `system_prompt: str = DEFAULT_SYSTEM_PROMPT` — agent's system prompt
- `allowed_tools: list[str]` — defaults to `["Read", "Grep", "Glob"]`
- `max_turns: int = 15` — hard cap on the agent's iterative tool loop
- `claude_bin: str = "claude"` — path to the `claude` CLI
- `timeout_seconds: float = 1800.0` — wall-clock cap per `.review()` call (agentic loops are slow)

The `.review(context, codebase_context=None, *, extra_user_message=None, run_context=None) -> tuple[list[Comment], dict]` method SHALL:

1. Honor `peer.deps.ALLOW_LLM_CALLS` — raise `LLMCallsDisabled` when False (same as other Reviewers).
2. Build the user prompt via `format_prompt(context, codebase_context) + _CLI_INSTRUCTIONS_SUFFIX`. Append `extra_user_message` if provided.
3. Construct argv: `claude --print --output-format json --model <model_id> --system-prompt <text> --disable-slash-commands --allowedTools=<comma-list> --max-turns <N>` followed by the prompt as the positional arg.
4. NOT pass `--disallowedTools` — the whole point is to enable the listed tools.
5. Run the subprocess with `check=False`; on non-zero exit, log WARNING and return empty comments list.
6. Parse the envelope: prefer `envelope["structured_output"]` if it contains `"comments"`; otherwise fall back to `_extract_comments_payload(envelope["result"] or "")`.
7. Return the parsed Comments + usage dict (input_tokens summed across cache_read/cache_creation/real input, output_tokens, model name, total_cost_usd).

#### Scenario: argv contains --allowedTools and --max-turns

- **GIVEN** a fake claude binary that records argv
- **WHEN** `AgenticReviewer(allowed_tools=["Read","Grep"], max_turns=8).review(ctx)` is called
- **THEN** the recorded argv contains `--allowedTools=Read,Grep`
- **AND** the recorded argv contains `--max-turns`
- **AND** the recorded argv contains `8`
- **AND** the recorded argv does NOT contain `--disallowedTools`

#### Scenario: structured_output parses to Comments

- **GIVEN** a fake claude binary returning envelope with `structured_output={"comments":[{path:"src/foo.py",line:10,severity:"minor",body:"b",rationale:"r"}]}`
- **WHEN** AgenticReviewer.review is called
- **THEN** the returned Comments list has length 1
- **AND** the first comment's path is `"src/foo.py"`

#### Scenario: prose fallback parses JSON when structured_output is missing

- **GIVEN** a fake claude binary returning envelope with empty `structured_output` but `result` containing fenced ```json block with one comment
- **WHEN** AgenticReviewer.review is called
- **THEN** the returned Comments list has length 1

#### Scenario: ALLOW_LLM_CALLS=False blocks the call

- **GIVEN** `peer.deps.ALLOW_LLM_CALLS = False`
- **WHEN** AgenticReviewer.review is called
- **THEN** `LLMCallsDisabled` is raised

### Requirement: AgenticReviewer is registered under the short name "agentic"

The `peer.strategies` module SHALL register `AgenticReviewer` under the short name `"agentic"` at import time. `resolve_strategy("agentic")` SHALL return the `AgenticReviewer` class. Recipe wiring via `reviewer_dotted_path: "agentic"` SHALL produce an `AgenticReviewer` instance when the recipe is applied.

#### Scenario: registry resolves "agentic" to AgenticReviewer

- **WHEN** `resolve_strategy("agentic")` is called
- **THEN** the returned class is `AgenticReviewer`

#### Scenario: Recipe with reviewer_dotted_path "agentic" yields an AgenticReviewer

- **GIVEN** `Recipe(reviewer_dotted_path="agentic", reviewer_kwargs={"max_turns": 5})`
- **WHEN** the recipe is applied to a fresh Agent
- **THEN** `agent.reviewer` is an instance of `AgenticReviewer`
- **AND** the reviewer's `max_turns` equals 5
