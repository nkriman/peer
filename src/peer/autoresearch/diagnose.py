"""Diagnose: extract structured failure summaries from an EvalReport.

Pure functions over an `EvalReport` — no I/O, no LLM calls. The
autoresearch loop calls these after each iteration to produce a markdown
hypothesis the experimenting agent reads before proposing its next
mutation. This closes the diagnostic loop: every mutation cites a
specific failure mode from the previous iteration, not vibes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_SEVERITY_KEYS = ("critical", "important", "minor", "nit")
_MUTATION_AXES = [
    "system_prompt (edit prompts/default_system_prompt.md content / structure)",
    "temperature (raise for diversity, lower for consistency)",
    "model (swap sonnet ↔ opus ↔ haiku for cost/quality)",
    "retries (raise output retries to recover from grounding misses)",
    "post_processing.max_comments_per_pr (cap to fight volume blowups)",
    "post_processing.severity_floor (drop nits / minors to lift precision)",
    "reviewer_dotted_path = draft_critique (add a self-critique pass)",
    "reviewer_dotted_path = two_model_pipeline (cheap screen + expensive detail)",
    "reviewer_dotted_path = self_filter (drop low-confidence comments)",
    "codebase_context_max_tokens (raise for more context, lower for cost)",
]


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PerSeverityCount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    critical: int = 0
    important: int = 0
    minor: int = 0
    nit: int = 0


class FailureSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    per_severity: PerSeverityCount = Field(default_factory=PerSeverityCount)
    n_samples_with_misses: int = 0
    n_unmatched_total: int = 0
    samples: list[dict] = Field(default_factory=list)


class DriftSample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pr_url: str
    n_peer_comments: int
    peer_locations: list[dict] = Field(default_factory=list)
    gold_locations: list[dict] = Field(default_factory=list)


class TopicDriftSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    drift_samples: list[DriftSample] = Field(default_factory=list)


class CostOutlier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pr_url: str
    cost_usd: float
    n_comments: int


class CostOutlierSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    top: list[CostOutlier] = Field(default_factory=list)
    total_cost_usd: float = 0.0


class PrecisionMiss(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pr_url: str
    path: str
    line: int | None = None
    severity: str
    body: str


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------


def _per_sample_detail(s: Any, metric: str) -> dict[str, Any]:
    mr = s.metrics.get(metric)
    if mr is None:
        return {}
    d = getattr(mr, "per_sample_detail", None)
    return d if isinstance(d, dict) else {}


def extract_failure_modes(report: Any) -> FailureSummary:
    """Aggregate unmatched_gold across all samples, grouping by severity."""
    counts = {k: 0 for k in _SEVERITY_KEYS}
    n_samples_with = 0
    n_total = 0
    samples_out: list[dict] = []
    for s in report.per_sample:
        d = _per_sample_detail(s, "mean_per_pr_recall")
        unmatched = d.get("unmatched_gold") or []
        if not unmatched:
            continue
        n_samples_with += 1
        per_sev: dict[str, int] = {k: 0 for k in _SEVERITY_KEYS}
        for g in unmatched:
            sev = (g.get("severity") if isinstance(g, dict) else None) or "minor"
            if sev in counts:
                counts[sev] += 1
                per_sev[sev] += 1
            n_total += 1
        samples_out.append(
            {"pr_url": s.pr_url, "per_severity": per_sev, "n_unmatched": len(unmatched)}
        )
    return FailureSummary(
        per_severity=PerSeverityCount(**counts),
        n_samples_with_misses=n_samples_with,
        n_unmatched_total=n_total,
        samples=samples_out,
    )


def extract_topic_drift(report: Any) -> TopicDriftSummary:
    """Samples where peer emitted >=1 comment AND matched 0 gold defects."""
    drift: list[DriftSample] = []
    for s in report.per_sample:
        rs = s.review_summary or {}
        n_peer = int(rs.get("n_comments", 0)) if isinstance(rs.get("n_comments"), int) else 0
        if n_peer == 0:
            continue
        d = _per_sample_detail(s, "detection_rate")
        matched = d.get("matched_count", 0) if isinstance(d.get("matched_count"), int) else 0
        if matched > 0:
            continue
        # Peer locations come from novelty_rate.unmatched_peer.
        nv = _per_sample_detail(s, "novelty_rate")
        unmatched_peer = nv.get("unmatched_peer") or []
        peer_locs = [
            {"path": c.get("path"), "line": c.get("line"), "body": (c.get("body") or "")[:200]}
            for c in unmatched_peer
            if isinstance(c, dict)
        ]
        # Gold locations come from mean_per_pr_recall.unmatched_gold.
        rg = _per_sample_detail(s, "mean_per_pr_recall")
        unmatched_gold = rg.get("unmatched_gold") or []
        gold_locs = [
            {
                "path": g.get("path"),
                "line": g.get("line"),
                "severity": g.get("severity"),
                "description": (g.get("description") or "")[:200],
            }
            for g in unmatched_gold
            if isinstance(g, dict)
        ]
        drift.append(
            DriftSample(
                pr_url=s.pr_url,
                n_peer_comments=n_peer,
                peer_locations=peer_locs,
                gold_locations=gold_locs,
            )
        )
    return TopicDriftSummary(drift_samples=drift)


def extract_cost_outliers(report: Any, n_top: int = 3) -> CostOutlierSummary:
    """Top-N most expensive samples by cost_usd."""
    items: list[CostOutlier] = []
    total = 0.0
    for s in report.per_sample:
        cost = s.cost_usd
        if cost is None:
            continue
        total += float(cost)
        rs = s.review_summary or {}
        n = rs.get("n_comments", 0) if isinstance(rs.get("n_comments"), int) else 0
        items.append(CostOutlier(pr_url=s.pr_url, cost_usd=float(cost), n_comments=int(n)))
    items.sort(key=lambda x: x.cost_usd, reverse=True)
    return CostOutlierSummary(top=items[:n_top], total_cost_usd=total)


def extract_precision_misses(report: Any) -> list[PrecisionMiss]:
    """Peer comments not matched to any gold defect, across all samples."""
    out: list[PrecisionMiss] = []
    for s in report.per_sample:
        nv = _per_sample_detail(s, "novelty_rate")
        for c in nv.get("unmatched_peer") or []:
            if not isinstance(c, dict):
                continue
            out.append(
                PrecisionMiss(
                    pr_url=s.pr_url,
                    path=str(c.get("path") or "?"),
                    line=c.get("line") if isinstance(c.get("line"), int) else None,
                    severity=str(c.get("severity") or "minor"),
                    body=str(c.get("body") or "")[:300],
                )
            )
    return out


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def render_markdown(
    failure: FailureSummary,
    drift: TopicDriftSummary,
    cost: CostOutlierSummary,
    precision_misses: list[PrecisionMiss],
) -> str:
    """Render the structured hypothesis document. Deterministic; no timestamps."""
    lines: list[str] = []
    lines.append("# Hypothesis")
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append(
        f"- unmatched gold defects: {failure.n_unmatched_total} across "
        f"{failure.n_samples_with_misses} sample(s)"
    )
    lines.append(
        f"- topic-drift samples (peer commented, matched none): {len(drift.drift_samples)}"
    )
    lines.append(
        f"- top cost: ${cost.top[0].cost_usd:.4f} on {cost.top[0].pr_url}"
        if cost.top
        else "- top cost: n/a"
    )
    lines.append(f"- total session cost: ${cost.total_cost_usd:.4f}")
    lines.append(f"- precision-miss peer comments: {len(precision_misses)}")
    lines.append("")
    lines.append("## Failure modes by severity")
    lines.append("")
    s = failure.per_severity
    lines.append(f"- critical: {s.critical}")
    lines.append(f"- important: {s.important}")
    lines.append(f"- minor: {s.minor}")
    lines.append(f"- nit: {s.nit}")
    lines.append("")
    lines.append("### Per-sample failures")
    lines.append("")
    for s_entry in failure.samples:
        url = s_entry.get("pr_url", "?")
        per_sev = s_entry.get("per_severity") or {}
        lines.append(
            f"- {url} — {s_entry.get('n_unmatched', 0)} unmatched "
            f"(critical={per_sev.get('critical', 0)}, important={per_sev.get('important', 0)}, "
            f"minor={per_sev.get('minor', 0)}, nit={per_sev.get('nit', 0)})"
        )
    lines.append("")
    lines.append("## Topic drift")
    lines.append("")
    if not drift.drift_samples:
        lines.append("- (none — every PR with peer comments matched at least one gold)")
    else:
        for ds in drift.drift_samples:
            lines.append(
                f"### {ds.pr_url} — peer wrote {ds.n_peer_comments} comment(s); 0 matched gold"
            )
            lines.append("")
            lines.append("Peer wrote about:")
            for p in ds.peer_locations:
                lines.append(f"- {p.get('path')}:{p.get('line')} — {p.get('body', '')}")
            lines.append("")
            lines.append("Gold expected:")
            for g in ds.gold_locations:
                lines.append(
                    f"- [{g.get('severity')}] {g.get('path')}:{g.get('line')} — "
                    f"{g.get('description', '')}"
                )
            lines.append("")
    lines.append("## Cost outliers")
    lines.append("")
    if not cost.top:
        lines.append("- (no cost data; pricing table may not recognize the model)")
    else:
        for co in cost.top:
            lines.append(f"- ${co.cost_usd:.4f} — {co.pr_url} ({co.n_comments} comments)")
    lines.append("")
    lines.append("## Precision concerns")
    lines.append("")
    if not precision_misses:
        lines.append("- (none — every peer comment matched a gold defect)")
    else:
        lines.append(f"- {len(precision_misses)} peer comment(s) matched no gold defect:")
        for pm in precision_misses[:20]:  # cap to avoid runaway markdown
            lines.append(f"  - [{pm.severity}] {pm.pr_url} @ {pm.path}:{pm.line} — {pm.body[:120]}")
        if len(precision_misses) > 20:
            lines.append(f"  - ...+{len(precision_misses) - 20} more")
    lines.append("")
    lines.append("## Suggested mutation axes")
    lines.append("")
    lines.append(
        "When proposing your next mutation, pick ONE axis (or a small combo). "
        "Cite a specific failure mode above as your motivation."
    )
    lines.append("")
    for axis in _MUTATION_AXES:
        lines.append(f"- {axis}")
    lines.append("")
    return "\n".join(lines)


def diagnose_report(report: Any) -> str:
    """Convenience: extract everything + render in one call."""
    return render_markdown(
        extract_failure_modes(report),
        extract_topic_drift(report),
        extract_cost_outliers(report),
        extract_precision_misses(report),
    )
