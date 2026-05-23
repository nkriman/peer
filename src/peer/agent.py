"""Top-level PR review agent: dispatches to a Reviewer based on the model id,
gathers context, validates LLM output against the diff, and returns a Review.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .context import gather
from .exceptions import UnknownModelError
from .prompts import DEFAULT_SYSTEM_PROMPT
from .reviewers import ClaudeReviewer, Reviewer
from .types import Comment, Context, Review

logger = logging.getLogger(__name__)


def _select_reviewer(model: str, system_prompt: str) -> Reviewer:
    if model.startswith("claude"):
        return ClaudeReviewer(model=model, system_prompt=system_prompt)
    if model.startswith("gpt"):
        raise UnknownModelError(
            f"OpenAI backend not yet implemented (Slice 3). model={model}"
        )
    raise UnknownModelError(
        f"Unknown model: {model}. Supported prefixes in Slice 1: claude-*."
    )


def _valid_lines_per_path(ctx: Context) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    for h in ctx.hunks:
        bucket = out.setdefault(h.path, set())
        for ln in range(h.new_start, h.new_start + max(h.new_lines, 0)):
            bucket.add(ln)
    return out


def _validate_comments(
    comments: list[Comment], ctx: Context
) -> list[Comment]:
    valid_lines = _valid_lines_per_path(ctx)
    out: list[Comment] = []
    for c in comments:
        if c.path not in valid_lines:
            logger.warning(
                "Dropping comment with unknown path: %s (severity=%s)",
                c.path, c.severity,
            )
            continue
        if c.line is not None and c.line not in valid_lines[c.path]:
            logger.warning(
                "Dropping comment with out-of-hunk line: %s:%s",
                c.path, c.line,
            )
            continue
        out.append(c)
    return out


class Agent:
    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        system_prompt: Optional[str] = None,
        system_prompt_file: Optional[Path] = None,
    ) -> None:
        if system_prompt and system_prompt_file:
            raise ValueError(
                "Pass system_prompt OR system_prompt_file, not both."
            )
        if system_prompt_file:
            system_prompt = Path(system_prompt_file).read_text()
        self.model = model
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.reviewer = _select_reviewer(model, self.system_prompt)

    def review(self, pr_url: str) -> Review:
        ctx = gather(pr_url)
        logger.info(
            "Gathered context for %s: %d hunks, ~%d tokens",
            pr_url, len(ctx.hunks), ctx.token_estimate,
        )
        raw_comments, usage = self.reviewer.review(ctx)
        valid = _validate_comments(raw_comments, ctx)
        dropped = len(raw_comments) - len(valid)
        if dropped:
            logger.info("Dropped %d invalid comment(s)", dropped)
        if not valid:
            return Review(comments=[], reason="no issues found", usage=usage)
        return Review(comments=valid, usage=usage)
