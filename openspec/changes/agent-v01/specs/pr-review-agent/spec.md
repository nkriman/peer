## ADDED Requirements

### Requirement: Agent reviews a PR end-to-end
The Agent SHALL accept a GitHub PR URL and produce a structured `Review` consisting of severity-tagged inline `Comment` objects.

#### Scenario: Successful review of a small PR
- **WHEN** `Agent.review(pr_url)` is called with a valid GitHub PR URL pointing to a small PR within the context budget
- **THEN** the agent gathers the PR context, sends it to the configured LLM, parses the structured response, and returns a `Review` containing zero or more `Comment` objects

#### Scenario: PR has no issues worth flagging
- **WHEN** the LLM returns no comments for a PR
- **THEN** `Agent.review` returns a `Review` with an empty `comments` list and `reason="no issues found"`

### Requirement: Multi-LLM backend support
The Agent SHALL support multiple LLM backends via a pluggable `Reviewer` interface, with Claude and OpenAI implementations available in v0.1.

#### Scenario: Dispatch to ClaudeReviewer for Anthropic models
- **WHEN** `Agent` is instantiated with `model="claude-opus-4-7"` (or any Anthropic model identifier)
- **THEN** review calls go through a `ClaudeReviewer` using the Anthropic SDK

#### Scenario: Dispatch to OpenAIReviewer for OpenAI models
- **WHEN** `Agent` is instantiated with `model="gpt-4o"` (or any OpenAI model identifier)
- **THEN** review calls go through an `OpenAIReviewer` using the OpenAI SDK

#### Scenario: Unknown model identifier
- **WHEN** `Agent` is instantiated with a model string that matches no known backend
- **THEN** instantiation raises `UnknownModelError` with the supported backend list

### Requirement: Structured comment output via SDK features
Each `Comment` SHALL be produced via the LLM SDK's native structured-output feature (Anthropic tool-calling, OpenAI structured outputs), not via free-text parsing.

#### Scenario: Claude reviewer uses tool-calling
- **WHEN** `ClaudeReviewer.review` is called
- **THEN** it invokes the Anthropic SDK with a tool-calling spec that constrains output to the `Comment` schema

#### Scenario: OpenAI reviewer uses structured outputs
- **WHEN** `OpenAIReviewer.review` is called
- **THEN** it invokes the OpenAI SDK with a `response_format` derived from the `Comment` Pydantic model

### Requirement: Comment schema
Every `Comment` SHALL have `path` (str), optional `line` (int), `severity` ∈ `{critical, important, minor, nit}`, `body` (str), and `rationale` (str).

#### Scenario: All returned comments validate against the schema
- **WHEN** `Agent.review` returns a `Review`
- **THEN** every `Comment` in `review.comments` validates against the Pydantic `Comment` model

### Requirement: Review schema with token usage
The `Review` returned by `Agent.review` SHALL have `comments` (list[Comment]), optional `reason` (str), and `usage` (dict containing at minimum `input_tokens`, `output_tokens`, and `model`).

#### Scenario: Review carries usage info from the LLM call
- **WHEN** `Agent.review` returns a `Review`
- **THEN** `review.usage` contains `input_tokens`, `output_tokens`, and the model identifier used

#### Scenario: Review carries reason when no comments
- **WHEN** the LLM returns no comments for a PR
- **THEN** `review.comments` is empty AND `review.reason == "no issues found"`

### Requirement: Invalid LLM output is dropped with warning
If the LLM produces a `Comment` whose `path` or `line` does not exist in the PR diff, that comment SHALL be dropped from the final `Review` and a warning logged.

#### Scenario: LLM hallucinates a file path
- **WHEN** LLM output includes a `Comment` with `path="nonexistent.py"` that is not part of the PR diff
- **THEN** that `Comment` is omitted from `review.comments` and a `WARNING` is logged identifying the dropped path

#### Scenario: LLM produces a line number outside the diff
- **WHEN** LLM output includes a `Comment` with a `line` that doesn't fall within any hunk of the cited `path`
- **THEN** that `Comment` is omitted and a `WARNING` is logged

### Requirement: CLI smoke-test entry point
A `python -m peer.review <pr_url>` CLI entry SHALL be provided for ad-hoc, single-PR review runs.

#### Scenario: Successful CLI run
- **WHEN** `python -m peer.review https://github.com/owner/repo/pull/123` is executed
- **THEN** it prints a human-readable summary of the `Review` (severity counts + comment bodies grouped by severity) to stdout
