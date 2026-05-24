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

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


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
