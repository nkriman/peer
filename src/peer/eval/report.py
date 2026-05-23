"""EvalReport serialization + CLI rendering (single-report + A/B diff)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from ..exceptions import EvalReportSchemaMismatch
from .types import REPORT_SCHEMA_VERSION, EvalReport


# ---------------------------------------------------------------------------
# Serialization (monkey-patched onto EvalReport for ergonomic .to_json()).
# ---------------------------------------------------------------------------


def _to_json(self: EvalReport, path: Union[Path, str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = self.model_dump(mode="json")
    p.write_text(json.dumps(data, indent=2, default=str))


def _from_json(cls, path: Union[Path, str]) -> EvalReport:
    p = Path(path)
    raw = json.loads(p.read_text())
    version = raw.get("report_schema_version")
    if version != REPORT_SCHEMA_VERSION:
        raise EvalReportSchemaMismatch(
            f"Report at {p} has schema version {version!r}, but loader "
            f"supports {REPORT_SCHEMA_VERSION!r}. Migration hint: regenerate "
            f"the report with the current peer release, or pin to a peer "
            f"version that supports schema {version!r}."
        )
    return cls.model_validate(raw)


EvalReport.to_json = _to_json  # type: ignore[attr-defined]
EvalReport.from_json = classmethod(_from_json)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _fmt_float(v, fmt: str = "{:.3f}") -> str:
    if v is None:
        return "n/a"
    return fmt.format(v)


def _fmt_money(v) -> str:
    if v is None:
        return "n/a"
    return f"${v:.4f}"


def _fmt_secs(v) -> str:
    if v is None:
        return "n/a"
    return f"{v:.2f}s"


def render_summary(report: EvalReport) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"  peer eval report ({report.run_id[:8]})")
    lines.append("=" * 60)
    lines.append(f"  timestamp:     {report.timestamp.isoformat()}")
    lines.append(f"  schema:        {report.report_schema_version}")
    if report.peer_version:
        lines.append(f"  peer version:  {report.peer_version}")
    lines.append("")
    lines.append("  Agent config:")
    lines.append(f"    model:          {report.agent_config.model}")
    lines.append(f"    reviewer:       {report.agent_config.reviewer_class}")
    if report.agent_config.system_prompt_hash:
        lines.append(
            f"    prompt hash:    {report.agent_config.system_prompt_hash}"
        )
    lines.append("")
    lines.append(f"  Dataset:         {report.dataset_path}")
    lines.append(f"  Samples total:   {report.summary.n_samples_total}")
    lines.append(f"  Samples ok:      {report.summary.n_samples_succeeded}")
    lines.append(f"  Samples failed:  {report.summary.n_samples_failed}")
    lines.append("")
    lines.append("  Metrics (mean across samples with value):")
    if not report.summary.metric_values:
        lines.append("    (no metrics)")
    for name, value in report.summary.metric_values.items():
        details = report.summary.metric_details.get(name, {})
        n_with = details.get("n_samples_with_value", "?")
        n_skip = details.get("n_samples_skipped", "?")
        lines.append(
            f"    {name:<24} {_fmt_float(value):>8}    "
            f"(n={n_with}, skipped={n_skip})"
        )
    lines.append("")
    lines.append("  Cost (USD):")
    lines.append(f"    total:           {_fmt_money(report.summary.cost_usd_total)}")
    lines.append(f"    p50 per sample:  {_fmt_money(report.summary.cost_usd_p50)}")
    lines.append(f"    p95 per sample:  {_fmt_money(report.summary.cost_usd_p95)}")
    if report.summary.cost_unavailable_reason:
        lines.append(
            f"    note: {report.summary.cost_unavailable_reason}"
        )
    lines.append("")
    lines.append("  Latency:")
    lines.append(f"    p50:             {_fmt_secs(report.summary.latency_seconds_p50)}")
    lines.append(f"    p95:             {_fmt_secs(report.summary.latency_seconds_p95)}")
    lines.append("=" * 60)
    return "\n".join(lines)


def _delta_str(a, b) -> str:
    if a is None or b is None:
        return "n/a"
    d = b - a
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:.3f}"


def _money_delta_str(a, b) -> str:
    if a is None or b is None:
        return "n/a"
    d = b - a
    sign = "+" if d >= 0 else ""
    return f"{sign}${d:.4f}"


def render_diff(report_a: EvalReport, report_b: EvalReport) -> str:
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("  peer eval A/B diff")
    lines.append(
        f"  A: {report_a.run_id[:8]}  model={report_a.agent_config.model}"
    )
    lines.append(
        f"  B: {report_b.run_id[:8]}  model={report_b.agent_config.model}"
    )
    lines.append("=" * 72)

    # Per-metric deltas
    lines.append("")
    lines.append("  Metrics  (A -> B, delta):")
    all_metrics = list(report_a.summary.metric_values.keys()) + [
        m for m in report_b.summary.metric_values.keys()
        if m not in report_a.summary.metric_values
    ]
    for name in all_metrics:
        a = report_a.summary.metric_values.get(name)
        b = report_b.summary.metric_values.get(name)
        lines.append(
            f"    {name:<24} {_fmt_float(a):>8} -> {_fmt_float(b):>8}   "
            f"({_delta_str(a, b)})"
        )

    # Cost
    lines.append("")
    lines.append("  Cost (USD):")
    a_t = report_a.summary.cost_usd_total
    b_t = report_b.summary.cost_usd_total
    lines.append(
        f"    total            {_fmt_money(a_t)} -> {_fmt_money(b_t)}   "
        f"({_money_delta_str(a_t, b_t)})"
    )
    a_p50 = report_a.summary.cost_usd_p50
    b_p50 = report_b.summary.cost_usd_p50
    lines.append(
        f"    p50 per sample   {_fmt_money(a_p50)} -> {_fmt_money(b_p50)}   "
        f"({_money_delta_str(a_p50, b_p50)})"
    )
    a_p95 = report_a.summary.cost_usd_p95
    b_p95 = report_b.summary.cost_usd_p95
    lines.append(
        f"    p95 per sample   {_fmt_money(a_p95)} -> {_fmt_money(b_p95)}   "
        f"({_money_delta_str(a_p95, b_p95)})"
    )

    # Latency
    lines.append("")
    lines.append("  Latency:")
    a_l50 = report_a.summary.latency_seconds_p50
    b_l50 = report_b.summary.latency_seconds_p50
    lines.append(
        f"    p50              {_fmt_secs(a_l50)} -> {_fmt_secs(b_l50)}"
    )
    a_l95 = report_a.summary.latency_seconds_p95
    b_l95 = report_b.summary.latency_seconds_p95
    lines.append(
        f"    p95              {_fmt_secs(a_l95)} -> {_fmt_secs(b_l95)}"
    )

    # Per-sample regression / improvement counts
    a_by_url = {s.pr_url: s for s in report_a.per_sample}
    b_by_url = {s.pr_url: s for s in report_b.per_sample}
    regressions = 0
    improvements = 0
    newly_failed = 0
    for url, b_s in b_by_url.items():
        a_s = a_by_url.get(url)
        if a_s is None:
            continue
        # If A succeeded but B errored, regression.
        if a_s.error is None and b_s.error is not None:
            regressions += 1
            newly_failed += 1
            continue
        # Compare per-metric
        sample_regressed = False
        sample_improved = False
        for name, b_mr in b_s.metrics.items():
            a_mr = a_s.metrics.get(name)
            if a_mr is None:
                continue
            if a_mr.value is None or b_mr.value is None:
                continue
            if b_mr.value < a_mr.value:
                sample_regressed = True
            elif b_mr.value > a_mr.value:
                sample_improved = True
        if sample_regressed:
            regressions += 1
        elif sample_improved:
            improvements += 1

    lines.append("")
    lines.append("  Per-sample:")
    lines.append(f"    regressions:     {regressions}")
    lines.append(f"    improvements:    {improvements}")
    lines.append(f"    newly failed:    {newly_failed}")
    lines.append(
        f"    A samples: {len(a_by_url)}   B samples: {len(b_by_url)}"
    )
    lines.append("=" * 72)
    return "\n".join(lines)


__all__ = ["render_summary", "render_diff"]
