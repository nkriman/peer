"""BugBenchmarkRunner: orchestrates a reviewer over a BugSample dataset.

For each bug:
  1. Build a synthetic PR URL (repo_url + "/commit/" + commit_sha when both
     are present; otherwise the raw bug_id) and invoke
     `reviewer.review(pr_url)`.
  2. For each peer Comment within proximity of any bug location, call
     `judge_bug_caught`. Any CAUGHT marks the bug caught.
  3. Record per-bug result + reason on miss.

Cost + latency tracking uses `peer.eval.pricing.estimate_cost` so the
report's numbers line up with eval reports.
"""

from __future__ import annotations

import hashlib
import logging
import time
from statistics import mean
from typing import Any, Protocol

from ..eval.pricing import estimate_cost
from ..eval.types import AgentConfig
from ..types import Comment, Review
from .baselines import PUBLISHED_BASELINES
from .judge import DEFAULT_JUDGE_MODEL, DEFAULT_PROXIMITY_LINES, judge_bug_caught
from .types import BenchmarkReport, BugBenchmarkResult, BugSample

logger = logging.getLogger(__name__)


class _PRReviewerLike(Protocol):
    """Anything with .review(pr_url) -> Review. Agent satisfies this."""

    def review(self, pr_url: str) -> Review: ...


def _infer_agent_config(reviewer: _PRReviewerLike) -> AgentConfig:
    model = getattr(reviewer, "model", None) or "unknown"
    system_prompt = getattr(reviewer, "system_prompt", None)
    prompt_hash: str | None = None
    if isinstance(system_prompt, str):
        prompt_hash = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:16]
    return AgentConfig(
        model=model,
        system_prompt_hash=prompt_hash,
        reviewer_class=type(reviewer).__name__,
    )


def _bug_target_url(bug: BugSample) -> str:
    """Where the reviewer should look. Prefer the PR if known, else build a
    commit URL from repo_url + commit_sha. Falls back to the bug_id when
    neither is set."""
    if bug.pr_url:
        return bug.pr_url
    if bug.repo_url and bug.commit_sha:
        sep = "/" if not bug.repo_url.endswith("/") else ""
        return f"{bug.repo_url}{sep}commit/{bug.commit_sha}"
    return bug.bug_id


class BugBenchmarkRunner:
    def __init__(
        self,
        reviewer: _PRReviewerLike,
        dataset: list[BugSample],
        judge_client: Any | None = None,
        judge_fn: Any = judge_bug_caught,
        judge_model: str = DEFAULT_JUDGE_MODEL,
        proximity: int = DEFAULT_PROXIMITY_LINES,
    ) -> None:
        self.reviewer = reviewer
        self.dataset = list(dataset)
        self.judge_client = judge_client
        # judge_fn is injectable so BDD scenarios can pass a fake without
        # constructing an Anthropic client.
        self.judge_fn = judge_fn
        self.judge_model = judge_model
        self.proximity = proximity

    def _bug_caught(self, bug: BugSample, comments: list[Comment]) -> tuple[bool, str, list[dict]]:
        """Returns (caught, reason, matching_comment_dicts)."""
        any_in_proximity = False
        matches: list[dict] = []
        for c in comments:
            try:
                caught = self.judge_fn(
                    bug,
                    c,
                    client=self.judge_client,
                    judge_model=self.judge_model,
                    proximity=self.proximity,
                )
            except Exception as e:
                logger.warning("judge raised on %s / %s: %s", bug.bug_id, c.path, e)
                continue
            if caught:
                matches.append({"path": c.path, "line": c.line, "body": c.body[:200]})
                return True, "caught", matches
            # Track proximity-only matches so we can give a meaningful miss reason.
            if c.path in {loc.path for loc in bug.bug_paths}:
                any_in_proximity = True
        if not matches and not any_in_proximity:
            return False, "no comments on bug's file(s)", matches
        return False, "comments on file but judge rejected", matches

    def run(self) -> BenchmarkReport:
        agent_config = _infer_agent_config(self.reviewer)
        per_bug: list[BugBenchmarkResult] = []
        latencies: list[float] = []
        costs: list[float] = []
        per_pr_counts: list[int] = []
        n_caught = 0
        n_total = len(self.dataset)

        for i, bug in enumerate(self.dataset, start=1):
            target = _bug_target_url(bug)
            logger.info("[bench] %d/%d %s", i, n_total, bug.bug_id)
            t0 = time.monotonic()
            try:
                review: Review = self.reviewer.review(target)
            except Exception as e:
                logger.warning("reviewer failed on %s: %s", bug.bug_id, e)
                per_bug.append(
                    BugBenchmarkResult(
                        bug_id=bug.bug_id,
                        caught=False,
                        reason=f"reviewer error: {e}",
                    )
                )
                continue
            latencies.append(time.monotonic() - t0)

            usage = review.usage or {}
            model = usage.get("model") or agent_config.model
            in_tok = int(usage.get("input_tokens", 0) or 0)
            out_tok = int(usage.get("output_tokens", 0) or 0)
            cost = estimate_cost(model, in_tok, out_tok)
            if cost is not None:
                costs.append(cost)

            per_pr_counts.append(len(review.comments))
            caught, reason, matching = self._bug_caught(bug, review.comments)
            if caught:
                n_caught += 1
            per_bug.append(
                BugBenchmarkResult(
                    bug_id=bug.bug_id,
                    caught=caught,
                    reason=reason,
                    matching_peer_comments=matching,
                )
            )

        detection_rate = (n_caught / n_total) if n_total else None
        comments_per_pr = mean(per_pr_counts) if per_pr_counts else None
        latency_p50 = sorted(latencies)[len(latencies) // 2] if latencies else None
        cost_total = sum(costs) if costs else None

        return BenchmarkReport(
            agent_config=agent_config,
            dataset_id="ad-hoc",
            dataset_size=n_total,
            n_bugs_total=n_total,
            n_bugs_caught=n_caught,
            n_bugs_skipped=0,
            detection_rate=detection_rate,
            comments_per_pr=comments_per_pr,
            cost_usd_total=cost_total,
            latency_p50_seconds=latency_p50,
            per_bug=per_bug,
            published_baselines=dict(PUBLISHED_BASELINES),
        )
