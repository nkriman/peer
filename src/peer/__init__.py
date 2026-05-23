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
    # Eval surface (most important new exports)
    "EvalRunner",
    "EvalReport",
    "EvalMetric",
    "DefectRecall",
    "NoveltyRate",
    "SeverityCalibration",
    "render_summary",
    # Dataset surface
    "Curator",
    "GoldSample",
    "GoldDefect",
    "Taxonomy",
    "DefaultTaxonomy",
    "JSONLStorage",
    # Existing types
    "CallSite",
    "CodebaseContext",
    "Comment",
    "Context",
    "ContextHunk",
    "Review",
    "Severity",
    "Symbol",
    "TestFile",
    # Exceptions
    "PeerError",
    "UnknownModelError",
    "InvalidPRURL",
    "PRNotAccessible",
    "GHCLINotAvailable",
    "GHCLINotAuthenticated",
    "ContextTooLarge",
    "CodebaseContextTooLarge",
    "InvalidGoldSample",
    "EvalReportSchemaMismatch",
    "DatasetNotFound",
    "CurationRejected",
    "UnknownCategoryError",
]
