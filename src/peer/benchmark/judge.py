"""Bug-detection judge: did a peer Comment identify a known bug?

Two-stage filter:
  1. Cheap deterministic prefilter: path overlap + line proximity (±10 by
     default). If the peer Comment isn't on the bug's file or is more than
     `proximity` lines away from the bug range, return False immediately —
     no judge call.
  2. LLM judge call: single Haiku-class invocation. Prompt is grounded on
     the bug's root_cause + the peer Comment's body/rationale. Parses
     CAUGHT vs NOT_CAUGHT from the response.
"""

from __future__ import annotations

import logging
from typing import Any

from ..types import Comment
from .types import BugSample

logger = logging.getLogger(__name__)

DEFAULT_JUDGE_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_PROXIMITY_LINES = 10


def _in_proximity(comment: Comment, bug: BugSample, proximity: int) -> bool:
    """True iff the Comment's path matches any bug location and its line is
    within `proximity` of that location's [start_line, end_line] range."""
    if comment.line is None:
        return False
    for loc in bug.bug_paths:
        if loc.path != comment.path:
            continue
        lo, hi = loc.start_line - proximity, loc.end_line + proximity
        if lo <= comment.line <= hi:
            return True
    return False


def _build_judge_prompt(bug: BugSample, comment: Comment) -> str:
    return (
        f"You are evaluating whether a code-review comment correctly identified "
        f"a known bug.\n\n"
        f"KNOWN BUG:\n"
        f"  bug_id: {bug.bug_id}\n"
        f"  root_cause: {bug.root_cause}\n"
        f"  affected: "
        + ", ".join(f"{loc.path}:{loc.start_line}-{loc.end_line}" for loc in bug.bug_paths)
        + "\n\n"
        f"PEER COMMENT:\n"
        f"  location: {comment.path}:{comment.line}\n"
        f"  body: {comment.body}\n"
        f"  rationale: {comment.rationale}\n\n"
        f'Respond on ONE line: "CAUGHT — <reason>" if the comment correctly '
        f"identifies the same bug (same root cause, same defect), or "
        f'"NOT_CAUGHT — <reason>" otherwise. Be strict: a vague comment about '
        f"unrelated code that happens to be nearby is NOT_CAUGHT."
    )


def _parse_judge_response(text: str) -> tuple[bool, str]:
    """Returns (caught, reason). Defaults to False on ambiguous output."""
    head = text.strip().splitlines()[0] if text.strip() else ""
    upper = head.upper()
    if upper.startswith("CAUGHT"):
        return True, head
    if upper.startswith("NOT_CAUGHT") or "NOT_CAUGHT" in upper or upper.startswith("NOT "):
        return False, head
    logger.warning("ambiguous judge response: %r", head)
    return False, f"ambiguous: {head}"


def judge_bug_caught(
    bug: BugSample,
    peer_comment: Comment,
    client: Any | None = None,
    *,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    proximity: int = DEFAULT_PROXIMITY_LINES,
) -> bool:
    """Did `peer_comment` catch `bug`?

    Returns False without invoking the judge when path/proximity prefilter
    fails. When `client` is None, raises RuntimeError — the caller (runner)
    is responsible for providing an Anthropic client.
    """
    if not _in_proximity(peer_comment, bug, proximity):
        return False
    if client is None:
        raise RuntimeError(
            "judge_bug_caught requires an anthropic.Anthropic-shaped client; "
            "the BugBenchmarkRunner passes one in. For tests, pass a fake."
        )
    prompt = _build_judge_prompt(bug, peer_comment)
    resp = client.messages.create(
        model=judge_model,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    # Anthropic SDK + most test fakes expose response.content as a list of
    # blocks; take the first text block's text.
    text = ""
    for block in getattr(resp, "content", []):
        t = getattr(block, "text", None)
        if t:
            text = t
            break
    caught, _reason = _parse_judge_response(text)
    return caught
