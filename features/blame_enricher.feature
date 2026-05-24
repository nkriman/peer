# blame-enricher-v01 (peer-vh8):
#   - gather_git_history pure function
#   - CodebaseContext.git_history field
#   - gather_codebase_context include_git_history kwarg
#   - format_prompt renders the GIT HISTORY section
#   - Recipe.include_git_history toggles it

Feature: blame enricher — git history as a context section

  @fast
  Scenario: gather_git_history formats recent commits + blame for one path
    Given a fake git that returns 3 commit lines and 2 blame lines for "src/foo.py"
    When I call gather_git_history with one hunk on "src/foo.py" line 10 length 2
    Then the returned string contains "Recent commits to src/foo.py:"
    And the returned string contains "@@ -10,+2 @@ in src/foo.py:"
    And the returned string contains the literal blame author names

  @fast
  Scenario: gather_git_history returns empty string for empty hunks
    When I call gather_git_history with an empty hunks list
    Then the returned string is the empty string

  @fast
  Scenario: gather_git_history degrades on git failure
    Given a fake git that returns exit code 128 for every call
    When I call gather_git_history with one hunk on "src/foo.py" line 10 length 2
    Then no exception is raised
    And the returned string is the empty string

  @fast
  Scenario: default CodebaseContext has empty git_history
    When I construct a default CodebaseContext
    Then the CodebaseContext's git_history equals the empty string

  @fast
  Scenario: gather_codebase_context populates git_history when include_git_history is True
    Given a fake gather_git_history returning "fake blame content"
    When I call gather_codebase_context with include_git_history True
    Then the returned CodebaseContext's git_history equals "fake blame content"

  @fast
  Scenario: gather_codebase_context leaves git_history empty when include_git_history is False
    When I call gather_codebase_context with include_git_history False
    Then the returned CodebaseContext's git_history equals the empty string

  @fast
  Scenario: format_prompt renders GIT HISTORY section when populated
    Given a Context with one hunk and a CodebaseContext with git_history "fake blame content"
    When I call format_prompt with both
    Then the rendered prompt contains "## GIT HISTORY"
    And the rendered prompt contains "fake blame content"

  @fast
  Scenario: format_prompt omits GIT HISTORY section when git_history is empty
    Given a Context with one hunk and a CodebaseContext with empty git_history
    When I call format_prompt with both
    Then the rendered prompt does NOT contain "## GIT HISTORY"

  @fast
  Scenario: Recipe defaults preserve back-compat
    When I construct a Recipe with no arguments
    Then the Recipe's include_git_history equals False
