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


class ContextGatherError(PeerError):
    """A `gh` subprocess in context-gathering failed transiently and did not
    recover after retries (e.g. `gh pr view`/`pr diff`/`api` returning a 5xx or
    network blip). Raised loudly so the eval runner records the sample as
    errored instead of silently proceeding with empty PR context — the same
    fail-loud contract as baselines.BaselineInfraError, on peer's own
    context-gathering path (peer-d55)."""


class CodebaseContextTooLarge(PeerError):
    """The assembled CodebaseContext exceeds the configured token budget
    even after dropping all trimmable categories. Raised when
    modified_symbols alone exceed the budget."""


# -- eval-v01 exceptions ----------------------------------------------------


class InvalidGoldSample(PeerError):
    """A line in a JSONL dataset file failed to validate against the
    GoldSample schema. Includes line number and validation detail."""


class EvalReportSchemaMismatch(PeerError):
    """The loaded EvalReport's report_schema_version doesn't match the
    current loader's supported version."""


class DatasetNotFound(PeerError):
    """The configured dataset path doesn't exist or isn't readable."""


class CurationRejected(PeerError):
    """The operator rejected a proposed GoldSample during an interactive
    Curator.add session."""


class UnknownCategoryError(PeerError):
    """A Classification referenced a category not present in the active
    Taxonomy."""


# -- peer-deps-v01 exceptions ----------------------------------------------


class InvalidBugSample(PeerError):
    """A line in a bug-benchmark JSONL file failed to validate against
    the BugSample schema. Includes line number and field name."""


class LLMCallsDisabled(PeerError):
    """A Reviewer attempted an LLM call while peer.deps.ALLOW_LLM_CALLS=False.

    This is the safety gate against accidental real LLM calls in CI / tests.
    Use `with agent.override(reviewer=TestReviewer()):` for unit tests that
    should not invoke a real model.
    """

    DEFAULT_MESSAGE = (
        "LLM calls are disabled (peer.deps.ALLOW_LLM_CALLS=False). "
        "Use Agent.override(reviewer=TestReviewer()) for tests that should "
        "not invoke a real LLM."
    )

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.DEFAULT_MESSAGE)


class ReviewerRateLimited(PeerError):
    """A Reviewer's HTTP-429 retry budget was exhausted.

    Raised by real Reviewers after `rate_limit_max_retries` exponential
    backoff attempts all failed with HTTP 429. The benchmark runner
    catches this to mark a sample as `rate_limited` rather than `errored`.
    """

    def __init__(self, model: str, attempts: int, last_error: Exception | None = None) -> None:
        self.model = model
        self.attempts = attempts
        self.last_error = last_error
        msg = (
            f"Reviewer for model={model!r} rate-limited after {attempts} attempt(s). "
            f"Last error: {last_error!r}"
        )
        super().__init__(msg)
