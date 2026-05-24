"""Per-run context — typed wrapper around deps + PR identity + attempt counter.

Inspired by Pydantic AI's `RunContext[T]` pattern. Generic over the deps
type so static type checkers see e.g. `RunContext[PeerDeps]` and surface
errors when a Reviewer or Evaluator accesses a non-existent field on
`ctx.deps`.

NO `metadata` field (per peer-deps-v01 adversarial review item 5.4): the
escape-hatch dict undermines the type-safety pitch RunContext exists to
deliver. If user code needs adaptive per-attempt data, it lives on a
user-supplied PeerDeps subclass or a typed model — not on RunContext.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class CapturedMessage(BaseModel):
    """One Reviewer round-trip captured inside a `capture_run_messages` block.

    `raw_response` is a dict (Reviewers convert SDK responses to plain dicts so
    capture buffers serialize cleanly to JSON for eval/benchmark forensics).
    """

    system_prompt: str
    user_prompt: str
    raw_response: dict
    usage: dict
    latency_ms: float = 0.0
    pr_url: str | None = None
    attempt: int = 0

    model_config = ConfigDict(extra="forbid")


# Async-safe per-run buffer (peer-deps-v01 adversarial review 1.2).
# Each `capture_run_messages()` block sets this to a fresh list scoped to the
# current task; Agent.run appends if the contextvar is non-None.
_capture_buffer: ContextVar[list[CapturedMessage] | None] = ContextVar(
    "_peer_capture_buffer", default=None
)


@contextmanager
def capture_run_messages() -> Iterator[list[CapturedMessage]]:
    """Context manager that captures every Reviewer round-trip inside the block.

    Yields a list that Agent.run appends to after each Reviewer call.
    contextvars-based, so concurrent asyncio tasks each get an independent
    buffer (verified by features/peer_deps_followups.feature).
    """
    buf: list[CapturedMessage] = []
    token = _capture_buffer.set(buf)
    try:
        yield buf
    finally:
        _capture_buffer.reset(token)


def _emit_captured_message(**kwargs: Any) -> None:
    """Internal: Agent.run calls this after each Reviewer round-trip.

    Silently no-ops when no capture block is active.
    """
    buf = _capture_buffer.get()
    if buf is None:
        return
    buf.append(CapturedMessage(**kwargs))


class RunContext(BaseModel, Generic[T]):
    """Run-scoped context handed to Reviewers + Evaluators.

    Fields:
      - `deps`: the typed per-run dependency container (typically `PeerDeps`
        or a user-supplied dataclass).
      - `pr_url`: the PR being reviewed.
      - `attempt`: retry attempt index, 0-based. The first call has
        `attempt=0`; subsequent retries from validation-retry plumbing
        increment this so Reviewers can adapt their prompt on retries.
    """

    deps: T
    pr_url: str
    attempt: int = 0

    model_config = ConfigDict(arbitrary_types_allowed=True)
