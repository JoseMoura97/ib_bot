"""Tests for portfolio optimization methods."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.portfolio_math import (
    compare_all_methods,
    optimize_equal_weight,
    optimize_inverse_volatility,
    optimize_max_sharpe,
    optimize_portfolio,
    optimize_risk_parity,
)


def _make_curves(n: int = 4, days: int = 500, seed: int = 42) -> dict[str, pd.Series]:
    rng = np.random.RandomState(seed)
    idx = pd.bdate_range("2020-01-01", periods=days)
    curves = {}
    for i in range(n):
        drift = 0.0003 + i * 0.0001
        vol = 0.01 + i * 0.003
        returns = rng.normal(drift, vol, days)
        prices = 100.0 * np.cumprod(1 + returns)
        curves[f"Strategy_{i+1}"] = pd.Series(prices, index=idx)
    return curves


class TestEqualWeight:
    def test_produces_valid_weights(self):
        curves = _make_curves(4)
        result = optimize_equal_weight(curves)
        assert "error" not in result
        assert result["method"] == "equal_weight"
        weights = result["weights"]
        assert len(weights) == 4
        assert abs(sum(weights.values()) - 1.0) < 1e-6
        for w in weights.values():
            assert abs(w - 0.25) < 1e-6

    def test_empty_curves_returns_error(self):
        result = optimize_equal_weight({})
        assert "error" in result


class TestInverseVolatility:
    def test_produces_valid_weights(self):
        curves = _make_curves(4)
        result = optimize_inverse_volatility(curves)
        assert "error" not in result
        assert result["method"] == "inverse_volatility"
        weights = result["weights"]
        assert len(weights) == 4
        assert abs(sum(weights.values()) - 1.0) < 1e-6
        for w in weights.values():
            assert w >= 0

    def test_lower_vol_gets_higher_weight(self):
        curves = _make_curves(4)
        result = optimize_inverse_volatility(curves, max_weight=1.0, min_weight=0.0)
        weights = result["weights"]
        assert weights["Strategy_1"] > weights["Strategy_4"]

    def test_respects_max_weight_constraint(self):
        curves = _make_curves(2)
        result = optimize_inverse_volatility(curves, max_weight=0.6)
        for w in result["weights"].values():
            assert w <= 0.6 + 1e-6


class TestRiskParity:
    def test_produces_valid_weights(self):
        curves = _make_curves(4)
        result = optimize_risk_parity(curves)
        assert "error" not in result
        assert result["method"] == "risk_parity"
        weights = result["weights"]
        assert len(weights) == 4
        assert abs(sum(weights.values()) - 1.0) < 1e-4

    def test_weights_within_bounds(self):
        curves = _make_curves(4)
        result = optimize_risk_parity(curves, max_weight=0.40, min_weight=0.05)
        for w in result["weights"].values():
            assert w >= 0.05 - 1e-6
            assert w <= 0.40 + 1e-6


class TestMaxSharpe:
    def test_produces_valid_weights(self):
        curves = _make_curves(4)
        result = optimize_max_sharpe(curves)
        assert "error" not in result
        assert result["method"] == "max_sharpe"
        weights = result["weights"]
        assert len(weights) == 4
        assert abs(sum(weights.values()) - 1.0) < 1e-4

    def test_weights_within_bounds(self):
        curves = _make_curves(4)
        result = optimize_max_sharpe(curves, max_weight=0.35, min_weight=0.05)
        for w in result["weights"].values():
            assert w >= 0.05 - 1e-6
            assert w <= 0.35 + 1e-6

    def test_stats_include_sharpe(self):
        curves = _make_curves(4)
        result = optimize_max_sharpe(curves)
        assert "stats" in result
        assert "sharpe" in result["stats"]
        assert "annual_return" in result["stats"]
        assert "annual_vol" in result["stats"]


class TestDispatcher:
    def test_unknown_method_returns_error(self):
        curves = _make_curves(2)
        result = optimize_portfolio(curves, "nonexistent_method")
        assert "error" in result

    def test_all_methods_via_dispatcher(self):
        curves = _make_curves(3)
        for method in ["equal_weight", "inverse_volatility", "risk_parity", "max_sharpe"]:
            result = optimize_portfolio(curves, method)
            assert "error" not in result, f"{method} returned error: {result}"
            assert abs(sum(result["weights"].values()) - 1.0) < 1e-4


class TestCompareAll:
    def test_returns_four_methods(self):
        curves = _make_curves(3)
        results = compare_all_methods(curves)
        assert len(results) == 4
        methods = {r["method"] for r in results}
        assert methods == {"equal_weight", "inverse_volatility", "risk_parity", "max_sharpe"}

    def test_all_weights_sum_to_one(self):
        curves = _make_curves(3)
        results = compare_all_methods(curves)
        for r in results:
            assert abs(sum(r["weights"].values()) - 1.0) < 1e-4
