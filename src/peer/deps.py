"""Per-run dependencies + the ALLOW_LLM_CALLS safety flag.

Inspired by Pydantic AI's `deps_type` / `RunContext` pattern (see
`docs/pydantic_ai_design_philosophy.md`). `PeerDeps` carries the
runtime-pluggable dependencies an Agent needs; it's passed to
`Agent.run(pr_url, deps=...)` at run-time rather than stuffed into the
constructor.

`ALLOW_LLM_CALLS` is a module-level boolean. When `False`, every shipped
real Reviewer (ClaudeReviewer / OpenAIReviewer) raises `LLMCallsDisabled`
before making the SDK call. The TestReviewer ignores the flag — its job
is to be invoked without network access. Intended use:

    import peer.deps
    peer.deps.ALLOW_LLM_CALLS = False  # in conftest.py for CI safety
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Fields that will hold richer types as later v0.2 changes land
# (peer-config-v01 → PeerConfig; linter-context-v01 → Linter; etc.) are typed
# as `Any` here so PeerDeps stays import-safe today AND so RunContext[PeerDeps]
# can rebuild its Pydantic validator without forward-reference resolution.
# Each downstream change tightens these to real types when it ships.


# Module-level safety flag. Mutate from test fixtures / conftest.py:
#
#     import peer.deps
#     peer.deps.ALLOW_LLM_CALLS = False
#
# Real Reviewers (ClaudeReviewer, OpenAIReviewer) check this before any
# LLM SDK invocation and raise LLMCallsDisabled when False.
ALLOW_LLM_CALLS: bool = True


@dataclass
class PeerDeps:
    """Per-run dependencies an Agent uses to review a PR.

    All fields are Optional with safe defaults. Fields land as additional
    capability changes ship (`peer-config-v01` populates `config`,
    `linter-context-v01` populates `linters`, etc.). Constructing an empty
    `PeerDeps()` is always safe — the Agent uses default fallbacks for
    unset fields.
    """

    config: Any = None  # PeerConfig once peer-config-v01 lands
    classifier: Any = None  # CommentClassifier
    taxonomy: Any = None  # Taxonomy
    enrichment: Any = None  # EnrichmentStep
    linters: list[Any] = field(default_factory=list)  # list[Linter] once linter-context-v01 lands
    extra_instructions: str | None = None
