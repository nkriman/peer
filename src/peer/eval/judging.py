"""LLM-as-judge helper for semantic same-issue matching.

Promoted from the MVP at src/peer/eval.py: same prompt, but the comparator
now takes a GoldDefect (curated dataset record) instead of a raw HumanComment.
"""

from __future__ import annotations

import anthropic

from ..dataset.types import GoldDefect
from ..types import Comment

JUDGE_MODEL = "claude-haiku-4-5-20251001"
JUDGE_PROMPT = """Two code reviewers commented on a pull request, both on the same file. Decide whether they are flagging the SAME ISSUE or DIFFERENT ISSUES.

Reviewer A (line {peer_line}):
{peer_body}

Reviewer B (line {human_line}):
{human_body}

Same issue = the underlying concern is the same, even if phrased differently or focused on slightly different lines of the same code. Different issue = they're about different things entirely (different bugs, different concerns).

Respond with exactly one word: SAME or DIFFERENT."""


def judge_match(
    peer_comment: Comment,
    gold_defect: GoldDefect,
    client: anthropic.Anthropic | None = None,
) -> bool:
    """Use a cheap LLM judge to decide if a peer comment refers to the same
    issue as a gold defect."""
    if client is None:
        client = anthropic.Anthropic()
    gold_line = (
        gold_defect.line
        if gold_defect.line is not None
        else (gold_defect.line_range[0] if gold_defect.line_range else 0)
    )
    prompt = JUDGE_PROMPT.format(
        peer_line=peer_comment.line if peer_comment.line is not None else 0,
        peer_body=peer_comment.body[:1500],
        human_line=gold_line,
        human_body=gold_defect.description[:1500],
    )
    resp = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )
    text = ""
    for block in resp.content:
        t = getattr(block, "text", None)
        if t:
            text = t.strip().upper()
            break
    return text.startswith("SAME")
