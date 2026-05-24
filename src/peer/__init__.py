"""peer — build AI PR review agents with evaluation built in.

See https://github.com/nkriman/peer
"""

from .agent import Agent
from .baselines import BareClaudeCodeReviewer
from .dataset import (
    Curator,
    DefaultTaxonomy,
    GoldDefect,
    GoldSample,
    JSONLStorage,
    Taxonomy,
)
from .deps import PeerDeps
from .eval import (
    DefectRecall,
    EvalMetric,
    EvalReport,
    EvalRunner,
    NoveltyRate,
    SeverityCalibration,
    render_summary,
)
from .exceptions import (
    CodebaseContextTooLarge,
    ContextTooLarge,
    CurationRejected,
    DatasetNotFound,
    EvalReportSchemaMismatch,
    GHCLINotAuthenticated,
    GHCLINotAvailable,
    InvalidGoldSample,
    InvalidPRURL,
    LLMCallsDisabled,
    PeerError,
    PRNotAccessible,
    ReviewerRateLimited,
    UnknownCategoryError,
    UnknownModelError,
)
from .linters import Linter, RuffLinter
from .recipe import Recipe
from .reviewers import ClaudeCodeCLIReviewer, ClaudeReviewer, Reviewer, TestReviewer
from .runtime import CapturedMessage, RunContext, capture_run_messages
from .types import (
    CallSite,
    CodebaseContext,
    Comment,
    Context,
    ContextHunk,
    LinterFinding,
    Review,
    Severity,
    Symbol,
    TestFile,
)

__version__ = "0.0.1"

__all__ = [
    # Agent
    "Agent",
    "BareClaudeCodeReviewer",
    # Existing types
    "CallSite",
    "CapturedMessage",
    "ClaudeCodeCLIReviewer",
    "ClaudeReviewer",
    "CodebaseContext",
    "CodebaseContextTooLarge",
    "Comment",
    "Context",
    "ContextHunk",
    "ContextTooLarge",
    "CurationRejected",
    # Dataset surface
    "Curator",
    "DatasetNotFound",
    "DefaultTaxonomy",
    "DefectRecall",
    "EvalMetric",
    "EvalReport",
    "EvalReportSchemaMismatch",
    # Eval surface (most important new exports)
    "EvalRunner",
    "GHCLINotAuthenticated",
    "GHCLINotAvailable",
    "GoldDefect",
    "GoldSample",
    "InvalidGoldSample",
    "InvalidPRURL",
    "JSONLStorage",
    "LLMCallsDisabled",
    "Linter",
    "LinterFinding",
    "NoveltyRate",
    "PRNotAccessible",
    "PeerDeps",
    # Exceptions
    "PeerError",
    "Recipe",
    "Review",
    "Reviewer",
    "ReviewerRateLimited",
    "RuffLinter",
    "RunContext",
    "Severity",
    "SeverityCalibration",
    "Symbol",
    "Taxonomy",
    "TestFile",
    "TestReviewer",
    "UnknownCategoryError",
    "UnknownModelError",
    "capture_run_messages",
    "render_summary",
]
