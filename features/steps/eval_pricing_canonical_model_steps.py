"""Step definitions for features/eval_pricing_canonical_model.feature (peer-edz)."""

from __future__ import annotations

from behave import then, when  # type: ignore[import-untyped]

from peer.eval.pricing import estimate_cost


@when('I call estimate_cost with model "{model}", input_tokens {it:d}, output_tokens {ot:d}')
def step_call_estimate_cost(context, model: str, it: int, ot: int) -> None:
    context.fixtures["cost"] = estimate_cost(model, it, ot)


@then("the returned cost equals {val:f}")
def step_cost_equals(context, val: float) -> None:
    got = context.fixtures["cost"]
    assert got == val, f"expected {val}, got {got!r}"


@then("the returned cost is None")
def step_cost_is_none(context) -> None:
    got = context.fixtures["cost"]
    assert got is None, f"expected None, got {got!r}"
