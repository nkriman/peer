"""peer.autoresearch — autonomous recipe experimentation loop.

See `program.md` at the repo root for the agent-facing protocol. This
subpackage ships the leaderboard appender, the safe utility-formula
parser, and the CLI implementations behind `peer autoresearch run/loop`.
"""

from .diagnose import (
    CostOutlierSummary,
    FailureSummary,
    PrecisionMiss,
    TopicDriftSummary,
    diagnose_report,
    extract_cost_outliers,
    extract_failure_modes,
    extract_precision_misses,
    extract_topic_drift,
    render_markdown,
)
from .leaderboard import LEADERBOARD_HEADER, append_row
from .loop import no_op_mutator, run_loop
from .runner import run_one_iteration
from .utility import UnsafeUtilityFormula, default_utility, parse_utility_formula

__all__ = [
    "LEADERBOARD_HEADER",
    "CostOutlierSummary",
    "FailureSummary",
    "PrecisionMiss",
    "TopicDriftSummary",
    "UnsafeUtilityFormula",
    "append_row",
    "default_utility",
    "diagnose_report",
    "extract_cost_outliers",
    "extract_failure_modes",
    "extract_precision_misses",
    "extract_topic_drift",
    "no_op_mutator",
    "parse_utility_formula",
    "render_markdown",
    "run_loop",
    "run_one_iteration",
]
