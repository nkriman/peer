"""Default eval metrics: DetectionRate, CommentsPerPR, PrecisionPerSeverity,
MeanPerPRRecall (formerly DefectRecall — see deprecation note), NoveltyRate,
SeverityCalibration.

Each metric implements the EvalMetric Protocol (structural typing — no
inheritance required for user-supplied metrics).

DetectionRate is the headline recall metric (sum-of-sums). MeanPerPRRecall is
the legacy mean-of-rates metric — kept for back-compat but Simpson's-paradoxes
when gold counts vary across samples (see docstring + design.md for
eval-metrics-v01).
"""

from __future__ import annotations

import warnings
from typing import Protocol

import anthropic

from ..dataset.types import GoldDefect, GoldSample
from ..types import Comment, Review, Severity
from .judging import judge_match
from .types import MetricResult

_SEVERITY_ORDER: dict[Severity, int] = {
    "critical": 0,
    "important": 1,
    "minor": 2,
    "nit": 3,
}

_LINE_PROXIMITY = 5


def _severity_to_int(sev: Severity) -> int:
    return _SEVERITY_ORDER[sev]


def _gold_lines(defect: GoldDefect) -> tuple[int, int]:
    """Return (lo, hi) inclusive line bounds for a gold defect."""
    if defect.line_range is not None:
        return defect.line_range
    if defect.line is not None:
        return (defect.line, defect.line)
    return (0, 0)


def _line_close(peer_line: int | None, defect: GoldDefect) -> bool:
    if peer_line is None:
        # If the gold defect has no line either, treat as compatible.
        return defect.line is None and defect.line_range is None
    lo, hi = _gold_lines(defect)
    if lo == 0 and hi == 0:
        return True
    if peer_line < lo - _LINE_PROXIMITY:
        return False
    return not peer_line > hi + _LINE_PROXIMITY


def _match_peer_to_gold(
    peer_comments: list[Comment],
    gold_defects: list[GoldDefect],
    client: anthropic.Anthropic | None = None,
) -> tuple[list[tuple[int, int]], set[int], set[int]]:
    """Greedy match peer comments to gold defects.

    Returns (matched_pairs, matched_peer_indices, matched_gold_indices).
    matched_pairs is a list of (peer_idx, gold_idx) tuples.
    """
    matched_pairs: list[tuple[int, int]] = []
    matched_peer: set[int] = set()
    matched_gold: set[int] = set()
    for pi, p in enumerate(peer_comments):
        for gi, g in enumerate(gold_defects):
            if gi in matched_gold:
                continue
            if p.path != g.path:
                continue
            if not _line_close(p.line, g):
                continue
            if judge_match(p, g, client=client):
                matched_pairs.append((pi, gi))
                matched_peer.add(pi)
                matched_gold.add(gi)
                break
    return matched_pairs, matched_peer, matched_gold


class EvalMetric(Protocol):
    """Structural Protocol — any class with `name` and `score` satisfies it."""

    name: str

    def score(
        self,
        sample: GoldSample,
        review: Review,
        client: anthropic.Anthropic | None = None,
    ) -> MetricResult: ...


class MeanPerPRRecall:
    """Per-sample recall (matches / gold) averaged across samples.

    WARNING (Simpson's paradox): when gold counts vary widely across samples,
    this mean is misleading. A PR with 23 gold defects (1 match = 4.3% recall)
    is weighted equally with a PR with 2 gold defects (2 matches = 100% recall).
    Per the v0.1 reference dataset's eval-metrics-v01 design, prefer
    `DetectionRate` (sum-of-sums) as the headline number; consult this metric
    only when you specifically want a per-PR average.

    Formerly named `DefectRecall`. The old name is deprecated.
    """

    name = "mean_per_pr_recall"

    def score(
        self,
        sample: GoldSample,
        review: Review,
        client: anthropic.Anthropic | None = None,
    ) -> MetricResult:
        gold = sample.gold_defects
        if not gold:
            return MetricResult(
                name=self.name,
                value=None,
                notes="no gold defects on this sample",
                per_sample_detail={"matched_pairs": [], "unmatched_gold": []},
            )
        matched_pairs, _, matched_gold = _match_peer_to_gold(review.comments, gold, client=client)

        # Per-severity hit/miss counts
        per_severity: dict[str, dict[str, int]] = {}
        for sev in ("critical", "important", "minor", "nit"):
            per_severity[sev] = {"hit": 0, "miss": 0, "total": 0}
        for gi, g in enumerate(gold):
            sev = g.severity
            per_severity[sev]["total"] += 1
            if gi in matched_gold:
                per_severity[sev]["hit"] += 1
            else:
                per_severity[sev]["miss"] += 1

        pairs_detail = [
            {
                "peer": review.comments[pi].model_dump(),
                "gold": gold[gi].model_dump(mode="json"),
            }
            for pi, gi in matched_pairs
        ]
        unmatched_gold = [
            g.model_dump(mode="json") for gi, g in enumerate(gold) if gi not in matched_gold
        ]

        value = len(matched_gold) / len(gold)
        return MetricResult(
            name=self.name,
            value=value,
            per_sample_detail={
                "matched_count": len(matched_gold),
                "total_gold": len(gold),
                "per_severity": per_severity,
                "matched_pairs": pairs_detail,
                "unmatched_gold": unmatched_gold,
            },
        )


class NoveltyRate:
    """Fraction of peer comments that did NOT match any gold defect.

    Signal, not verdict — novel comments may be real defects gold missed.
    Always reported alongside DefectRecall. NOT a false-positive rate.
    """

    name = "novelty_rate"

    def score(
        self,
        sample: GoldSample,
        review: Review,
        client: anthropic.Anthropic | None = None,
    ) -> MetricResult:
        peer = review.comments
        if not peer:
            return MetricResult(
                name=self.name,
                value=None,
                notes="reviewer produced 0 comments on this sample",
                per_sample_detail={"unmatched_peer": [], "peer_total": 0},
            )
        _, matched_peer, _ = _match_peer_to_gold(peer, sample.gold_defects, client=client)
        unmatched = [c for i, c in enumerate(peer) if i not in matched_peer]
        value = len(unmatched) / len(peer)
        return MetricResult(
            name=self.name,
            value=value,
            per_sample_detail={
                "unmatched_peer": [c.model_dump() for c in unmatched],
                "peer_total": len(peer),
                "peer_unmatched_count": len(unmatched),
            },
        )


class SeverityCalibration:
    """Mean signed delta between peer and gold severity on matched pairs.

    Ordering: critical=0, important=1, minor=2, nit=3.
    Positive delta = peer rated LESS severe than gold (higher ordinal).
    """

    name = "severity_calibration"

    def score(
        self,
        sample: GoldSample,
        review: Review,
        client: anthropic.Anthropic | None = None,
    ) -> MetricResult:
        gold = sample.gold_defects
        matched_pairs, _, _ = _match_peer_to_gold(review.comments, gold, client=client)
        if not matched_pairs:
            return MetricResult(
                name=self.name,
                value=None,
                notes="no matched pairs to calibrate against",
                per_sample_detail={"pairs": [], "confusion": {}},
            )

        deltas: list[int] = []
        pair_details: list[dict] = []
        # 4x4 confusion: (gold_sev, peer_sev) -> count
        confusion: dict[str, dict[str, int]] = {}
        for sev in ("critical", "important", "minor", "nit"):
            confusion[sev] = {
                "critical": 0,
                "important": 0,
                "minor": 0,
                "nit": 0,
            }
        for pi, gi in matched_pairs:
            peer_sev = review.comments[pi].severity
            gold_sev = gold[gi].severity
            delta = _severity_to_int(peer_sev) - _severity_to_int(gold_sev)
            deltas.append(delta)
            confusion[gold_sev][peer_sev] += 1
            pair_details.append(
                {
                    "peer_severity": peer_sev,
                    "gold_severity": gold_sev,
                    "delta": delta,
                    "path": review.comments[pi].path,
                    "line": review.comments[pi].line,
                }
            )

        value = sum(deltas) / len(deltas)
        return MetricResult(
            name=self.name,
            value=value,
            per_sample_detail={
                "pairs": pair_details,
                "confusion": confusion,
                "n_pairs": len(deltas),
            },
        )


# ---------------------------------------------------------------------------
# New metrics (eval-metrics-v01)
# ---------------------------------------------------------------------------


class DetectionRate:
    """Sum-of-sums recall across all samples: total matches / total gold.

    This is the industry-standard headline metric (matches Macroscope's
    "detection rate", CodeRabbit's reported numbers, etc.). Use this when
    comparing peer's reviewer to published baselines.

    Per-sample MetricResult.value is the per-sample rate (matches/gold or
    None when gold is empty). EvalRunner's aggregator then sums numerators
    and denominators across all samples for the report-level number, NOT a
    mean of the per-sample values.
    """

    name = "detection_rate"

    def score(
        self,
        sample: GoldSample,
        review: Review,
        client: anthropic.Anthropic | None = None,
    ) -> MetricResult:
        gold = sample.gold_defects
        if not gold:
            return MetricResult(
                name=self.name,
                value=None,
                notes="no gold defects on this sample",
                per_sample_detail={"matched_count": 0, "total_gold": 0},
            )
        _, _, matched_gold = _match_peer_to_gold(review.comments, gold, client=client)
        value = len(matched_gold) / len(gold)
        return MetricResult(
            name=self.name,
            value=value,
            per_sample_detail={
                "matched_count": len(matched_gold),
                "total_gold": len(gold),
            },
        )


class CommentsPerPR:
    """Count of peer comments per sample. Industry-standard noise indicator.

    Per-sample MetricResult.value is the comment count. Aggregator computes
    mean + median + min + max from per-sample values.
    """

    name = "comments_per_pr"

    def score(
        self,
        sample: GoldSample,
        review: Review,
        client: anthropic.Anthropic | None = None,
    ) -> MetricResult:
        n = len(review.comments)
        return MetricResult(
            name=self.name,
            value=float(n),
            per_sample_detail={"n_comments": n},
        )


class PrecisionPerSeverity:
    """For each severity tier, fraction of peer comments at that tier that
    matched a gold defect. Validates whether the severity rubric is meaningful
    (e.g., 'critical' should be ~100% precise — see Sentry Seer pattern).

    Per-sample MetricResult.value is None (no single number); per_sample_detail
    is a dict keyed by severity with {precision, n}. Aggregator does sum-of-sums
    per tier (skipping tiers where n==0).
    """

    name = "precision_per_severity"

    def score(
        self,
        sample: GoldSample,
        review: Review,
        client: anthropic.Anthropic | None = None,
    ) -> MetricResult:
        peer = review.comments
        if not peer:
            return MetricResult(
                name=self.name,
                value=None,
                notes="reviewer produced 0 comments on this sample",
                per_sample_detail={},
            )
        _, matched_peer, _ = _match_peer_to_gold(peer, sample.gold_defects, client=client)
        per_tier: dict[str, dict[str, int]] = {}
        for sev in ("critical", "important", "minor", "nit"):
            per_tier[sev] = {"matched": 0, "total": 0}
        for pi, p in enumerate(peer):
            per_tier[p.severity]["total"] += 1
            if pi in matched_peer:
                per_tier[p.severity]["matched"] += 1
        out: dict[str, dict] = {}
        for sev, counts in per_tier.items():
            if counts["total"] == 0:
                continue
            out[sev] = {
                "precision": counts["matched"] / counts["total"],
                "n": counts["total"],
                "matched": counts["matched"],
            }
        return MetricResult(
            name=self.name,
            value=None,
            per_sample_detail=out,
        )


def _build_defect_recall_alias():
    """Construct a DefectRecall class that subclasses MeanPerPRRecall, keeps
    `name = "defect_recall"` for back-compat, and emits a DeprecationWarning
    on instantiation. The old name was used in eval/runner default until
    eval-metrics-v01.
    """

    class DefectRecall(MeanPerPRRecall):
        name = "defect_recall"

        def __init__(self) -> None:
            warnings.warn(
                "DefectRecall is deprecated; use MeanPerPRRecall (per-sample mean) "
                "or DetectionRate (industry-standard sum-of-sums recall). See "
                "openspec/changes/eval-metrics-v01/design.md for rationale.",
                DeprecationWarning,
                stacklevel=2,
            )
            super().__init__()

    DefectRecall.__doc__ = (
        "DEPRECATED back-compat alias for MeanPerPRRecall. New code should use "
        "MeanPerPRRecall (per-sample mean) or DetectionRate (sum-of-sums)."
    )
    return DefectRecall


DefectRecall = _build_defect_recall_alias()
