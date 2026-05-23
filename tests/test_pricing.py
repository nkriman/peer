"""Tests for peer.eval.pricing."""

from __future__ import annotations

import pytest

from peer.eval.pricing import (
    PRICING,
    cost_unavailable_reason,
    estimate_cost,
)


def test_estimate_cost_known_haiku():
    # 1M input + 1M output at (1.0, 5.0) USD per MTok
    cost = estimate_cost("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
    assert cost == pytest.approx(6.0)


def test_estimate_cost_known_opus():
    cost = estimate_cost("claude-opus-4-7", 1_000_000, 1_000_000)
    assert cost == pytest.approx(90.0)  # 15 + 75


def test_estimate_cost_small_token_count():
    cost = estimate_cost("claude-sonnet-4-6", 1000, 500)
    # 1000/1M * 3 + 500/1M * 15 = 0.003 + 0.0075 = 0.0105
    assert cost == pytest.approx(0.0105)


def test_estimate_cost_zero_tokens():
    cost = estimate_cost("claude-haiku-4-5-20251001", 0, 0)
    assert cost == 0.0


def test_estimate_cost_unknown_returns_none():
    assert estimate_cost("not-a-real-model", 1000, 1000) is None


@pytest.mark.parametrize("model", list(PRICING.keys()))
def test_estimate_cost_all_known_models_return_float(model):
    cost = estimate_cost(model, 100, 100)
    assert isinstance(cost, float)
    assert cost > 0


def test_cost_unavailable_reason_mentions_model():
    msg = cost_unavailable_reason("mystery-model")
    assert "mystery-model" in msg
