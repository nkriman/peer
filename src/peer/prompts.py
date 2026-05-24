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

from pathlib import Path as _Path

from .types import CodebaseContext, Context, ContextHunk

_PROMPT_FILE = _Path(__file__).resolve().parents[2] / "prompts" / "default_system_prompt.md"
if not _PROMPT_FILE.exists():
    raise FileNotFoundError(
        f"Default system prompt file not found at {_PROMPT_FILE}. "
        f"This file is the canonical source of truth for peer's default "
        f"reviewer instructions; restore it or check your working directory."
    )
DEFAULT_SYSTEM_PROMPT: str = _PROMPT_FILE.read_text()


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
        or cc.git_history
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

        if cc.git_history:
            parts.append("## GIT HISTORY")
            parts.append(
                "Recent commits and blame for files touched by this PR. Use this "
                "to weigh authorship + recency signals — old battle-tested code vs "
                "recent code in flux, same-author-as-surrounding-code vs not."
            )
            parts.append(cc.git_history)
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
