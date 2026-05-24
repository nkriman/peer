## ADDED Requirements

### Requirement: gather_git_history is a pure function over (repo_path, hunks)

The framework SHALL define `peer.context_git.gather_git_history(repo_path: Path, hunks: list[ContextHunk], n_recent_commits: int = 3) -> str`. The function SHALL:

1. Group hunks by `path`.
2. For each path:
   - Run `git -C <repo_path> log -n <n_recent_commits> --format='%h %an %s (%ar)' -- <path>` to collect recent commit summaries.
   - Run `git -C <repo_path> blame -L <line_start>,+<line_count> --porcelain <path>` for each hunk's line range; parse author + short hash per line.
3. Format the result as markdown with one section per path: a "Recent commits" bullet list, followed by per-hunk "@@ -line,+span @@ in <path>:" headers and per-line blame entries (`<hash> <author>: <line content>`).
4. Return the joined markdown string. Empty hunks list returns `""`.

The function SHALL be defensive: each subprocess call SHALL pass `check=False`, capture stderr, and on non-zero exit emit a WARNING log and skip that path's section. The function SHALL NEVER raise on git failures — graceful degradation matches the linter pattern.

#### Scenario: gather_git_history formats recent commits + blame for one path

- **GIVEN** a fake git that returns 3 commits for `src/foo.py` and 2 blame lines for the modified range
- **WHEN** `gather_git_history(repo_path, [ContextHunk(path="src/foo.py", new_start=10, new_lines=2, ...)])` is called
- **THEN** the returned string contains the literal `"Recent commits to src/foo.py:"`
- **AND** contains the literal `"@@ -10,+2 @@ in src/foo.py:"`
- **AND** contains both blame lines' author names

#### Scenario: gather_git_history returns empty string for empty hunks

- **WHEN** `gather_git_history(repo_path, [])` is called
- **THEN** the returned string is `""`

#### Scenario: gather_git_history degrades on git failure

- **GIVEN** a fake git that returns exit code 128 (not a git repo) for every call
- **WHEN** `gather_git_history(repo_path, [hunk])` is called
- **THEN** the function does NOT raise
- **AND** the returned string is `""`
- **AND** a WARNING log line is emitted referencing the failed path

### Requirement: CodebaseContext gains an optional git_history field

The `peer.types.CodebaseContext` Pydantic model SHALL gain a field `git_history: str = ""`. Empty string means "git history not gathered" (the default for back-compat). Non-empty string means `gather_git_history` returned markdown that should be rendered in the prompt.

#### Scenario: default CodebaseContext has empty git_history

- **WHEN** `CodebaseContext()` is constructed with no overrides
- **THEN** `cc.git_history` equals `""`

### Requirement: gather_codebase_context accepts include_git_history

The framework SHALL extend `gather_codebase_context()` with a keyword argument `include_git_history: bool = False`. When True AND `_ensure_repo_checkout` returned a valid path, the function SHALL call `gather_git_history(repo_path, ctx.hunks)` and store the result in `cc.git_history`. When False, `cc.git_history` SHALL remain `""`.

The flag SHALL NOT bypass the existing `_have_tree_sitter()` graceful-degradation check; git history runs independently of tree-sitter availability.

#### Scenario: include_git_history=True populates the field

- **GIVEN** a fake `_ensure_repo_checkout` returning a valid path and a fake `gather_git_history` returning "fake blame content"
- **WHEN** `gather_codebase_context(ctx, include_git_history=True)` is called
- **THEN** `cc.git_history` equals `"fake blame content"`

#### Scenario: include_git_history=False leaves the field empty

- **WHEN** `gather_codebase_context(ctx, include_git_history=False)` is called
- **THEN** `cc.git_history` equals `""`

### Requirement: format_prompt renders a GIT HISTORY section when present

The `peer.prompts.format_prompt(ctx, cc)` function SHALL render a `## GIT HISTORY` section in the user prompt when `cc.git_history` is non-empty. The section SHALL appear BEFORE the existing `## LINTER FINDINGS` section (so the model reads history → linter → diff in increasing-specificity order). The section header is the literal `## GIT HISTORY`, followed by a brief leading paragraph instructing the model to weigh authorship + recency signals, followed by the verbatim `cc.git_history` body. When `cc.git_history` is empty, the section SHALL NOT be rendered at all (no empty header).

#### Scenario: prompt includes GIT HISTORY section when populated

- **GIVEN** a Context with one hunk and a CodebaseContext where `git_history = "fake blame content"`
- **WHEN** `format_prompt(ctx, cc)` is called
- **THEN** the rendered prompt contains the literal `"## GIT HISTORY"`
- **AND** contains the literal `"fake blame content"`

#### Scenario: prompt omits GIT HISTORY section when empty

- **GIVEN** a CodebaseContext with `git_history = ""`
- **WHEN** `format_prompt(ctx, cc)` is called
- **THEN** the rendered prompt does NOT contain the literal `"## GIT HISTORY"`

### Requirement: Recipe.include_git_history toggles the section

The `peer.recipe.Recipe` model SHALL gain a field `include_git_history: bool = False`. When the recipe is applied to an Agent, the recipe's value SHALL be propagated into `gather_codebase_context(include_git_history=...)` at `Agent.run` time. (Mirrors how peer-config-v01 + linter-context-v01 plumb deps fields into the gather.)

#### Scenario: Recipe with include_git_history=True yields a populated git_history

- **GIVEN** a Recipe with `include_git_history=True` and a fake `gather_git_history` returning "blame text"
- **WHEN** an `Agent(recipe=recipe).run(pr_url)` call dispatches to the (mocked) gather pipeline
- **THEN** the CodebaseContext passed to the reviewer has `git_history == "blame text"`

#### Scenario: Recipe defaults preserve back-compat

- **WHEN** `Recipe()` is constructed with no overrides
- **THEN** `recipe.include_git_history` equals `False`
