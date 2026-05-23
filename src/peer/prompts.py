"""Default system prompt + LLM input formatting.

Per Decision 13 (agent-v01): the default prompt MUST explicitly name
the codebase-context fields and direct the model to consult them.
CodeCompass (arXiv 2602.20048) measured that without this explicit
direction, agents ignore structural context in 58% of trials.
"""

from typing import Optional

from .types import CodebaseContext, Context

DEFAULT_SYSTEM_PROMPT = """You are an expert code reviewer reviewing a GitHub pull request.

You will be given two kinds of context:

1. PR CONTEXT
   - The PR title, description, and prior discussion
   - The unified-diff hunks for each modified file
   - Surrounding code from the file at the PR head, for context around each hunk

2. CODEBASE CONTEXT (may be empty if the codebase context module is unavailable)
   - `modified_symbols`: the function / method / class definitions whose source spans
     overlap with the PR diff — these are the things the PR is changing
   - `call_sites`: where each modified symbol is referenced elsewhere in the repository.
     Use these to reason about the blast radius of the change. If a function's contract
     changes, check whether the call sites assume the old contract.
   - `related_tests`: existing test files that map to the modified source files by path
     convention. Use them to (a) check whether the PR updates the tests for behaviour it
     changes, and (b) reason about what the existing tests do and do not cover.
   - `untested_files`: modified source files with no matching test file. A signal that
     the change may lack test coverage.

For every non-trivial concern you identify, emit a structured Comment via the `post_review_comments` tool. Each comment has:
- path: the exact file path from the diff
- line: the line number in the new file (use the new-file line numbering from the diff hunk header)
- severity: one of "critical" (likely bug or security issue), "important" (significant correctness or design concern), "minor" (worth fixing but not blocking), "nit" (style or preference)
- body: a clear, specific comment a human reviewer could action
- rationale: a short justification grounded in the diff, surrounding code, or codebase context (cite specifically — e.g., "see call_sites for X at path:line"). Do NOT invent supporting evidence; if you don't have a citation, don't claim one.

Rules:
- Prioritize correctness, security, and clarity. Skip stylistic comments unless the file's style is strong and visible.
- Do NOT comment on lines outside the diff hunks. Do NOT invent file paths.
- USE the codebase context when it's available. If call_sites show a function has callers, your concerns about contract changes carry more weight; if call_sites is empty, "this could break callers" is hypothetical — say so or drop the comment.
- If the PR looks correct, return an empty `comments` list — false positives erode reviewer trust more than missed issues.
- Be concise. One issue per Comment.
"""


def format_prompt(
    ctx: Context, cc: Optional[CodebaseContext] = None
) -> str:
    """Render the Context (and optional CodebaseContext) as a labeled,
    sectioned string for the LLM."""
    parts: list[str] = [
        f"# PR #{ctx.number}: {ctx.title}",
        f"Repo: {ctx.owner}/{ctx.repo}",
        f"URL: {ctx.pr_url}",
        f"Head SHA: {ctx.head_sha}",
        "",
        "## PR description",
        ctx.body.strip() if ctx.body.strip() else "(no description)",
        "",
    ]

    if ctx.prior_comments:
        parts.append("## Prior discussion")
        for c in ctx.prior_comments:
            parts.append(c.strip())
            parts.append("")

    parts.append("## PR diff")
    if not ctx.hunks:
        parts.append("(no hunks)")
    for h in ctx.hunks:
        new_end = h.new_start + max(h.new_lines - 1, 0)
        parts.append(f"### {h.path} (new lines {h.new_start}-{new_end})")
        parts.append("```diff")
        parts.append(h.diff_text.rstrip())
        parts.append("```")
        if h.surrounding_code:
            parts.append(f"Surrounding code from `{h.path}` at head:")
            parts.append("```")
            parts.append(h.surrounding_code.rstrip())
            parts.append("```")
        parts.append("")

    if cc is not None and (
        cc.modified_symbols or cc.call_sites
        or cc.related_tests or cc.untested_files
    ):
        parts.append("## Codebase context")
        parts.append("")

        if cc.modified_symbols:
            parts.append("### modified_symbols")
            for s in cc.modified_symbols:
                qual = f"{s.enclosing_qualifier}." if s.enclosing_qualifier else ""
                tag = " [DELETED]" if s.deleted else ""
                parts.append(
                    f"- {s.kind} `{qual}{s.name}` @ {s.path}:{s.start_line}-{s.end_line}{tag}"
                )
                parts.append(f"  ```python")
                parts.append(f"  {s.signature}")
                parts.append(f"  ```")
            parts.append("")

        if cc.call_sites:
            parts.append("### call_sites")
            for c in cc.call_sites:
                parts.append(f"- `{c.symbol_name}` called at {c.path}:{c.line}")
                parts.append("  ```")
                parts.append("  " + c.snippet.replace("\n", "\n  "))
                parts.append("  ```")
            parts.append("")

        if cc.related_tests:
            parts.append("### related_tests")
            for t in cc.related_tests:
                trunc = " (truncated)" if t.truncated else ""
                parts.append(f"#### {t.path} — tests for `{t.source_file}`{trunc}")
                parts.append("```python")
                parts.append(t.content)
                parts.append("```")
            parts.append("")

        if cc.untested_files:
            parts.append("### untested_files")
            parts.append(
                "These modified source files have no matching test file by convention:"
            )
            for f in cc.untested_files:
                parts.append(f"- `{f}`")
            parts.append("")

        if cc.unsupported_files:
            parts.append("### unsupported_files")
            parts.append(
                "These modified files are in a language not yet supported by the "
                "codebase-context extractor (v0.1 ships Python only):"
            )
            for f in cc.unsupported_files:
                parts.append(f"- `{f}`")
            parts.append("")

    return "\n".join(parts)


# Back-compat alias for Slice 1 callers; format_context == format_prompt with no cc.
def format_context(ctx: Context) -> str:
    return format_prompt(ctx, None)
