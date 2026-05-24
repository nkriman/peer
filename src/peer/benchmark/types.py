"""Pydantic schemas for the bug-benchmark capability.

Per benchmark-v01 design.md Decision 0: BugLocation gains
`line_coordinate_system: Literal["bug_commit", "pr_head", "synthetic"]`
so the runner knows which frame each line number is in.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ..eval.types import AgentConfig
from ..types import Severity

# What frame BugLocation line numbers are in. Per design.md Decision 0,
# the runner translates between these via git blame --reverse when peer
# reviews a PR-introducing-the-bug; otherwise uses them as-is.
LineCoordinateSystem = Literal["bug_commit", "pr_head", "synthetic"]


class BugLocation(BaseModel):
    """One location in source code where a bug manifests."""

    path: str
    start_line: int
    end_line: int


class BugSample(BaseModel):
    """One unit of a runtime-bug benchmark dataset."""

    model_config = ConfigDict(extra="forbid")

    bug_id: str
    repo_url: str = ""
    pr_url: str | None = None  # PR that introduced the bug, when known
    commit_sha: str = ""  # the buggy commit
    bug_paths: list[BugLocation]
    root_cause: str
    suggested_fix: str | None = None
    severity: Severity = "important"
    language: str
    bug_category: str | None = None
    line_coordinate_system: LineCoordinateSystem = "bug_commit"
    metadata: dict[str, Any] = Field(default_factory=dict)


class BugBenchmarkResult(BaseModel):
    """Per-bug result inside a BenchmarkReport."""

    bug_id: str
    caught: bool
    reason: str = ""  # "no comments in proximity" / "judge rejected" / "caught"
    matching_peer_comments: list[dict[str, Any]] = Field(default_factory=list)


class BenchmarkReport(BaseModel):
    """A versioned, JSON-serializable bug-benchmark report."""

    report_schema_version: str = "1.0"
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    agent_config: AgentConfig
    dataset_id: str
    dataset_size: int = 0
    n_bugs_caught: int = 0
    n_bugs_total: int = 0
    n_bugs_skipped: int = 0
    detection_rate: float | None = None
    comments_per_pr: float | None = None
    cost_usd_total: float | None = None
    latency_p50_seconds: float | None = None
    per_bug: list[BugBenchmarkResult] = Field(default_factory=list)
    published_baselines: dict[str, dict[str, Any]] = Field(default_factory=dict)
    peer_version: str | None = None
