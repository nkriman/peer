"""EvalRunner: composes a Reviewer-like + dataset + metrics into one run.

v0.1 surface decision: accept anything with a `.review(pr_url) -> Review`
method (structurally an Agent). The bare `Reviewer` Protocol from
`peer.reviewers` takes (Context, CodebaseContext), which requires a Context
to be gathered first. Wrapping that here would duplicate Agent's
orchestration; users wanting custom reviewer plumbing wrap their reviewer
in an Agent-like adapter. See design.md Decision 1.
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from statistics import mean, median
from typing import Protocol

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
            ]
        self.metrics = metrics
        self.dataset_path = dataset_path or "in-memory"
        # One Anthropic client shared with metrics so judge calls reuse the
        # same connection pool / api key. Lazy-init so EvalRunner can be
        # constructed without ANTHROPIC_API_KEY (e.g., in unit tests).
        self._client: anthropic.Anthropic | None = None

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def run(self) -> EvalReport:
        agent_config = _infer_agent_config(self.reviewer)
        per_sample: list[EvalSampleResult] = []
        sample_costs: list[float] = []
        sample_latencies: list[float] = []
        any_cost_unavailable = False
        unavailable_reason: str | None = None

        n = len(self.dataset)
        for i, sample in enumerate(self.dataset, 1):
            print(f"[eval] {i}/{n} {sample.pr_url}", flush=True)
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
                per_sample.append(sample_result)
                continue
            latency = time.monotonic() - t0
            sample_result.latency_seconds = latency
            sample_latencies.append(latency)

            # Cost
            usage = review.usage or {}
            model = usage.get("model") or agent_config.model
            in_tok = int(usage.get("input_tokens", 0) or 0)
            out_tok = int(usage.get("output_tokens", 0) or 0)
            cost = estimate_cost(model, in_tok, out_tok)
            sample_result.cost_usd = cost
            if cost is None:
                any_cost_unavailable = True
                unavailable_reason = cost_unavailable_reason(model)
            else:
                sample_costs.append(cost)

            # Review summary
            sev_dist: dict[str, int] = {}
            for c in review.comments:
                sev_dist[c.severity] = sev_dist.get(c.severity, 0) + 1
            sample_result.review_summary = {
                "n_comments": len(review.comments),
                "severity_distribution": sev_dist,
                "usage": usage,
            }

            # Run metrics
            for metric in self.metrics:
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

            per_sample.append(sample_result)

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
