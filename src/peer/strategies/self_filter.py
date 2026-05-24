"""SelfFilterReviewer: drop Comments whose confidence-judge score falls below a threshold.

After the inner reviewer produces a draft list, each Comment is passed to
an `inner_judge` (any callable matching `(comment, ctx) -> float in [0, 1]`).
Comments scoring below `min_confidence` are dropped + INFO-logged.

The judge can be:
  - a custom callable (preferred for tests / cost-sensitive use)
  - a Reviewer-Protocol-shaped object (we call its `.review()` with a
    Context narrowed to the Comment's hunk and parse a 0-1 from the
    response's first Comment body's first token — best-effort)
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..reviewers import Reviewer
from ..types import CodebaseContext, Comment, Context

logger = logging.getLogger(__name__)

ConfidenceJudge = Callable[[Comment, Context], float]


def _merge_usage(usages: list[dict]) -> dict:
    out: dict = {"input_tokens": 0, "output_tokens": 0, "model": "self_filter"}
    for u in usages:
        for k in ("input_tokens", "output_tokens"):
            v = u.get(k)
            if isinstance(v, int):
                out[k] += v
    return out


def _parse_first_float(text: str) -> float:
    m = re.search(r"\b(0?\.\d+|1\.0|0|1)\b", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return 0.0


@dataclass
class SelfFilterReviewer:
    """Drop Comments whose confidence-judge score is below `min_confidence`."""

    name: str = "self_filter"
    model: str = "self_filter:composite"
    inner: Reviewer | None = None
    inner_judge: ConfidenceJudge | None = None
    min_confidence: float = 0.5
    extra_usage: dict = field(default_factory=dict)

    def review(
        self,
        context: Context,
        codebase_context: CodebaseContext | None = None,
        *,
        extra_user_message: str | None = None,
        run_context: object | None = None,
    ) -> tuple[list[Comment], dict]:
        if self.inner is None:
            raise ValueError("SelfFilterReviewer requires an `inner` reviewer.")
        if self.inner_judge is None:
            raise ValueError(
                "SelfFilterReviewer requires a `inner_judge` callable "
                "(Comment, Context) -> float in [0, 1]."
            )
        draft, draft_usage = self.inner.review(
            context,
            codebase_context,
            extra_user_message=extra_user_message,
            run_context=run_context,
        )
        usages: list[dict] = [draft_usage]
        kept: list[Comment] = []
        for c in draft:
            score = self.inner_judge(c, context)
            if score >= self.min_confidence:
                kept.append(c)
            else:
                logger.info(
                    "self_filter dropping %s:%s sev=%s (confidence=%.2f < %.2f)",
                    c.path,
                    c.line,
                    c.severity,
                    score,
                    self.min_confidence,
                )
        return kept, _merge_usage(usages)
