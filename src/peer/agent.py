"""Top-level PR review agent: dispatches to a Reviewer based on the model id,
gathers context, validates LLM output against the diff, and returns a Review.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .codebase_context import gather_codebase_context
from .context import gather
from .exceptions import CodebaseContextTooLarge, UnknownModelError
from .prompts import DEFAULT_SYSTEM_PROMPT
from .reviewers import ClaudeReviewer, Reviewer
from .types import CodebaseContext, Comment, Context, Review

logger = logging.getLogger(__name__)


def _select_reviewer(model: str, system_prompt: str) -> Reviewer:
    if model.startswith("claude"):
        return ClaudeReviewer(model=model, system_prompt=system_prompt)
    if model.startswith("gpt"):
        raise UnknownModelError(f"OpenAI backend not yet implemented (Slice 3). model={model}")
    raise UnknownModelError(f"Unknown model: {model}. Supported prefixes in Slice 1: claude-*.")


def _valid_lines_per_path(ctx: Context) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    for h in ctx.hunks:
        bucket = out.setdefault(h.path, set())
        for ln in range(h.new_start, h.new_start + max(h.new_lines, 0)):
            bucket.add(ln)
    return out


def _validate_comments(comments: list[Comment], ctx: Context) -> list[Comment]:
    valid_lines = _valid_lines_per_path(ctx)
    out: list[Comment] = []
    for c in comments:
        if c.path not in valid_lines:
            logger.warning(
                "Dropping comment with unknown path: %s (severity=%s)",
                c.path,
                c.severity,
            )
            continue
        if c.line is not None and c.line not in valid_lines[c.path]:
            logger.warning(
                "Dropping comment with out-of-hunk line: %s:%s",
                c.path,
                c.line,
            )
            continue
        out.append(c)
    return out


class Agent:
    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        system_prompt: str | None = None,
        system_prompt_file: Path | None = None,
        team_conventions: str | None = None,
        team_conventions_file: Path | None = None,
    ) -> None:
        if system_prompt and system_prompt_file:
            raise ValueError("Pass system_prompt OR system_prompt_file, not both.")
        if team_conventions and team_conventions_file:
            raise ValueError("Pass team_conventions OR team_conventions_file, not both.")
        if system_prompt_file:
            system_prompt = Path(system_prompt_file).read_text()
        if team_conventions_file:
            team_conventions = Path(team_conventions_file).read_text()

        base_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        if team_conventions:
            base_prompt = (
                base_prompt
                + "\n\n# TEAM CONVENTIONS\n\n"
                + "The following document captures style and review conventions "
                "this team consistently applies. When reviewing the PR below, "
                "flag departures from these conventions as defects. Infer the "
                "appropriate severity from the convention's own framing — a "
                "stated style preference is a style nit; a stated correctness "
                "rule is a correctness defect. Cite the convention by name when "
                "flagging a related issue.\n\n" + team_conventions.strip() + "\n"
            )
        self.model = model
        self.system_prompt = base_prompt
        self.reviewer = _select_reviewer(model, self.system_prompt)

    def review(self, pr_url: str) -> Review:
        ctx = gather(pr_url)
        logger.info(
            "Gathered PR context for %s: %d hunks, ~%d tokens",
            pr_url,
            len(ctx.hunks),
            ctx.token_estimate,
        )
        cc: CodebaseContext | None = None
        try:
            cc = gather_codebase_context(ctx)
            logger.info(
                "Gathered codebase context: %d symbols, %d call sites, "
                "%d tests, %d untested, ~%d tokens",
                len(cc.modified_symbols),
                len(cc.call_sites),
                len(cc.related_tests),
                len(cc.untested_files),
                cc.token_estimate,
            )
        except CodebaseContextTooLarge as e:
            logger.warning("Codebase context too large, proceeding without: %s", e)
            cc = None
        except Exception as e:
            logger.warning(
                "Codebase context extraction failed (%s); proceeding with PR context only",
                e,
            )
            cc = None

        raw_comments, usage = self.reviewer.review(ctx, cc)
        valid = _validate_comments(raw_comments, ctx)
        dropped = len(raw_comments) - len(valid)
        if dropped:
            logger.info("Dropped %d invalid comment(s)", dropped)
        if not valid:
            return Review(comments=[], reason="no issues found", usage=usage)
        return Review(comments=valid, usage=usage)
