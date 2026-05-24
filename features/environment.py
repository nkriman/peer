"""behave environment hooks for peer's BDD layer.

Scenarios are auto-extracted from openspec/changes/**/specs/ into features/*.feature.
Step definitions live in features/steps/ and bind WHEN/THEN phrases to Python.

This file is loaded by behave before any scenarios run. Use it for:
- per-feature setup/teardown
- shared context fixtures (e.g., mock clients) attached to `context`
"""

from __future__ import annotations

from typing import Any


def before_all(context: Any) -> None:
    """Run once before any scenario."""
    context.config.setup_logging()


def before_feature(context: Any, feature: Any) -> None:
    """Reset shared state before each feature."""
    context.fixtures = {}


def before_scenario(context: Any, scenario: Any) -> None:
    """Reset per-scenario state — no leakage between scenarios."""
    context.result = None
    context.error = None
    context.subject = None


def after_scenario(context: Any, scenario: Any) -> None:
    """Surface useful debug info when a scenario fails."""
    if scenario.status == "failed" and context.error is not None:
        print(f"[behave] scenario error: {context.error!r}")
    # Restore globals that scenarios may flip but not roll back.
    # The negative-path scenarios for ALLOW_LLM_CALLS leave the flag at
    # False if they don't reach their own try/finally — that bleeds into
    # subsequent scenarios across features.
    from peer import deps as _peer_deps

    _peer_deps.ALLOW_LLM_CALLS = True

    # claude-code-everywhere-v01 scenarios flip PEER_USE_CLAUDE_CODE; reset
    # so it doesn't leak into other features that construct SDK clients.
    import os as _os

    _os.environ.pop("PEER_USE_CLAUDE_CODE", None)
