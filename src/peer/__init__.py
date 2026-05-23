"""peer — build AI PR review agents with evaluation built in.

See https://github.com/nkriman/peer
"""

from .agent import Agent
from .exceptions import (
    CodebaseContextTooLarge,
    ContextTooLarge,
    GHCLINotAuthenticated,
    GHCLINotAvailable,
    InvalidPRURL,
    PeerError,
    PRNotAccessible,
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
    "Agent",
    "CallSite",
    "CodebaseContext",
    "Comment",
    "Context",
    "ContextHunk",
    "Review",
    "Severity",
    "Symbol",
    "TestFile",
    "PeerError",
    "UnknownModelError",
    "InvalidPRURL",
    "PRNotAccessible",
    "GHCLINotAvailable",
    "GHCLINotAuthenticated",
    "ContextTooLarge",
    "CodebaseContextTooLarge",
]
