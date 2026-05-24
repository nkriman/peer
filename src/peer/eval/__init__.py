"""peer.eval — eval-runner that composes (Reviewer, dataset, metrics) into
a versioned EvalReport. Three default metrics; pluggable EvalMetric Protocol.

See `openspec/changes/eval-v01/specs/eval-runner/spec.md` for requirements
and `openspec/changes/eval-v01/design.md` for rationale.
"""

# Import report.py for its side effect: it attaches to_json / from_json
# methods to EvalReport. Other importers depend on those methods being present.
from . import report  # noqa: F401
from .judging import JUDGE_MODEL, JUDGE_PROMPT, LLMJudge, RationaleGrounding, judge_match
from .metrics import (
    CommentsPerPR,
    DefectRecall,  # back-compat alias (DeprecationWarning on use)
    DetectionRate,
    EvalMetric,
    MeanPerPRRecall,
    NoveltyRate,
    PrecisionPerSeverity,
    SeverityCalibration,
    SuggestionRate,
)
from .pricing import cost_unavailable_reason, estimate_cost
from .report import render_diff, render_summary
from .runner import EvalRunner
from .types import (
    REPORT_SCHEMA_VERSION,
    AgentConfig,
    AggregateKind,
    EvalReport,
    EvalSampleResult,
    EvalSummary,
    MetricResult,
)

__all__ = [
    "JUDGE_MODEL",
    "JUDGE_PROMPT",
    "REPORT_SCHEMA_VERSION",
    "AgentConfig",
    "AggregateKind",
    "CommentsPerPR",
    "DefectRecall",  # deprecated alias
    "DetectionRate",
    "EvalMetric",
    "EvalReport",
    "EvalRunner",
    "EvalSampleResult",
    "EvalSummary",
    "LLMJudge",
    "MeanPerPRRecall",
    "MetricResult",
    "NoveltyRate",
    "PrecisionPerSeverity",
    "RationaleGrounding",
    "SeverityCalibration",
    "SuggestionRate",
    "cost_unavailable_reason",
    "estimate_cost",
    "judge_match",
    "render_diff",
    "render_summary",
]
