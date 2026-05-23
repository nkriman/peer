"""Default system prompt + LLM input formatting.

Slice 1 prompt covers PR diff + surrounding code + prior discussion only.
Slice 2 will revise this to also name modified_symbols / call_sites /
related_tests / untested_files explicitly (Decision 13).
"""

from .types import Context

DEFAULT_SYSTEM_PROMPT = """You are an expert code reviewer reviewing a GitHub pull request.

You will be given:
- The PR title, description, and prior discussion
- The unified-diff hunks for each modified file
- Surrounding code from the file at the PR head, for context around each hunk

For every non-trivial concern you identify in the diff, emit a structured Comment via the `post_review_comments` tool. Each comment has:
- path: the exact file path from the diff
- line: the line number in the new file (use the new-file line numbering from the diff hunk header)
- severity: one of "critical" (likely bug or security issue), "important" (significant correctness or design concern), "minor" (worth fixing but not blocking), "nit" (style or preference)
- body: a clear, specific comment a human reviewer could action
- rationale: a short justification grounded in the diff or surrounding code

Rules:
- Prioritize correctness, security, and clarity. Skip stylistic comments unless the surrounding code shows the file follows a strong style.
- Do NOT comment on lines outside the diff hunks. Do NOT invent file paths.
- If the PR looks correct, return an empty `comments` list — false positives erode reviewer trust more than missed issues.
- Be concise. One issue per Comment.
"""


def format_context(ctx: Context) -> str:
    """Render a Context as a labeled, sectioned string for the LLM."""
    parts: list[str] = [
        f"# PR #{ctx.number}: {ctx.title}",
        f"Repo: {ctx.owner}/{ctx.repo}",
        f"URL: {ctx.pr_url}",
        f"Head SHA: {ctx.head_sha}",
        "",
        "## Description",
        ctx.body.strip() if ctx.body.strip() else "(no description)",
        "",
    ]

    if ctx.prior_comments:
        parts.append("## Prior discussion")
        for c in ctx.prior_comments:
            parts.append(c.strip())
            parts.append("")

    parts.append("## Diff")
    if not ctx.hunks:
        parts.append("(no hunks)")
    for h in ctx.hunks:
        new_end = h.new_start + max(h.new_lines - 1, 0)
        parts.append(
            f"### {h.path} (new lines {h.new_start}-{new_end})"
        )
        parts.append("```diff")
        parts.append(h.diff_text.rstrip())
        parts.append("```")
        if h.surrounding_code:
            parts.append(f"Surrounding code from `{h.path}` at head:")
            parts.append("```")
            parts.append(h.surrounding_code.rstrip())
            parts.append("```")
        parts.append("")

    return "\n".join(parts)
