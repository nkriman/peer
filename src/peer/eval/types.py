"""Pydantic schemas for the eval pipeline.

Per design.md Decision 8: EvalReport is JSON-serializable with a versioned
schema so users can store reports in git for trend tracking.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

REPORT_SCHEMA_VERSION = "1.0"


class MetricResult(BaseModel):
    """One metric's result for one sample (or aggregate)."""

    name: str
    value: float | None = None  # the headline number; None if not computable
    per_sample_detail: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None  # e.g., "no gold defects on this sample"


class EvalSampleResult(BaseModel):
    """Per-sample slice of an EvalReport."""

    pr_url: str
    metrics: dict[str, MetricResult] = Field(default_factory=dict)  # keyed by metric name
    cost_usd: float | None = None
    latency_seconds: float | None = None
    review_summary: dict[str, Any] = Field(
        default_factory=dict
    )  # comment count, severity dist, usage
    error: str | None = None  # set if the reviewer failed on this sample


class EvalSummary(BaseModel):
    """Aggregate across all samples."""

    metric_values: dict[str, float | None] = Field(
        default_factory=dict
    )  # metric_name -> aggregate value
    metric_details: dict[str, dict[str, Any]] = Field(default_factory=dict)
    n_samples_total: int = 0
    n_samples_succeeded: int = 0
    n_samples_failed: int = 0
    cost_usd_total: float | None = None
    cost_usd_p50: float | None = None
    cost_usd_p95: float | None = None
    cost_unavailable_reason: str | None = None
    latency_seconds_p50: float | None = None
    latency_seconds_p95: float | None = None


class AgentConfig(BaseModel):
    """Capture of how the reviewer was configured for this run, for reproducibility."""

    model: str
    system_prompt_hash: str | None = None  # sha256 of the system prompt
    reviewer_class: str  # e.g., "ClaudeReviewer"


class EvalReport(BaseModel):
    """A versioned, JSON-serializable evaluation report."""

    report_schema_version: str = REPORT_SCHEMA_VERSION
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    agent_config: AgentConfig
    dataset_path: str | None = None  # filesystem path or "in-memory"
    dataset_size: int = 0
    summary: EvalSummary = Field(default_factory=EvalSummary)
    per_sample: list[EvalSampleResult] = Field(default_factory=list)
    peer_version: str | None = None  # from __version__
