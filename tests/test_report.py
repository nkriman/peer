"""Tests for peer.eval.report."""

from __future__ import annotations

import json

import pytest

# Importing peer.eval.report triggers monkey-patching of EvalReport.to_json/.from_json
from peer.eval import (  # noqa: F401
    AgentConfig,
    EvalReport,
    EvalSampleResult,
    EvalSummary,
    MetricResult,
    REPORT_SCHEMA_VERSION,
    render_diff,
    render_summary,
)
from peer.exceptions import EvalReportSchemaMismatch


def _agent_config() -> AgentConfig:
    return AgentConfig(
        model="claude-sonnet-4-6",
        system_prompt_hash="abc123",
        reviewer_class="Agent",
    )


def _report(
    metric_values: dict[str, float] | None = None,
    n_total: int = 2,
    n_succeeded: int = 2,
    n_failed: int = 0,
    cost_total: float | None = 0.05,
    per_sample: list[EvalSampleResult] | None = None,
) -> EvalReport:
    if metric_values is None:
        metric_values = {"defect_recall": 0.5, "novelty_rate": 0.2}
    summary = EvalSummary(
        metric_values=metric_values,
        metric_details={
            name: {"n_samples_with_value": 1, "n_samples_skipped": 0}
            for name in metric_values
        },
        n_samples_total=n_total,
        n_samples_succeeded=n_succeeded,
        n_samples_failed=n_failed,
        cost_usd_total=cost_total,
        cost_usd_p50=0.025,
        cost_usd_p95=0.04,
        latency_seconds_p50=1.5,
        latency_seconds_p95=2.5,
    )
    return EvalReport(
        agent_config=_agent_config(),
        dataset_path="data/test.jsonl",
        dataset_size=n_total,
        summary=summary,
        per_sample=per_sample or [],
    )


def test_to_json_from_json_roundtrip(tmp_path):
    report = _report()
    path = tmp_path / "report.json"
    report.to_json(path)
    loaded = EvalReport.from_json(path)
    assert loaded.run_id == report.run_id
    assert loaded.agent_config.model == "claude-sonnet-4-6"
    assert loaded.summary.metric_values["defect_recall"] == 0.5
    assert loaded.summary.cost_usd_total == 0.05


def test_to_json_creates_parent_dirs(tmp_path):
    report = _report()
    path = tmp_path / "nested" / "dirs" / "r.json"
    report.to_json(path)
    assert path.exists()


def test_from_json_raises_on_schema_mismatch(tmp_path):
    path = tmp_path / "old.json"
    data = {
        "report_schema_version": "0.1-ancient",
        "run_id": "x",
        "timestamp": "2026-01-01T00:00:00",
        "agent_config": {"model": "m", "reviewer_class": "X"},
        "summary": {},
        "per_sample": [],
    }
    path.write_text(json.dumps(data))
    with pytest.raises(EvalReportSchemaMismatch) as exc_info:
        EvalReport.from_json(path)
    assert "0.1-ancient" in str(exc_info.value)
    assert REPORT_SCHEMA_VERSION in str(exc_info.value)


def test_render_summary_contains_key_fields():
    report = _report()
    out = render_summary(report)
    assert isinstance(out, str)
    # Run id (truncated to 8)
    assert report.run_id[:8] in out
    # Agent config
    assert "claude-sonnet-4-6" in out
    # Metric names
    assert "defect_recall" in out
    assert "novelty_rate" in out
    # Dataset info
    assert "data/test.jsonl" in out
    # Cost row
    assert "Cost" in out
    assert "Latency" in out


def test_render_summary_handles_no_metrics():
    report = _report(metric_values={})
    out = render_summary(report)
    assert "(no metrics)" in out


def test_render_summary_handles_none_cost():
    report = _report(cost_total=None)
    out = render_summary(report)
    assert "n/a" in out


def test_render_diff_includes_both_run_ids():
    a = _report(metric_values={"defect_recall": 0.4})
    b = _report(metric_values={"defect_recall": 0.6})
    out = render_diff(a, b)
    assert a.run_id[:8] in out
    assert b.run_id[:8] in out
    assert "defect_recall" in out
    # Delta should be +0.200
    assert "+0.200" in out


def test_render_diff_counts_regressions_and_improvements():
    # Two samples shared between A and B with metric values that regressed
    pr1 = "https://github.com/o/r/pull/1"
    pr2 = "https://github.com/o/r/pull/2"
    a_samples = [
        EvalSampleResult(
            pr_url=pr1,
            metrics={"defect_recall": MetricResult(name="defect_recall", value=0.8)},
        ),
        EvalSampleResult(
            pr_url=pr2,
            metrics={"defect_recall": MetricResult(name="defect_recall", value=0.3)},
        ),
    ]
    b_samples = [
        EvalSampleResult(
            pr_url=pr1,
            metrics={"defect_recall": MetricResult(name="defect_recall", value=0.5)},
        ),
        EvalSampleResult(
            pr_url=pr2,
            metrics={"defect_recall": MetricResult(name="defect_recall", value=0.6)},
        ),
    ]
    a = _report(per_sample=a_samples)
    b = _report(per_sample=b_samples)
    out = render_diff(a, b)
    assert "regressions:     1" in out
    assert "improvements:    1" in out


def test_render_diff_counts_newly_failed():
    pr = "https://github.com/o/r/pull/1"
    a_samples = [EvalSampleResult(pr_url=pr)]  # no error
    b_samples = [EvalSampleResult(pr_url=pr, error="boom")]
    a = _report(per_sample=a_samples)
    b = _report(per_sample=b_samples)
    out = render_diff(a, b)
    assert "newly failed:    1" in out
    assert "regressions:     1" in out
