"""DraftCritiqueReviewer: wrap any inner reviewer in a draft → critique loop.

Draft pass produces an initial list of Comments. Critique pass receives that
list as additional context and returns a follow-up Review whose Comments are
the kept set (the framework treats critique's output AS the post-critique
list — it's the simplest contract).

`n_critique_rounds > 1` re-runs the critique on its own previous output,
useful for "self-improvement" loops where one pass isn't aggressive enough.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..reviewers import Reviewer
from ..types import CodebaseContext, Comment, Context

logger = logging.getLogger(__name__)


def _merge_usage(usages: list[dict]) -> dict:
    out: dict = {"input_tokens": 0, "output_tokens": 0, "model": "draft_critique"}
    for u in usages:
        for k in ("input_tokens", "output_tokens"):
            v = u.get(k)
            if isinstance(v, int):
                out[k] += v
    return out


@dataclass
class DraftCritiqueReviewer:
    """Two-pass reviewer: draft, then critique-and-revise."""

    name: str = "draft_critique"
    model: str = "draft_critique:composite"
    inner: Reviewer | None = None
    critique: Reviewer | None = None
    n_critique_rounds: int = 1
    drop_marker: str = "DROP"
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
            raise ValueError("DraftCritiqueReviewer requires an `inner` reviewer.")
        critique_rv = self.critique if self.critique is not None else self.inner

        # Draft pass
        draft, draft_usage = self.inner.review(
            context,
            codebase_context,
            extra_user_message=extra_user_message,
            run_context=run_context,
        )
        usages: list[dict] = [draft_usage]
        current = list(draft)

        for round_i in range(max(0, self.n_critique_rounds)):
            if not current:
                break
            critique_msg = self._build_critique_message(current, round_i + 1)
            kept_subset, critique_usage = critique_rv.review(
                context,
                codebase_context,
                extra_user_message=critique_msg,
                run_context=run_context,
            )
            usages.append(critique_usage)
            # The critique's returned Comments ARE the kept set (per spec).
            if not kept_subset:
                logger.info("draft_critique round %d dropped all draft comments", round_i + 1)
            current = list(kept_subset)

        return current, _merge_usage(usages)

    @staticmethod
    def _build_critique_message(draft: list[Comment], round_n: int) -> str:
        lines = [
            f"## Critique round {round_n}",
            "",
            "Below are the draft comments from the first pass. Re-evaluate each one:",
            "- KEEP comments that identify a real, actionable, in-hunk concern.",
            "- DROP comments that are speculative, vague, off-topic, or duplicates.",
            "- Return ONLY the comments worth keeping. Do not invent new ones in this pass.",
            "",
            "Draft comments:",
        ]
        for i, c in enumerate(draft, start=1):
            lines.append(f"{i}. [{c.severity.upper()}] {c.path}:{c.line} — {c.body[:200]}")
        return "\n".join(lines)
