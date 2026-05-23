"""PR review agent."""


class Agent:
    """An AI agent that reviews pull requests.

    Reads the diff, surrounding codebase context, PR description, and
    discussion, then produces structured review comments with severity labels.
    """

    def __init__(self, model: str = "claude-opus-4-7") -> None:
        self.model = model

    def review(self, pr_url: str) -> "Review":
        """Review a single PR by URL. Returns a structured Review."""
        raise NotImplementedError("v0.1")


class Review:
    """A structured review output. Placeholder shape — to be defined in v0.1."""
