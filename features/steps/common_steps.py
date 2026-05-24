"""Shared step definitions for peer's BDD scenarios.

Capability-specific steps live in features/steps/<capability>_steps.py.
When behave reports an undefined step, it prints a stub — paste it here or in
the capability-specific file and implement.

Two patterns we use:
- `@step("a freshly constructed quality framework")` — concrete smoke step.
- `@step("the scenario is pending implementation")` — explicit "not yet wired"
  marker so the Stop hook nudges us to write the real step.
"""

from __future__ import annotations

from behave import given, then, when  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Smoke step — keeps `behave --tags=@fast` green even with no extracted features.
# ---------------------------------------------------------------------------


@given("a freshly constructed quality framework")
def step_given_quality_framework(context) -> None:
    context.subject = {"ok": True}


@when("no action is taken")
def step_when_noop(context) -> None:
    context.result = context.subject


@then("no error is raised")
def step_then_no_error(context) -> None:
    if context.error is not None:
        raise AssertionError(f"expected no error, got: {context.error!r}")


# ---------------------------------------------------------------------------
# Explicit pending marker — for scenarios auto-extracted from OpenSpec that
# don't yet have step defs. behave will fail these, which is intentional:
# the Stop hook nudges you to either implement the step or move the scenario
# off the @fast tag.
# ---------------------------------------------------------------------------


@then("the scenario is pending implementation")
def step_then_pending(context) -> None:
    raise AssertionError("scenario pending implementation — add step defs in features/steps/")
