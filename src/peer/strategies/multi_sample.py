"""MultiSampleReviewer: independent K-pass + dedup union (multi-sample-v01).

Calls the inner reviewer K times and returns the deduplicated union of
all returned Comments. The caller is responsible for constructing the
inner reviewer with non-zero temperature so the K samples are actually
diverse — this strategy itself does not vary the model call.

Dedup key: (path, line, sha1(body[:N].strip().lower())).

Cost scales linearly with K; recall is expected to lift sublinearly per
the SWR-Bench / Codex-Verify literature on multi-sample code review.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from ..reviewers import Reviewer
from ..types import CodebaseContext, Comment, Context

logger = logging.getLogger(__name__)


def _comment_dedup_key(c: Comment, body_chars: int) -> tuple[str, int | None, str]:
    body_norm = (c.body or "").strip().lower()[:body_chars]
    body_hash = hashlib.sha1(body_norm.encode("utf-8")).hexdigest()
    return (c.path, c.line, body_hash)


def _merge_usage(usages: list[dict], inner_model: str) -> dict:
    out: dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_cost_usd": 0.0,
        "model": f"multi_sample:{inner_model}",
    }
    for u in usages:
        for k in ("input_tokens", "output_tokens"):
            v = u.get(k)
            if isinstance(v, int):
                out[k] += v
        c = u.get("total_cost_usd")
        if isinstance(c, (int, float)):
            out["total_cost_usd"] += float(c)
    return out


@dataclass
class MultiSampleReviewer:
    """Run inner reviewer K times; return deduplicated union of comments."""

    inner: Reviewer | None = None
    k: int = 5
    dedupe_path_line: bool = True
    dedupe_body_chars: int = 80
    name: str = "multi_sample"
    model: str = "multi_sample:composite"

    def __post_init__(self) -> None:
        if self.k < 1:
            raise ValueError(f"MultiSampleReviewer.k must be >= 1; got {self.k}")

    def review(
        self,
        context: Context,
        codebase_context: CodebaseContext | None = None,
        *,
        extra_user_message: str | None = None,
        run_context: object | None = None,
    ) -> tuple[list[Comment], dict]:
        if self.inner is None:
            raise ValueError("MultiSampleReviewer requires an `inner` reviewer.")

        # K=1: short-circuit, no dedup overhead.
        if self.k == 1:
            return self.inner.review(
                context,
                codebase_context,
                extra_user_message=extra_user_message,
                run_context=run_context,
            )

        all_comments: list[Comment] = []
        all_usages: list[dict] = []
        inner_model = "unknown"

        for i in range(self.k):
            comments, usage = self.inner.review(
                context,
                codebase_context,
                extra_user_message=extra_user_message,
                run_context=run_context,
            )
            all_comments.extend(comments)
            all_usages.append(usage)
            m = usage.get("model")
            if isinstance(m, str):
                inner_model = m
            logger.debug(
                "multi_sample sample %d/%d returned %d comments", i + 1, self.k, len(comments)
            )

        # Dedup preserving first occurrence.
        seen: set[tuple[str, int | None, str]] = set()
        deduped: list[Comment] = []
        for c in all_comments:
            key = _comment_dedup_key(c, self.dedupe_body_chars)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(c)

        logger.info(
            "multi_sample k=%d: %d raw comments → %d after dedup",
            self.k,
            len(all_comments),
            len(deduped),
        )
        return deduped, _merge_usage(all_usages, inner_model)
