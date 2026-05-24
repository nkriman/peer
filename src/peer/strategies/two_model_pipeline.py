"""TwoModelPipelineReviewer: screen with cheap model, detail with expensive.

Screen pass identifies candidate problem locations (typically with a cheap
model like Haiku). For each candidate, the detail pass runs on a narrowed
Context containing only that location's hunk, producing the final Comment.

This lets recipes trade cost for quality at known granularity — peer runs
the cheap model on the whole PR and only spends the expensive model where
the screen flagged something interesting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..reviewers import Reviewer
from ..types import CodebaseContext, Comment, Context

logger = logging.getLogger(__name__)


def _merge_usage(usages: list[dict]) -> dict:
    out: dict = {"input_tokens": 0, "output_tokens": 0, "model": "two_model_pipeline"}
    for u in usages:
        for k in ("input_tokens", "output_tokens"):
            v = u.get(k)
            if isinstance(v, int):
                out[k] += v
    return out


def _narrow_context_to_path(ctx: Context, path: str) -> Context:
    """Return a Context whose hunks list is filtered to those on `path`."""
    return Context(
        pr_url=ctx.pr_url,
        owner=ctx.owner,
        repo=ctx.repo,
        number=ctx.number,
        title=ctx.title,
        body=ctx.body,
        head_sha=ctx.head_sha,
        hunks=[h for h in ctx.hunks if h.path == path],
        prior_comments=ctx.prior_comments,
        token_estimate=ctx.token_estimate,
    )


@dataclass
class TwoModelPipelineReviewer:
    """Two-stage reviewer: cheap screen → expensive detail per candidate."""

    name: str = "two_model_pipeline"
    model: str = "two_model_pipeline:composite"
    screen: Reviewer | None = None
    detail: Reviewer | None = None
    extra_usage: dict = field(default_factory=dict)

    def review(
        self,
        context: Context,
        codebase_context: CodebaseContext | None = None,
        *,
        extra_user_message: str | None = None,
        run_context: object | None = None,
    ) -> tuple[list[Comment], dict]:
        if self.screen is None or self.detail is None:
            raise ValueError(
                "TwoModelPipelineReviewer requires both `screen` and `detail` reviewers."
            )

        screen_out, screen_usage = self.screen.review(
            context,
            codebase_context,
            extra_user_message=extra_user_message,
            run_context=run_context,
        )
        usages: list[dict] = [screen_usage]
        if not screen_out:
            usage = _merge_usage(usages)
            return [], usage

        # De-duplicate by path so we don't run the detail pass twice on the
        # same file when the screen flagged multiple things in it.
        seen_paths: set[str] = set()
        detail_comments: list[Comment] = []
        for c in screen_out:
            if c.path in seen_paths:
                continue
            seen_paths.add(c.path)
            narrowed = _narrow_context_to_path(context, c.path)
            if not narrowed.hunks:
                # Screen Comment cited a path with no hunks — skip.
                continue
            detail_out, detail_usage = self.detail.review(
                narrowed,
                codebase_context,
                extra_user_message=None,
                run_context=run_context,
            )
            usages.append(detail_usage)
            detail_comments.extend(detail_out)

        return detail_comments, _merge_usage(usages)
