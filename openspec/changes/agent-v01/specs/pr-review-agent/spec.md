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

### Requirement: Agent assembles PR + codebase context for the LLM
The Agent SHALL request the PR `Context` (`pr-context` capability) and the `CodebaseContext` (`codebase-context` capability) for every review, and SHALL include both in the LLM prompt structured so the LLM can distinguish them (e.g., labeled sections).

#### Scenario: Both contexts flow to the LLM
- **WHEN** `Agent.review(pr_url)` is called
- **THEN** the underlying LLM prompt contains a labeled section for the diff + PR description + prior discussion (from `Context`) AND a labeled section for modified symbols + call sites + related tests + untested files signal (from `CodebaseContext`)

#### Scenario: CodebaseContext extraction fails entirely
- **WHEN** codebase-context gathering raises (e.g., tree-sitter grammar unavailable)
- **THEN** the agent still proceeds with PR context only and logs a `WARNING` that codebase context was unavailable for this review

### Requirement: Default system prompt explicitly directs use of codebase context
The default system prompt (shipped in `src/peer/prompts.py`) SHALL explicitly instruct the LLM to consult `modified_symbols`, `call_sites`, `related_tests`, and `untested_files` when formulating each review comment. This requirement is informed by CodeCompass (arXiv 2602.20048, Feb 2026): without explicit prompt instruction to use structural context, agents ignored it in 58% of trials.

#### Scenario: Default prompt names the codebase-context sections
- **WHEN** an `Agent` is instantiated with no `system_prompt` override
- **THEN** the loaded default prompt text contains explicit references to `modified_symbols`, `call_sites`, `related_tests`, and `untested_files` and directs the model to consult them when relevant

#### Scenario: Custom prompt is preserved verbatim
- **WHEN** an `Agent` is instantiated with a `system_prompt=` override (str or `system_prompt_file=` path)
- **THEN** the custom prompt is used unmodified — it is the user's responsibility to direct context use; the framework does not splice or augment the override

#### Scenario: Prompt loadable from file
- **WHEN** an `Agent` is instantiated with `system_prompt_file=Path("./my_prompt.md")`
- **THEN** the file contents are loaded as the system prompt; missing file raises a clear error

### Requirement: Comments may reference cited codebase context (best-effort traceability)
Each `Comment` MAY include a `references` field listing the codebase-context items (symbol names, call-site paths, test file paths) the agent consulted for that comment. The framework SHALL accept this field if the LLM produces it but SHALL NOT require it (LLMs do not reliably populate this kind of traceability field).

#### Scenario: LLM populates references
- **WHEN** the LLM produces a `Comment` about a behavior change that affects callers and includes `references=["foo", "src/bar.py:42"]`
- **THEN** the `Comment` round-trips with `references` populated, useful for eval debugging

#### Scenario: LLM omits references
- **WHEN** the LLM omits the `references` field
- **THEN** the `Comment` is accepted with `references=None`; no error, no warning

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
