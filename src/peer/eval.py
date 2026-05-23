"""Evaluation harness — historical reviews as the gold standard.

Mines a repo's own historical PR review comments as the calibration set,
then scores any agent's reviews against that standard.

Four metrics planned for v0.1:
- severity_match: does the agent's severity label match the human reviewer's?
- coverage: what fraction of issues humans flagged does the agent also flag?
- false_positive_rate: what fraction of agent flags weren't flagged by humans?
- comment_substance: LLM judge — is the comment substantive vs noise?
"""

from typing import Any


def against_history(
    agent: Any,
    repo: str,
    sample_size: int = 50,
    date_range: tuple[str, str] | None = None,
) -> "EvalReport":
    """Score an agent against the repo's historical human reviews.

    Args:
        agent: an instance with a `.review(pr_url)` method
        repo: "owner/repo"
        sample_size: number of historical PRs to sample
        date_range: optional ("YYYY-MM-DD", "YYYY-MM-DD"). Recommended:
            ("2023-01-01", "2023-12-31") for a clean pre-AI-tool baseline.

    Returns:
        EvalReport with per-metric scores plus per-PR breakdowns.
    """
    raise NotImplementedError("v0.1")


class EvalReport:
    """Container for eval results. Placeholder shape — to be defined in v0.1."""
