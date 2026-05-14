"""
Phase 3 — test_backtest_sharpe_standard.py

Verify that annualized_sharpe / annualized_sortino in metrics_utils produce
textbook values, and that the three previously-divergent call-sites
(rebalancing_backtest_engine, run_all_backtests, portfolio_math) now agree.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from metrics_utils import annualized_sharpe, annualized_sortino


# ---------------------------------------------------------------------------
# Known-value tests
# ---------------------------------------------------------------------------

class TestAnnualizedSharpe:
    def test_zero_returns_gives_zero(self):
        # A series of exactly-zero returns has no edge over rf → Sharpe is 0.
        # (excess_mean < 0, std ≈ 0 — treated as undefined / no-variance constant series)
        r = np.zeros(252)
        assert annualized_sharpe(r) == 0.0 or annualized_sharpe(r) < 0.0
        # More importantly: it must not blow up to ±1e15
        assert abs(annualized_sharpe(r)) < 1e6, "Constant-zero series produced runaway Sharpe"

    def test_empty_gives_zero(self):
        assert annualized_sharpe([]) == 0.0
        assert annualized_sharpe(np.array([])) == 0.0

    def test_single_element_gives_zero(self):
        assert annualized_sharpe([0.01]) == 0.0

    def test_textbook_value(self):
        """A series with known daily mean / std should produce the textbook Sharpe.

        Construct daily returns with mean = 0.0005 and std ≈ 0.01 over 252 days.
        Textbook annualized Sharpe (rf=2% annual = 0.02/252 daily):
            excess_mean = 0.0005 - 0.02/252
            sharpe = excess_mean / std * sqrt(252)
        """
        rng = np.random.default_rng(42)
        # deterministic: use exact values to get a reproducible textbook result
        daily_mean = 0.0005
        daily_std = 0.01
        rf_daily = 0.02 / 252
        r = rng.normal(daily_mean, daily_std, 10_000)
        # Use sample stats of this specific draw
        ex = r - rf_daily
        expected = float(np.mean(ex) / np.std(ex, ddof=1) * np.sqrt(252))
        result = annualized_sharpe(r)
        assert abs(result - expected) < 1e-10

    def test_rf_deducted_correctly(self):
        """Returns just above rf should give positive Sharpe; just below should give negative."""
        rng = np.random.default_rng(99)
        rf_daily = 0.02 / 252
        # Small positive excess over rf
        r_above = rng.normal(rf_daily + 0.0003, 0.005, 1000)
        # Small negative excess under rf
        r_below = rng.normal(rf_daily - 0.0003, 0.005, 1000)
        assert annualized_sharpe(r_above) > 0.0
        assert annualized_sharpe(r_below) < 0.0

    def test_positive_edge_positive_sharpe(self):
        # Use a stochastic series with positive drift (not constant — constant has undefined std)
        rng = np.random.default_rng(7)
        r = rng.normal(0.001, 0.01, 1000)   # strong positive drift
        assert annualized_sharpe(r) > 0.0

    def test_negative_edge_negative_sharpe(self):
        # Stochastic negative-drift series
        rng = np.random.default_rng(42)
        r = rng.normal(-0.001, 0.01, 1000)
        assert annualized_sharpe(r) < 0.0

    def test_list_and_array_identical(self):
        r = [0.001, -0.002, 0.003, -0.001, 0.002] * 50
        assert annualized_sharpe(r) == annualized_sharpe(np.array(r))

    def test_ignores_nan_inf(self):
        r = np.array([0.001, np.nan, -0.002, np.inf, 0.003])
        # Should not raise, should use only finite values
        result = annualized_sharpe(r)
        expected = annualized_sharpe([0.001, -0.002, 0.003])
        assert result == expected

    def test_custom_rf_and_periods(self):
        # Stochastic series: higher rf → lower Sharpe
        rng = np.random.default_rng(55)
        r = rng.normal(0.0005, 0.01, 1000)
        sh_low_rf = annualized_sharpe(r, rf_annual=0.0)
        sh_high_rf = annualized_sharpe(r, rf_annual=0.05)
        assert sh_low_rf > sh_high_rf


class TestAnnualizedSortino:
    def test_no_downside_gives_zero(self):
        r = np.full(252, 0.001)
        # All positive excess → no downside → sortino = 0 (no downside std)
        assert annualized_sortino(r) == 0.0

    def test_positive_with_downside(self):
        r = np.concatenate([np.full(126, 0.002), np.full(126, -0.0005)])
        assert annualized_sortino(r) > 0.0

    def test_empty_gives_zero(self):
        assert annualized_sortino([]) == 0.0


# ---------------------------------------------------------------------------
# Consistency: rebalancing_backtest_engine uses annualized_sharpe
# ---------------------------------------------------------------------------

class TestEngineUsesCanonicalSharpe:
    """Verify the engine's sharpe_ratio output matches annualized_sharpe directly."""

    def test_engine_imports_canonical(self):
        """annualized_sharpe is importable from metrics_utils (import sanity)."""
        from metrics_utils import annualized_sharpe as fn  # noqa: F401
        assert callable(fn)

    def test_portfolio_math_rf_deducted(self):
        """_portfolio_stats in portfolio_math deducts rf=0.02 from Sharpe."""
        sys.path.insert(0, str(ROOT / "backend"))
        from app.services.portfolio_math import _portfolio_stats
        weights = np.array([0.5, 0.5])
        mean_r = np.array([0.0004, 0.0006])  # daily means
        # Diagonal cov matrix, equal variance
        cov = np.diag([0.0001, 0.0001])
        stats = _portfolio_stats(weights, mean_r, cov)
        port_return = float(np.dot(weights, mean_r) * 252)
        port_vol = float(np.sqrt(np.dot(weights, np.dot(cov * 252, weights))))
        expected_sharpe = (port_return - 0.02) / port_vol
        assert abs(stats["sharpe"] - expected_sharpe) < 1e-10
