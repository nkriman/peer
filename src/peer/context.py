"""Context gathering: fetches diff, surrounding codebase, PR description,
and discussion for a given PR.

The shape of the context object is part of the framework's opinion — it
determines what the agent sees. v0.1 will define the canonical schema.
"""


def gather(pr_url: str) -> "Context":
    """Pull all context the agent needs to review a PR."""
    raise NotImplementedError("v0.1")


class Context:
    """Container for everything an agent needs to review a PR.

    Placeholder shape — to be defined in v0.1. Expected fields:
    diff, surrounding_code_snippets, pr_description, prior_comments,
    repo_metadata.
    """
