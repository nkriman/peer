"""Hand-maintained per-token pricing table for cost estimation.

Last updated: 2026-05-23. Prices are USD per million tokens (MTok).
Update this table when new models are released or prices change.
"""

from __future__ import annotations

PRICING_TABLE_DATE = "2026-05-23"

# model_id -> (input_per_mtok_usd, output_per_mtok_usd)
PRICING: dict[str, tuple[float, float]] = {
    # Anthropic Claude family
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    # OpenAI family
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimate USD cost for a single LLM call, or None if model unknown."""
    entry = PRICING.get(model)
    if entry is None:
        return None
    in_per_mtok, out_per_mtok = entry
    return (input_tokens / 1_000_000.0) * in_per_mtok + (output_tokens / 1_000_000.0) * out_per_mtok


def cost_unavailable_reason(model: str) -> str:
    """Human-readable explanation of why cost could not be computed."""
    return f"model {model!r} not in pricing table (last updated {PRICING_TABLE_DATE})"
