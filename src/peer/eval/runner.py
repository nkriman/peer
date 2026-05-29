"""EvalRunner: composes a Reviewer-like + dataset + metrics into one run.

v0.1 surface decision: accept anything with a `.review(pr_url) -> Review`
method (structurally an Agent). The bare `Reviewer` Protocol from
`peer.reviewers` takes (Context, CodebaseContext), which requires a Context
to be gathered first. Wrapping that here would duplicate Agent's
orchestration; users wanting custom reviewer plumbing wrap their reviewer
in an Agent-like adapter. See design.md Decision 1.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone
from statistics import mean, median
from typing import Any, Protocol

import anthropic

from ..agent import Agent
from ..dataset.types import GoldSample
from ..types import Review
from .metrics import (
    CommentsPerPR,
    DetectionRate,
    EvalMetric,
    MeanPerPRRecall,
    NoveltyRate,
    PrecisionPerSeverity,
    SeverityCalibration,
    SuggestionRate,
)
from .pricing import cost_unavailable_reason, estimate_cost
from .types import (
    AgentConfig,
    EvalReport,
    EvalSampleResult,
    EvalSummary,
    MetricResult,
)


def _aggregate_metrics(
    metrics: list[EvalMetric],
    per_sample: list,
) -> tuple[dict[str, float | None], dict[str, dict]]:
    """Aggregate per-sample MetricResults into report-level numbers + details.

    Per-metric special-casing where the metric's semantics call for it:
    - detection_rate: sum-of-sums (Macroscope-style headline)
    - comments_per_pr: mean + median + min + max
    - precision_per_severity: per-tier sum-of-sums
    - others: mean of non-None per-sample values
    """
    values: dict[str, float | None] = {}
    details: dict[str, dict] = {}
    for metric in metrics:
        name = metric.name
        per_sample_mr = [r.metrics[name] for r in per_sample if name in r.metrics]
        if name == "detection_rate":
            total_matches = 0
            total_gold = 0
            for mr in per_sample_mr:
                d = mr.per_sample_detail or {}
                total_matches += d.get("matched_count", 0)
                total_gold += d.get("total_gold", 0)
            values[name] = (total_matches / total_gold) if total_gold > 0 else None
            details[name] = {
                "total_matches": total_matches,
                "total_gold": total_gold,
                "n_samples_with_gold": sum(
                    1
                    for mr in per_sample_mr
                    if (mr.per_sample_detail or {}).get("total_gold", 0) > 0
                ),
            }
        elif name == "comments_per_pr":
            counts = [(mr.per_sample_detail or {}).get("n_comments", 0) for mr in per_sample_mr]
            if counts:
                values[name] = mean(counts)
                details[name] = {
                    "mean": mean(counts),
                    "median": median(counts),
                    "min": min(counts),
                    "max": max(counts),
                    "n_samples": len(counts),
                }
            else:
                values[name] = None
                details[name] = {"n_samples": 0}
        elif name == "precision_per_severity":
            per_tier_totals: dict[str, dict[str, int]] = {
                sev: {"matched": 0, "total": 0} for sev in ("critical", "important", "minor", "nit")
            }
            for mr in per_sample_mr:
                d = mr.per_sample_detail or {}
                for sev, counts in d.items():
                    if isinstance(counts, dict):
                        per_tier_totals[sev]["matched"] += counts.get("matched", 0)
                        per_tier_totals[sev]["total"] += counts.get("total", 0)
            per_tier_agg: dict[str, dict] = {}
            for sev, tier_counts in per_tier_totals.items():
                if tier_counts["total"] == 0:
                    continue
                per_tier_agg[sev] = {
                    "precision": tier_counts["matched"] / tier_counts["total"],
                    "n": tier_counts["total"],
                    "matched": tier_counts["matched"],
                }
            values[name] = None  # no single number; consult details
            details[name] = per_tier_agg
        else:
            vals = [mr.value for mr in per_sample_mr if mr.value is not None]
            values[name] = sum(vals) / len(vals) if vals else None
            details[name] = {
                "n_samples_with_value": len(vals),
                "n_samples_skipped": len(per_sample) - len(vals),
            }
    return values, details


logger = logging.getLogger(__name__)


class _ReviewerLike(Protocol):
    """Anything with .review(pr_url) -> Review. Agent satisfies this."""

    def review(self, pr_url: str) -> Review: ...


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def _infer_agent_config(reviewer: _ReviewerLike) -> AgentConfig:
    """Extract model + prompt hash from an Agent-shaped object; fall back to
    sensible placeholders otherwise."""
    model = getattr(reviewer, "model", None) or "unknown"
    system_prompt = getattr(reviewer, "system_prompt", None)
    prompt_hash: str | None = None
    if isinstance(system_prompt, str):
        prompt_hash = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:16]
    cls_name = type(reviewer).__name__
    return AgentConfig(
        model=model,
        system_prompt_hash=prompt_hash,
        reviewer_class=cls_name,
    )


class EvalRunner:
    def __init__(
        self,
        reviewer: _ReviewerLike,
        dataset: list[GoldSample],
        metrics: list[EvalMetric] | None = None,
        dataset_path: str | None = None,
        concurrency: int = 5,
        judge_client_override: Any | None = None,
        per_sample_timeout_seconds: float = 300.0,
    ) -> None:
        self.reviewer = reviewer
        self.dataset = list(dataset)
        if metrics is None:
            metrics = [
                DetectionRate(),
                CommentsPerPR(),
                PrecisionPerSeverity(),
                MeanPerPRRecall(),
                NoveltyRate(),
                SeverityCalibration(),
                SuggestionRate(),
            ]
        self.metrics = metrics
        self.dataset_path = dataset_path or "in-memory"
        # Bounded concurrency for run_async. <=1 forces strict sequential.
        self.concurrency = max(1, int(concurrency))
        # Per-sample wall-clock cap (peer-2z2). Without this, a stuck judge
        # subprocess inside the to_thread worker pins the asyncio.gather
        # forever: the gather has no view into thread health, the work
        # already returned 0% CPU because the subprocess.run is blocked
        # waiting for stdout that never arrives, and SIGINT doesn't reach
        # the thread. wait_for at least frees the coroutine; the leaked
        # thread is bounded and exits on interpreter shutdown.
        if per_sample_timeout_seconds <= 0:
            raise ValueError(
                f"per_sample_timeout_seconds must be > 0; got {per_sample_timeout_seconds}"
            )
        self.per_sample_timeout_seconds = float(per_sample_timeout_seconds)
        # One Anthropic client shared with metrics so judge calls reuse the
        # same connection pool / api key. Lazy-init so EvalRunner can be
        # constructed without ANTHROPIC_API_KEY (e.g., in unit tests).
        self._client: anthropic.Anthropic | None = None
        # eval-cross-judge-v01: when set, _get_client returns this directly
        # (skipping make_client). Used by CrossJudgeRunner to swap judges.
        self._judge_client_override: Any | None = judge_client_override

    def _get_client(self) -> Any:
        # Return type widened to Any because the override may be a
        # CrossJudgeRunner pinned-model shim (not strictly anthropic.Anthropic).
        if self._judge_client_override is not None:
            return self._judge_client_override
        if self._client is None:
            from ..claude_code_client import make_client

            self._client = make_client()
        return self._client

    def _eval_one_sample(
        self,
        sample: GoldSample,
        agent_config: AgentConfig,
    ) -> tuple[EvalSampleResult, float | None, float | None, str | None]:
        """Run reviewer + all metrics on one sample.

        Returns (sample_result, sample_cost_or_None, sample_latency_or_None,
        unavailable_reason). Both None values denote a sample where the
        reviewer raised.
        """
        sample_result = EvalSampleResult(pr_url=sample.pr_url)
        t0 = time.monotonic()
        review: Review | None = None
        try:
            review = self.reviewer.review(sample.pr_url)
        except Exception as exc:
            latency = time.monotonic() - t0
            logger.warning("Reviewer failed on %s: %s", sample.pr_url, exc)
            sample_result.error = str(exc)
            sample_result.latency_seconds = latency
            return sample_result, None, None, None
        latency = time.monotonic() - t0
        sample_result.latency_seconds = latency

        # Cost
        usage = review.usage or {}
        model = usage.get("model") or agent_config.model
        in_tok = int(usage.get("input_tokens", 0) or 0)
        out_tok = int(usage.get("output_tokens", 0) or 0)
        cost = estimate_cost(model, in_tok, out_tok)
        sample_result.cost_usd = cost
        unavail = cost_unavailable_reason(model) if cost is None else None

        # Review summary
        sev_dist: dict[str, int] = {}
        for c in review.comments:
            sev_dist[c.severity] = sev_dist.get(c.severity, 0) + 1
        sample_result.review_summary = {
            "n_comments": len(review.comments),
            "severity_distribution": sev_dist,
            "usage": usage,
        }

        # Merge dataset-wide + case-specific metrics; case-specific wins on
        # name collision (eval-v02 design — sample's per-PR rubric overrides).
        case_specific = list(getattr(sample, "evaluators", []) or [])
        merged_metrics: dict[str, EvalMetric] = {}
        for m in self.metrics:
            merged_metrics[getattr(m, "name", type(m).__name__)] = m
        for m in case_specific:
            mname = getattr(m, "name", type(m).__name__)
            if mname in merged_metrics:
                logger.debug(
                    "case-specific evaluator %r overrides dataset-wide on %s",
                    mname,
                    sample.pr_url,
                )
            merged_metrics[mname] = m

        for metric in merged_metrics.values():
            try:
                mr = metric.score(sample, review, client=self._get_client())
            except Exception as exc:
                logger.warning(
                    "Metric %s failed on %s: %s",
                    getattr(metric, "name", type(metric).__name__),
                    sample.pr_url,
                    exc,
                )
                mr = MetricResult(
                    name=getattr(metric, "name", type(metric).__name__),
                    value=None,
                    notes=f"metric raised: {exc}",
                )
            sample_result.metrics[mr.name] = mr

        return sample_result, cost, latency, unavail

    def run(self) -> EvalReport:
        """Synchronous entry point. Runs `run_async()` under `asyncio.run`."""
        return asyncio.run(self.run_async())

    async def run_async(self, concurrency: int | None = None) -> EvalReport:
        """Async entry: per-sample work runs under `asyncio.to_thread` with
        a `Semaphore(concurrency)`. concurrency=None uses self.concurrency."""
        agent_config = _infer_agent_config(self.reviewer)
        per_sample: list[EvalSampleResult] = []
        sample_costs: list[float] = []
        sample_latencies: list[float] = []
        any_cost_unavailable = False
        unavailable_reason: str | None = None

        n = len(self.dataset)
        eff_concurrency = max(1, int(concurrency if concurrency is not None else self.concurrency))
        sem = asyncio.Semaphore(eff_concurrency)

        async def _one(
            idx: int, sample: GoldSample
        ) -> tuple[int, EvalSampleResult, float | None, float | None, str | None]:
            async with sem:
                print(f"[eval] {idx}/{n} {sample.pr_url}", flush=True)
                # Sync reviewer + sync metrics — defer to a thread so the
                # event loop can interleave samples up to `eff_concurrency`.
                t_start = time.monotonic()
                try:
                    res, cost, latency, unavail = await asyncio.wait_for(
                        asyncio.to_thread(self._eval_one_sample, sample, agent_config),
                        timeout=self.per_sample_timeout_seconds,
                    )
                except (TimeoutError, asyncio.TimeoutError):
                    # peer-2z2: a stuck worker thread (typically a hanging
                    # judge subprocess) must not be allowed to block the
                    # gather. Convert the hang into a recorded error so the
                    # phase still completes.
                    elapsed = time.monotonic() - t_start
                    logger.warning(
                        "Per-sample timeout (%.1fs > %.1fs) on %s — marking errored",
                        elapsed,
                        self.per_sample_timeout_seconds,
                        sample.pr_url,
                    )
                    res = EvalSampleResult(
                        pr_url=sample.pr_url,
                        error=f"per-sample timeout ({elapsed:.1f}s > "
                        f"{self.per_sample_timeout_seconds:.1f}s)",
                        latency_seconds=elapsed,
                    )
                    cost, latency, unavail = None, None, None
                return idx, res, cost, latency, unavail

        # return_exceptions=True: belt-and-suspenders. _one shouldn't ever
        # raise (everything inside is caught), but if a future refactor
        # breaks that, surface the exception in results rather than tank
        # the whole gather.
        raw_results = await asyncio.gather(
            *(_one(i + 1, s) for i, s in enumerate(self.dataset)),
            return_exceptions=True,
        )
        results: list[tuple[int, EvalSampleResult, float | None, float | None, str | None]] = []
        for idx_or_exc, raw in enumerate(raw_results):
            if isinstance(raw, BaseException):
                logger.error("Per-sample coroutine raised unexpectedly: %s", raw)
                err_idx = idx_or_exc + 1
                err_sample = self.dataset[idx_or_exc]
                results.append(
                    (
                        err_idx,
                        EvalSampleResult(
                            pr_url=err_sample.pr_url, error=f"coroutine raised: {raw!r}"
                        ),
                        None,
                        None,
                        None,
                    )
                )
            else:
                results.append(raw)
        # Preserve input order regardless of completion order.
        results_sorted = sorted(results, key=lambda r: r[0])
        for _idx, sample_result, cost, latency, unavail in results_sorted:
            per_sample.append(sample_result)
            if latency is not None:
                sample_latencies.append(latency)
            if cost is not None:
                sample_costs.append(cost)
            if cost is None and not sample_result.error:
                any_cost_unavailable = True
                unavailable_reason = unavail or unavailable_reason

        # Aggregate. Per-metric aggregation honors each metric's semantics:
        # - detection_rate: sum-of-sums (Macroscope-style; the headline number)
        # - comments_per_pr: mean + median + min + max
        # - precision_per_severity: sum-of-sums per tier
        # - mean_per_pr_recall / novelty_rate / severity_calibration: mean
        #   of per-sample values (the legacy aggregator).
        metric_values, metric_details = _aggregate_metrics(self.metrics, per_sample)

        n_failed = sum(1 for r in per_sample if r.error is not None)
        n_succeeded = len(per_sample) - n_failed

        # When at least one sample had pricing, report the partial total
        # (clearly flagged via cost_unavailable_reason so users see it's
        # incomplete). Report None only if NO sample had pricing.
        cost_total: float | None = sum(sample_costs) if sample_costs else None
        summary = EvalSummary(
            metric_values=metric_values,
            metric_details=metric_details,
            n_samples_total=len(per_sample),
            n_samples_succeeded=n_succeeded,
            n_samples_failed=n_failed,
            cost_usd_total=cost_total,
            cost_usd_p50=_percentile(sample_costs, 50),
            cost_usd_p95=_percentile(sample_costs, 95),
            cost_unavailable_reason=(unavailable_reason if any_cost_unavailable else None),
            latency_seconds_p50=_percentile(sample_latencies, 50),
            latency_seconds_p95=_percentile(sample_latencies, 95),
        )

        _peer_version: str | None
        try:
            from .. import __version__ as _peer_version
        except Exception:
            _peer_version = None

        return EvalReport(
            agent_config=agent_config,
            dataset_path=self.dataset_path,
            dataset_size=len(self.dataset),
            summary=summary,
            per_sample=per_sample,
            peer_version=_peer_version,
            timestamp=datetime.now(tz=timezone.utc),
        )


__all__ = ["Agent", "EvalRunner"]
