"""Git-history context section (blame-enricher-v01).

Pure function over `(repo_path, hunks)` that returns formatted markdown
ready to drop into `format_prompt` as a `## GIT HISTORY` section. Used
when `Recipe.include_git_history = True`.

Defensive: every subprocess call uses `check=False`; failures log a
WARNING and skip that path's section. Never raises on git errors —
graceful degradation matches the linter pattern.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .types import ContextHunk

logger = logging.getLogger(__name__)


def _run_git(repo_path: Path, *args: str) -> tuple[int, str]:
    """Run `git -C <repo_path> <args>`. Returns (returncode, stdout)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("git invocation failed (%s): %s", e, args[:3])
        return 1, ""
    if proc.returncode != 0:
        logger.warning(
            "git %s exited %s on %s; stderr=%s",
            args[0] if args else "?",
            proc.returncode,
            repo_path,
            (proc.stderr or "")[:200],
        )
    return proc.returncode, proc.stdout or ""


def _parse_blame_porcelain(text: str) -> list[tuple[str, str, str]]:
    """Parse `git blame --porcelain` output into [(short_hash, author, content), ...].

    Porcelain emits one section per source line. The first line of each
    section is `<full-hash> <orig-line> <final-line> [num-lines]`. Header
    fields follow (key value lines) until a tab-prefixed content line.
    We collect author + first 8 chars of hash + the content line.
    """
    out: list[tuple[str, str, str]] = []
    cur_hash = ""
    cur_author = ""
    for raw_line in text.splitlines():
        if not raw_line:
            continue
        if raw_line.startswith("\t"):
            # The actual source line for the current entry.
            out.append((cur_hash[:8], cur_author or "?", raw_line[1:]))
            continue
        parts = raw_line.split(" ", 1)
        head = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        if len(head) == 40 and all(c in "0123456789abcdef" for c in head):
            # New section header line
            cur_hash = head
        elif head == "author":
            cur_author = rest
    return out


def gather_git_history(
    repo_path: Path,
    hunks: list[ContextHunk],
    n_recent_commits: int = 3,
) -> str:
    """Format recent commits + blame for each path touched by `hunks`.

    Returns a markdown string suitable for inclusion in a `## GIT HISTORY`
    prompt section. Empty hunks → empty string. Git failures → empty
    string + WARNING log.
    """
    if not hunks:
        return ""

    by_path: dict[str, list[ContextHunk]] = {}
    for h in hunks:
        by_path.setdefault(h.path, []).append(h)

    sections: list[str] = []
    for path, path_hunks in by_path.items():
        # Recent commits to the file.
        rc, log_out = _run_git(
            repo_path,
            "log",
            f"-n{n_recent_commits}",
            "--format=%h %an: %s (%ar)",
            "--",
            path,
        )
        # Per-hunk blame.
        any_blame = False
        path_lines: list[str] = []
        if rc == 0 and log_out.strip():
            path_lines.append(f"Recent commits to {path}:")
            for line in log_out.strip().splitlines():
                path_lines.append(f"  - {line}")

        for h in path_hunks:
            blame_rc, blame_out = _run_git(
                repo_path,
                "blame",
                f"-L{h.new_start},+{max(h.new_lines, 1)}",
                "--porcelain",
                path,
            )
            if blame_rc == 0 and blame_out:
                any_blame = True
                path_lines.append(f"\n@@ -{h.new_start},+{h.new_lines} @@ in {path}:")
                for short_hash, author, content in _parse_blame_porcelain(blame_out):
                    path_lines.append(f"  {short_hash} {author}: {content}")

        # Skip this path entirely if neither log nor blame produced anything.
        if path_lines and (rc == 0 or any_blame):
            sections.append("\n".join(path_lines))

    return "\n\n".join(sections)
