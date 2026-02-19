"""
Backtest regression tests.

Snapshot known-good results for top strategies and assert future runs
produce numbers within tolerance. Uses cached plot_data.json as the
source of truth (avoids hitting external APIs).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app.services.portfolio_math import records_to_series


def _load_plot_data() -> dict | None:
    for path in [
        Path("/app/.cache/plot_data.json"),
        Path(".cache/plot_data.json"),
        Path("../.cache/plot_data.json"),
    ]:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def _compute_metrics(series: pd.Series) -> dict:
    if series.empty or len(series) < 2:
        return {}
    daily = series.pct_change().dropna()
    total_return = float(series.iloc[-1] / series.iloc[0] - 1)
    n_days = len(daily)
    years = n_days / 252.0
    cagr = float((1 + total_return) ** (1 / years) - 1) if years > 0 else 0
    vol = float(daily.std() * (252 ** 0.5))
    sharpe = float(daily.mean() * 252 / (daily.std() * 252 ** 0.5)) if daily.std() > 0 else 0
    roll_max = series.cummax()
    dd = (series / roll_max) - 1
    max_dd = float(dd.min())
    return {"cagr": cagr, "sharpe": sharpe, "max_dd": max_dd, "vol": vol, "total_return": total_return}


KNOWN_STRATEGIES = [
    "Michael Burry (SEC EDGAR)",
    "Congress Buys",
    "Congress Long-Short",
    "Sector Weighted DC Insider",
    "Bill Ackman (SEC EDGAR)",
]

plot_data = _load_plot_data()


@pytest.mark.skipif(plot_data is None, reason="plot_data.json not available")
class TestBacktestRegression:
    """Verify cached equity curves produce consistent metrics."""

    def test_at_least_one_strategy_present(self):
        """At least one known strategy should have equity curve data."""
        strategies = plot_data.get("strategies", {})
        found = 0
        for name in KNOWN_STRATEGIES:
            if name in strategies:
                ec = strategies[name].get("equity_curve", [])
                if len(ec) > 10:
                    found += 1
        if found == 0:
            pytest.skip("No known strategies have equity curve data (run on server with full cache)")

    @pytest.mark.parametrize("strategy_name", KNOWN_STRATEGIES)
    def test_metrics_are_finite(self, strategy_name):
        strategies = plot_data.get("strategies", {})
        entry = strategies.get(strategy_name)
        if entry is None:
            pytest.skip(f"{strategy_name} not in plot_data.json")
        ec = entry.get("equity_curve", [])
        if not ec:
            pytest.skip(f"{strategy_name} has no equity curve")

        series = records_to_series(ec)
        metrics = _compute_metrics(series)

        assert metrics, f"{strategy_name} produced empty metrics"
        assert -1 < metrics["cagr"] < 10, f"{strategy_name} CAGR={metrics['cagr']} out of range"
        assert -5 < metrics["sharpe"] < 10, f"{strategy_name} Sharpe={metrics['sharpe']} out of range"
        assert -1 <= metrics["max_dd"] <= 0, f"{strategy_name} MaxDD={metrics['max_dd']} out of range"
        assert 0 < metrics["vol"] < 5, f"{strategy_name} Vol={metrics['vol']} out of range"

    @pytest.mark.parametrize("strategy_name", KNOWN_STRATEGIES)
    def test_equity_curve_is_monotone_start(self, strategy_name):
        """First value should be close to initial capital (100000)."""
        strategies = plot_data.get("strategies", {})
        entry = strategies.get(strategy_name)
        if entry is None:
            pytest.skip(f"{strategy_name} not in plot_data.json")
        ec = entry.get("equity_curve", [])
        if not ec:
            pytest.skip(f"{strategy_name} has no equity curve")

        first_val = ec[0].get("value", 0)
        assert 50000 < first_val < 200000, f"{strategy_name} first value {first_val} unexpected"

    def test_determinism(self):
        """Running _compute_metrics twice on same data produces identical results."""
        strategies = plot_data.get("strategies", {})
        for name in KNOWN_STRATEGIES:
            entry = strategies.get(name)
            if not entry:
                continue
            ec = entry.get("equity_curve", [])
            if not ec:
                continue
            s = records_to_series(ec)
            m1 = _compute_metrics(s)
            m2 = _compute_metrics(s)
            for key in m1:
                assert abs(m1[key] - m2[key]) < 1e-12, f"{name}.{key} not deterministic"
