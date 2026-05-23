"""Custom exceptions for peer.

CodebaseContextTooLarge lands in Slice 2 alongside the codebase-context module.
"""


class PeerError(Exception):
    """Base class for all peer-raised errors."""


class UnknownModelError(PeerError):
    """The configured model string doesn't map to a known Reviewer backend."""


class InvalidPRURL(PeerError):
    """The supplied string is not a recognizable GitHub PR URL."""


class PRNotAccessible(PeerError):
    """The PR could not be fetched (404 / 403 / private without auth)."""


class GHCLINotAvailable(PeerError):
    """The `gh` CLI is not installed or not on PATH."""


class GHCLINotAuthenticated(PeerError):
    """The `gh` CLI is installed but not authenticated."""


class ContextTooLarge(PeerError):
    """The assembled Context exceeds the configured token budget."""
