@fast
Feature: GitHubAppReviewer adapter (benchmark-the-field Phase 0, peer-ya3)
  To put commercial AI reviewers (CodeRabbit, Greptile, Qodo) on the same
  leaderboard as peer, we score the inline review comments they ALREADY
  posted on a PR. The adapter reads those comments via the GitHub API and
  returns a peer Review, so it flows through the same EvalRunner + scoring
  (DetectionRate / SignalToNoiseRatio) as peer itself.

  Scenario: maps a bot's inline review comments to peer Comments
    Given a PR whose inline comments are:
      | author            | path        | line | body                  |
      | coderabbitai[bot] | src/a.py    | 10   | Possible null deref   |
      | coderabbitai[bot] | src/b.py    | 22   | Unhandled error path  |
      | human-dev         | src/a.py    | 10   | nit: rename this      |
    When I run GitHubAppReviewer for bot "coderabbitai[bot]" on the PR
    Then the external Review has 2 comments
    And the external Review comment for "src/a.py" is on line 10

  Scenario: returns an empty Review when the bot posted nothing
    Given a PR whose inline comments are:
      | author    | path     | line | body            |
      | human-dev | src/a.py | 5    | looks good to me |
    When I run GitHubAppReviewer for bot "greptileai[bot]" on the PR
    Then the external Review has 0 comments

  Scenario: comments without a file path are skipped (not anchorable to code)
    Given a PR whose inline comments are:
      | author            | path     | line | body              |
      | coderabbitai[bot] |          |      | PR-level summary  |
      | coderabbitai[bot] | src/a.py | 14   | real line comment |
    When I run GitHubAppReviewer for bot "coderabbitai[bot]" on the PR
    Then the external Review has 1 comments

  Scenario: persistent gh failure raises (fail-loud, never a fake zero-comment success)
    Given the gh CLI always fails
    When I run GitHubAppReviewer for bot "coderabbitai[bot]" on the PR with max_attempts 2
    Then an ExternalReviewerError is raised
