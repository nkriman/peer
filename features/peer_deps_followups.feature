# peer-deps-v01 follow-ups (peer-0um):
#  - Validation retries: dropped comments fed back to the Reviewer and re-tried.
#  - capture_run_messages(): async-safe per-run prompt + response capture.
#  - ReviewerRateLimited: typed 429 + exponential backoff in ClaudeReviewer.

Feature: peer-deps v01 follow-ups — validation retries, message capture, 429 backoff

  @fast
  Scenario: Validation retries — Reviewer is re-invoked when validation drops all comments
    Given an Agent with retries set to one
    And a scripted Reviewer that returns a bad-path Comment on attempt 0 and a valid Comment on attempt 1
    When I call Agent.run on a synthetic PR with one hunk on "src/foo.py"
    Then the returned Review has 1 comment
    And the Review's usage records n_retries_used equal to 1
    And the scripted Reviewer was invoked exactly 2 times

  @fast
  Scenario: Validation retries — exhausted budget logs and returns what was salvaged
    Given an Agent with retries set to zero
    And a scripted Reviewer that always returns a bad-path Comment
    When I call Agent.run on a synthetic PR with one hunk on "src/foo.py"
    Then the returned Review has 0 comments
    And the Review's usage records n_retries_used equal to 0
    And the scripted Reviewer was invoked exactly 1 time

  @fast
  Scenario: Validation retries — Reviewer sees attempt bump via RunContext
    Given an Agent with retries set to one
    And a scripted Reviewer that records each ctx.attempt it was passed
    When I call Agent.run on a synthetic PR with one hunk on "src/foo.py"
    Then the scripted Reviewer recorded attempts "0,1"

  @fast
  Scenario: capture_run_messages records the system + user prompts and the raw response
    Given an Agent with a TestReviewer that returns one fixed Comment on "src/foo.py"
    When I call Agent.run inside a capture_run_messages block on a synthetic PR with one hunk on "src/foo.py"
    Then the captured messages list has length 1
    And the first captured message's system_prompt is non-empty
    And the first captured message's user_prompt contains "src/foo.py"
    And the first captured message's raw_response is a dict
    And the first captured message's usage has model "test"

  @fast
  Scenario: capture_run_messages is async-safe — concurrent runs don't leak into each other's buffers
    Given two independent capture_run_messages buffers in two separate asyncio tasks
    When each task calls Agent.run once with a distinct PR url
    Then each buffer contains exactly 1 captured message
    And each buffer's captured PR url matches the task that opened it

  @fast
  Scenario: capture_run_messages outside any block is a no-op
    Given an Agent with a TestReviewer that returns one fixed Comment on "src/foo.py"
    When I call Agent.run on a synthetic PR with one hunk on "src/foo.py" with no active capture block
    Then no captured-messages list is populated

  @fast
  Scenario: ReviewerRateLimited is raised on HTTP 429 after backoff exhausts
    Given a ClaudeReviewer whose underlying client always raises a 429
    And the Reviewer's rate_limit_max_retries is set to 2
    When the Reviewer is invoked
    Then ReviewerRateLimited is raised
    And the underlying client was called exactly 3 times
    And the cumulative sleep time was approximately 3 ticks of base backoff

  @fast
  Scenario: ReviewerRateLimited recovers when the 429 resolves before the budget is exhausted
    Given a ClaudeReviewer whose underlying client raises a 429 on call 0 and succeeds on call 1
    And the Reviewer's rate_limit_max_retries is set to 3
    When the Reviewer is invoked
    Then no exception is raised
    And the underlying client was called exactly 2 times
