"""Default system prompt + LLM input formatting.

Per Decision 13 (agent-v01): the default prompt MUST explicitly name
the codebase-context fields and direct the model to consult them.
CodeCompass (arXiv 2602.20048) measured that without this explicit
direction, agents ignore structural context in 58% of trials.

Portions of DEFAULT_SYSTEM_PROMPT and the diff-format renderer are
adapted from The-PR-Agent/pr-agent (Apache License 2.0, copyright Qodo).
Specifically: the "Determining what to flag" + "Constructing comments"
calibration subsections, and the `__new hunk__` / `__old hunk__` diff
section format with prepended new-file line numbers.

See `docs/pr_agent_reverse_engineering.md` for the reverse-engineering
analysis and the rationale behind these specific adoptions.
"""

from .types import CodebaseContext, Context, ContextHunk

DEFAULT_SYSTEM_PROMPT = """You are an expert code reviewer reviewing a GitHub pull request. Focus on new code added in the PR (lines starting with '+') and on issues introduced by this PR.

You will be given two kinds of context:

1. PR CONTEXT
   - The PR title, description, and prior discussion.
   - Diff hunks for each modified file, presented in a structured format. Each `__new hunk__` line is prepended with its new-file line number; `__old hunk__` shows removed lines for reference.
   - Surrounding code from the file at the PR head, for context around each hunk.

2. CODEBASE CONTEXT (may be empty if the codebase context module is unavailable)
   - `modified_symbols`: the function / method / class definitions whose source spans
     overlap with the PR diff — these are the things the PR is changing.
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
- line: the new-file line number, as shown in the `__new hunk__` section
- end_line: (optional) inclusive upper bound for a multi-line range. Set ONLY when the concern spans multiple lines; otherwise omit it. Must stay within the same hunk and satisfy `end_line >= line`.
- severity: one of "critical" (likely bug or security issue), "important" (significant correctness or design concern), "minor" (worth fixing but not blocking), "nit" (style or preference)
- body: a clear, specific comment a human reviewer could action
- rationale: a short justification grounded in the diff, surrounding code, or codebase context (cite specifically — e.g., "see call_sites for X at path:line"). Do NOT invent supporting evidence; if you don't have a citation, don't claim one.
- issue_header: (optional) a 1-3 word categorical label such as "Possible Bug", "Performance Concern", "Test Coverage", or "Security". Surfaced in CLI output and eval reports for grouping. Omit when no short label fits.
- suggestion: (optional) the proposed replacement text for the lines being commented on. INCLUDE a suggestion ONLY when ALL of the following hold:
  * the fix is small (≤5 lines of changed code),
  * the fix is concrete (you can write the exact replacement, not a description),
  * you are confident the replacement compiles / type-checks / preserves behavior outside the bug.
  DO NOT include a suggestion for vague guidance like "consider refactoring this", for large rewrites, or when you are uncertain about syntax — the empty `suggestion` field is the right call there.

Determining what to flag:
- For clear bugs and security issues, be thorough. Do not skip a genuine problem just because the trigger scenario is narrow.
- For lower-severity concerns, be certain before flagging. If you cannot confidently explain why something is a problem with a concrete scenario, do not flag it.
- Each issue must be discrete and actionable, not a vague concern about the codebase in general.
- Do not speculate that a change might break other code unless you can identify the specific affected code path from the diff context.
- Do not flag intentional design choices or stylistic preferences unless they introduce a clear defect.
- When confidence is limited but the potential impact is high (e.g., data loss, security), report it with an explicit note on what remains uncertain. Otherwise, prefer not reporting over guessing.

Constructing comments:
- Be direct about why something is a problem and the realistic scenario where it manifests.
- Communicate severity accurately. Do not overstate impact. If an issue only arises under specific inputs or environments, say so upfront.
- Keep each issue description concise. Write so the reader grasps the point immediately without close reading.
- Use a matter-of-fact, helpful tone. Avoid accusatory language, excessive praise, or filler phrases like 'Great job', 'Thanks for'.

Peer-specific guardrails:
- Do NOT comment on lines outside the diff hunks. Do NOT invent file paths.
- USE the codebase context when it's available. If `call_sites` show a function has callers, your concerns about contract changes carry more weight; if `call_sites` is empty, "this could break callers" is hypothetical — say so or drop the comment.
- If the PR looks correct, return an empty `comments` list — false positives erode reviewer trust more than missed issues.
- One issue per Comment.
"""


# ---------------------------------------------------------------------------
# Diff rendering (adapted from PR-Agent's `__new hunk__` / `__old hunk__` format)
# ---------------------------------------------------------------------------


def _parse_hunk_to_lines(hunk: ContextHunk) -> tuple[str, list[tuple[str, str, int | None]]]:
    """Parse a ContextHunk into (header, lines).

    `lines` is a list of (op, content, new_line_no) tuples where:
      - op is one of " ", "+", "-"
      - content is the line's text (no op prefix)
      - new_line_no is the new-file line number (for context + added lines) or None (for removed)
    """
    raw = hunk.diff_text.splitlines()
    header = ""
    lines: list[tuple[str, str, int | None]] = []
    new_no = hunk.new_start
    for line in raw:
        if line.startswith("@@"):
            header = line
            continue
        if not line:
            # blank line in diff is typically the trailing newline; treat as context
            lines.append((" ", "", new_no))
            new_no += 1
            continue
        op = line[0]
        content = line[1:]
        if op == "+":
            lines.append(("+", content, new_no))
            new_no += 1
        elif op == "-":
            lines.append(("-", content, None))
            # No new-file line number; don't increment new_no
        elif op == " ":
            lines.append((" ", content, new_no))
            new_no += 1
        elif op == "\\":
            # `\ No newline at end of file` — skip
            continue
        else:
            # Unexpected (e.g. binary marker); treat as context
            lines.append((" ", line, new_no))
            new_no += 1
    return header, lines


def _normalize_header(header: str) -> str:
    """Turn `@@ -10,5 +10,5 @@ def foo():` into `@@ ... @@ def foo():`."""
    if not header.startswith("@@"):
        return header
    parts = header.split("@@", 2)
    suffix = parts[2].strip() if len(parts) > 2 else ""
    return f"@@ ... @@ {suffix}".rstrip()


def _render_hunk_pragent_format(hunk: ContextHunk) -> list[str]:
    """Render one ContextHunk in PR-Agent's __new hunk__ / __old hunk__ format
    with new-file line numbers prepended. Returns a list of output lines."""
    header, lines = _parse_hunk_to_lines(hunk)
    out: list[str] = []
    if header:
        out.append(_normalize_header(header))

    new_lines = [(op, content, n) for op, content, n in lines if op in (" ", "+")]
    old_lines = [(op, content) for op, content, _ in lines if op in (" ", "-")]
    has_removals = any(op == "-" for op, _ in old_lines)

    out.append("__new hunk__")
    for op, content, n in new_lines:
        ln = f"{n:>4}" if n is not None else "    "
        out.append(f"{ln} {op}{content}")

    if has_removals:
        out.append("__old hunk__")
        for op, content in old_lines:
            out.append(f"{op}{content}")
    return out


# ---------------------------------------------------------------------------
# Top-level prompt formatter
# ---------------------------------------------------------------------------


def format_prompt(ctx: Context, cc: CodebaseContext | None = None) -> str:
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

    # Group hunks by file for cleaner rendering — one ## File: header per file.
    file_to_hunks: dict[str, list[ContextHunk]] = {}
    for h in ctx.hunks:
        file_to_hunks.setdefault(h.path, []).append(h)

    for path, hunks in file_to_hunks.items():
        parts.append("")
        parts.append(f"## File: '{path}'")
        for h in hunks:
            parts.append("")
            parts.extend(_render_hunk_pragent_format(h))
            if h.surrounding_code:
                parts.append("")
                parts.append(f"Surrounding code from `{h.path}` at head (for additional context):")
                parts.append("```")
                parts.append(h.surrounding_code.rstrip())
                parts.append("```")
        parts.append("")

    if cc is not None and (
        cc.modified_symbols
        or cc.call_sites
        or cc.related_tests
        or cc.untested_files
        or cc.linter_findings
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
                parts.append("  ```python")
                parts.append(f"  {s.signature}")
                parts.append("  ```")
            parts.append("")

        if cc.call_sites:
            parts.append("### call_sites")
            for cs in cc.call_sites:
                parts.append(f"- `{cs.symbol_name}` called at {cs.path}:{cs.line}")
                parts.append("  ```")
                parts.append("  " + cs.snippet.replace("\n", "\n  "))
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
            parts.append("These modified source files have no matching test file by convention:")
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

        if cc.linter_findings:
            parts.append("## LINTER FINDINGS")
            parts.append(
                "Pre-computed by linters running on the modified files. CITE the "
                "rule_id and message when surfacing a related issue; do NOT re-discover "
                "and post a duplicate Comment for something the linter already caught."
            )
            for lf in cc.linter_findings:
                parts.append(
                    f"- [{lf.linter} {lf.rule_id} {lf.severity}] {lf.path}:{lf.line} — {lf.message}"
                )
                if lf.fix_suggestion:
                    parts.append(f"  fix: {lf.fix_suggestion}")
            parts.append("")

    return "\n".join(parts)


# Back-compat alias for Slice 1 callers; format_context == format_prompt with no cc.
def format_context(ctx: Context) -> str:
    return format_prompt(ctx, None)
