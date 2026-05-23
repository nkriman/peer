"""Pluggable reviewer interface — adapters for different LLM backends and,
later, for commercial AI PR review tools so they can be scored on the same
eval harness.

v0.1 will ship: ClaudeReviewer, OpenAIReviewer.
v0.3 may add: GreptileAdapter, CodeRabbitAdapter (BYO API keys).
"""

from typing import Protocol


class Reviewer(Protocol):
    """Anything that takes a Context and produces review comments."""

    def review(self, context: "Context") -> list["Comment"]:  # type: ignore[name-defined]
        ...


class Comment:
    """A single review comment. Placeholder shape — defined in v0.1.

    Expected fields: path, line, severity (critical/important/minor/nit),
    body, rationale.
    """
