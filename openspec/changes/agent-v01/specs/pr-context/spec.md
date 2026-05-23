## ADDED Requirements

### Requirement: Gather PR context from URL
The `context` module SHALL fetch the diff, PR description, and prior discussion comments for any public GitHub PR URL.

#### Scenario: Gather context for a valid public PR
- **WHEN** `gather(pr_url)` is called with a valid GitHub PR URL
- **THEN** it returns a `Context` containing the unified diff, surrounding code snippets per hunk, PR description, and any prior issue/review comments

#### Scenario: Invalid PR URL
- **WHEN** `gather` is called with a string that doesn't parse as a GitHub PR URL
- **THEN** it raises `InvalidPRURL` with a clear message naming the expected format

#### Scenario: PR does not exist or is inaccessible
- **WHEN** `gather` is called with a URL pointing to a PR that returns 404 or 403 via `gh`
- **THEN** it raises `PRNotAccessible` with the underlying status code surfaced

### Requirement: Include surrounding code context per hunk
Each diff hunk in the `Context` SHALL include the surrounding ±N lines of the file's current state, where N defaults to 20 and is configurable.

#### Scenario: Default window is included
- **WHEN** a PR modifies lines 50–55 of `file.py` with default window
- **THEN** the `Context` for that hunk includes the file content from roughly line 30 through line 75

#### Scenario: Custom window override
- **WHEN** `gather(pr_url, context_lines=50)` is called
- **THEN** each hunk's surrounding context spans ±50 lines

### Requirement: Use the `gh` CLI for GitHub access
Context gathering SHALL use the `gh` CLI under the hood for GitHub API access, mirroring `curate.py`, so no separate token plumbing is required in development.

#### Scenario: `gh` CLI is not installed
- **WHEN** `gather` is called and `gh` is not on PATH
- **THEN** it raises `GHCLINotAvailable` with installation instructions

#### Scenario: `gh` CLI is not authenticated
- **WHEN** `gh` returns an authentication error on first call
- **THEN** `gather` raises `GHCLINotAuthenticated` and instructs the user to run `gh auth login`

### Requirement: Reject PRs that exceed the context budget
If a PR's gathered context (diff + surrounding code + description + comments) exceeds the configured token budget, `gather` SHALL raise a clear error rather than truncating silently.

#### Scenario: PR exceeds the configured token budget
- **WHEN** the assembled `Context` for a PR exceeds the configured `max_tokens` (default `100_000`)
- **THEN** `gather` raises `ContextTooLarge` with the measured size and the configured limit, and recommends waiting for v0.2's chunking support
