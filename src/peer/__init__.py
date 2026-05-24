"""peer — build AI PR review agents with evaluation built in.

See https://github.com/nkriman/peer
"""

from .agent import Agent
from .dataset import (
    Curator,
    DefaultTaxonomy,
    GoldDefect,
    GoldSample,
    JSONLStorage,
    Taxonomy,
)
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
    PeerError,
    PRNotAccessible,
    UnknownCategoryError,
    UnknownModelError,
)
from .types import (
    CallSite,
    CodebaseContext,
    Comment,
    Context,
    ContextHunk,
    Review,
    Severity,
    Symbol,
    TestFile,
)

__version__ = "0.0.1"

__all__ = [
    # Agent
    "Agent",
    # Existing types
    "CallSite",
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
    "NoveltyRate",
    "PRNotAccessible",
    # Exceptions
    "PeerError",
    "Review",
    "Severity",
    "SeverityCalibration",
    "Symbol",
    "Taxonomy",
    "TestFile",
    "UnknownCategoryError",
    "UnknownModelError",
    "render_summary",
]
