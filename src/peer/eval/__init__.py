"""peer.eval — eval-runner that composes (Reviewer, dataset, metrics) into
a versioned EvalReport. Three default metrics; pluggable EvalMetric Protocol.

See `openspec/changes/eval-v01/specs/eval-runner/spec.md` for requirements
and `openspec/changes/eval-v01/design.md` for rationale.
"""

# Import report.py for its side effect: it attaches to_json / from_json
# methods to EvalReport. Other importers depend on those methods being present.
from . import report  # noqa: F401

from .judging import JUDGE_MODEL, JUDGE_PROMPT, judge_match
from .metrics import (
    DefectRecall,
    EvalMetric,
    NoveltyRate,
    SeverityCalibration,
)
from .pricing import cost_unavailable_reason, estimate_cost
from .report import render_diff, render_summary
from .runner import EvalRunner
from .types import (
    AgentConfig,
    EvalReport,
    EvalSampleResult,
    EvalSummary,
    MetricResult,
    REPORT_SCHEMA_VERSION,
)

__all__ = [
    "EvalRunner",
    "EvalMetric",
    "DefectRecall",
    "NoveltyRate",
    "SeverityCalibration",
    "EvalReport",
    "EvalSampleResult",
    "EvalSummary",
    "MetricResult",
    "AgentConfig",
    "REPORT_SCHEMA_VERSION",
    "render_summary",
    "render_diff",
    "estimate_cost",
    "cost_unavailable_reason",
    "judge_match",
    "JUDGE_MODEL",
    "JUDGE_PROMPT",
]
