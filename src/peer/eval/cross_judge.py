"""Cross-judge variance utility (eval-cross-judge-v01).

Re-judges cached reviews against N different judge models and reports
per-metric variance bands. The reviewer runs ONCE per sample; only the
metric-scoring phase fans out to N judges. This is cheap and gives us
honest error bars on every detection_rate number we'd otherwise publish
as a point estimate.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..dataset.types import GoldSample
from ..types import Review
from .runner import EvalRunner
from .types import EvalReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Report models
# ---------------------------------------------------------------------------


class MetricBand(BaseModel):
    """min / max / median / range of a single metric across N judges."""

    model_config = ConfigDict(extra="forbid")

    min: float | None = None
    max: float | None = None
    median: float | None = None
    range: float | None = None
    n_judges_included: int = 0


class CrossJudgeReport(BaseModel):
    """Output of CrossJudgeRunner: per-judge EvalReports + variance bands."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    judge_models: list[str]
    per_judge: dict[str, EvalReport] = Field(default_factory=dict)
    metric_bands: dict[str, MetricBand] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Variance computation
# ---------------------------------------------------------------------------


def compute_variance_bands(reports: list[EvalReport]) -> dict[str, MetricBand]:
    """For each metric name appearing in any report, compute the band across
    the reports' per-judge values.

    None values are excluded (judge couldn't compute it for some reason).
    `n_judges_included` records the count of non-None values per metric.
    """
    # Collect metric names appearing in any report.
    names: set[str] = set()
    for r in reports:
        names.update((r.summary.metric_values or {}).keys())

    bands: dict[str, MetricBand] = {}
    for name in names:
        values: list[float] = []
        for r in reports:
            v = (r.summary.metric_values or {}).get(name)
            if isinstance(v, (int, float)):
                values.append(float(v))
        if not values:
            bands[name] = MetricBand(n_judges_included=0)
            continue
        vmin = min(values)
        vmax = max(values)
        bands[name] = MetricBand(
            min=vmin,
            max=vmax,
            median=statistics.median(values),
            range=vmax - vmin,
            n_judges_included=len(values),
        )
    return bands


# ---------------------------------------------------------------------------
# CrossJudgeRunner
# ---------------------------------------------------------------------------


def _judge_client_for(model: str) -> Any:
    """Build a client pinned to a specific judge model.

    Routes through `peer.claude_code_client.make_client()` so when
    `PEER_USE_CLAUDE_CODE=1` the judge calls go through the CLI (free under
    subscription). Wraps the resulting client so .messages.create overrides
    the model kwarg with the pinned judge model — metrics that pass their
    own `model=` to the SDK get re-routed transparently.
    """
    from ..claude_code_client import make_client

    class _PinnedModelClient:
        def __init__(self, base: Any, model: str) -> None:
            self._base = base
            self._pinned_model = model
            self.messages = _PinnedMessages(base.messages, model)

    class _PinnedMessages:
        def __init__(self, base_messages: Any, model: str) -> None:
            self._base = base_messages
            self._pinned_model = model

        def create(self, **kwargs: Any) -> Any:
            kwargs["model"] = self._pinned_model
            return self._base.create(**kwargs)

    return _PinnedModelClient(make_client(), model)


class _CachedReviewer:
    """Reviewer wrapper that returns pre-computed Reviews from a cache.

    Used by CrossJudgeRunner so the reviewer call is paid for ONCE across
    all judge passes.
    """

    def __init__(self, cache: dict[str, Review], fallback_model: str = "cached") -> None:
        self._cache = cache
        self.model = fallback_model

    def review(self, pr_url: str) -> Review:
        if pr_url not in self._cache:
            raise KeyError(f"No cached review for {pr_url!r}")
        return self._cache[pr_url]


class CrossJudgeRunner:
    """Re-judge cached reviews against N judge models. See spec."""

    def __init__(
        self,
        reviewer: Any,
        dataset: list[GoldSample],
        judge_models: list[str],
        concurrency: int = 5,
    ) -> None:
        if not judge_models:
            raise ValueError("judge_models must be non-empty")
        self.reviewer = reviewer
        self.dataset = list(dataset)
        self.judge_models = list(judge_models)
        self.concurrency = max(1, int(concurrency))

    def _build_review_cache(self) -> dict[str, Review]:
        """Phase 1: run the reviewer once per sample, cache Reviews."""
        cache: dict[str, Review] = {}
        for sample in self.dataset:
            try:
                cache[sample.pr_url] = self.reviewer.review(sample.pr_url)
            except Exception as e:
                logger.warning("reviewer failed on %s during cache phase: %s", sample.pr_url, e)
                # Don't cache; the per-judge EvalRunner will register an error row.
        return cache

    def run(self) -> CrossJudgeReport:
        """Synchronous entry point. Returns a CrossJudgeReport."""
        return asyncio.run(self.run_async())

    async def run_async(self) -> CrossJudgeReport:
        """Async entry point: build cache once, then fan out per judge."""
        cache = self._build_review_cache()
        cached_reviewer = _CachedReviewer(cache)

        per_judge: dict[str, EvalReport] = {}
        for judge_model in self.judge_models:
            judge_client = _judge_client_for(judge_model)
            runner = EvalRunner(
                reviewer=cached_reviewer,
                dataset=self.dataset,
                concurrency=self.concurrency,
                judge_client_override=judge_client,
            )
            report = await runner.run_async()
            per_judge[judge_model] = report

        bands = compute_variance_bands(list(per_judge.values()))
        return CrossJudgeReport(
            judge_models=self.judge_models,
            per_judge=per_judge,
            metric_bands=bands,
        )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_cross_judge_summary(report: CrossJudgeReport) -> str:
    """Markdown summary of cross-judge variance. Flags metrics where
    `max / min >= 2.0` as ⚠️ HIGH VARIANCE.
    """
    lines: list[str] = []
    lines.append("# Cross-judge variance report")
    lines.append("")
    lines.append(f"Judges: {', '.join(report.judge_models)}")
    lines.append("")
    lines.append("## Variance bands")
    lines.append("")
    lines.append("| metric | min | median | max | range | flag |")
    lines.append("|---|---:|---:|---:|---:|:---:|")
    for name in sorted(report.metric_bands):
        band = report.metric_bands[name]
        flag = ""
        if band.min is not None and band.max is not None and band.min > 0:
            ratio = band.max / band.min
            if ratio >= 2.0:
                flag = "⚠️ HIGH VARIANCE"
        lines.append(
            f"| {name} | "
            f"{_fmt(band.min)} | "
            f"{_fmt(band.median)} | "
            f"{_fmt(band.max)} | "
            f"{_fmt(band.range)} | "
            f"{flag} |"
        )
    lines.append("")
    return "\n".join(lines)


def _fmt(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:.4f}"
