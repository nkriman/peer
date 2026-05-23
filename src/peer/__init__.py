"""peer — build AI PR review agents with evaluation built in.

See https://github.com/nkriman/peer
"""

from .agent import Agent
from .exceptions import (
    ContextTooLarge,
    GHCLINotAuthenticated,
    GHCLINotAvailable,
    InvalidPRURL,
    PeerError,
    PRNotAccessible,
    UnknownModelError,
)
from .types import Comment, Context, ContextHunk, Review, Severity

__version__ = "0.0.1"

__all__ = [
    "Agent",
    "Comment",
    "Context",
    "ContextHunk",
    "Review",
    "Severity",
    "PeerError",
    "UnknownModelError",
    "InvalidPRURL",
    "PRNotAccessible",
    "GHCLINotAvailable",
    "GHCLINotAuthenticated",
    "ContextTooLarge",
]
