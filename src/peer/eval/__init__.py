"""peer.eval — eval-runner that composes (Reviewer, dataset, metrics) into
a versioned EvalReport. Three default metrics; pluggable EvalMetric Protocol.

See `openspec/changes/eval-v01/specs/eval-runner/spec.md` for requirements
and `openspec/changes/eval-v01/design.md` for rationale.
"""

# Import report.py for its side effect: it attaches to_json / from_json
# methods to EvalReport. Other importers depend on those methods being present.
from . import report  # noqa: F401
from .compare import (
    ComparisonEntry,
    ComparisonReport,
    compare_to_baseline,
    render_comparison_summary,
)
from .cross_judge import (
    CrossJudgeReport,
    CrossJudgeRunner,
    MetricBand,
    compute_variance_bands,
    render_cross_judge_summary,
)
from .cross_run import (
    CrossRunRunner,
    MultiRunReport,
    compute_run_bands,
    render_multirun_summary,
)
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
    "ComparisonEntry",
    "ComparisonReport",
    "CrossJudgeReport",
    "CrossJudgeRunner",
    "CrossRunRunner",
    "DefectRecall",  # deprecated alias
    "DetectionRate",
    "EvalMetric",
    "EvalReport",
    "EvalRunner",
    "EvalSampleResult",
    "EvalSummary",
    "LLMJudge",
    "MeanPerPRRecall",
    "MetricBand",
    "MetricResult",
    "MultiRunReport",
    "NoveltyRate",
    "PrecisionPerSeverity",
    "RationaleGrounding",
    "SeverityCalibration",
    "SuggestionRate",
    "compare_to_baseline",
    "compute_run_bands",
    "compute_variance_bands",
    "cost_unavailable_reason",
    "estimate_cost",
    "judge_match",
    "render_comparison_summary",
    "render_cross_judge_summary",
    "render_diff",
    "render_multirun_summary",
    "render_summary",
]
