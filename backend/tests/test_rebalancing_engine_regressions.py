from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from rebalancing_backtest_engine import RebalancingBacktestEngine


def _fake_prices(start: datetime, end: datetime, tickers: list[str]) -> dict[str, pd.DataFrame]:
    # Simple deterministic “up only” price series for all tickers.
    idx = pd.date_range(start=start, end=end, freq="B")  # business days
    out: dict[str, pd.DataFrame] = {}
    for i, t in enumerate(tickers):
        base = 100.0 + i
        # Linear growth: +0.01% per day
        close = pd.Series(base * (1.0 + 0.0001) ** np.arange(len(idx)), index=idx, name="Close")
        out[t] = pd.DataFrame({"Close": close})
    return out


def test_portfolio_mirror_latest_action_equal_weight(monkeypatch):
    """
    Portfolio-mirror strategies should infer "currently held" tickers using the latest action
    (buy vs sell) per ticker, then equal-weight holdings.
    """
    start = datetime(2020, 1, 1)
    end = datetime(2020, 2, 1)

    bt = RebalancingBacktestEngine(quiver_api_key="DUMMY", initial_capital=100000.0, transaction_cost_bps=0.0)

    # Force a simple on-trade schedule by returning a few dated rows.
    def _raw_at_date(strategy_name: str, as_of_date: datetime, lookback_days: int = 90):
        return pd.DataFrame(
            {
                "Ticker": ["AAA", "AAA", "BBB"],
                "Transaction": ["Purchase", "Sale", "Buy"],
                "TransactionDate": [datetime(2020, 1, 5), datetime(2020, 1, 20), datetime(2020, 1, 10)],
                "Amount": [1000, 1000, 1000],
            }
        )

    monkeypatch.setattr(bt.quiver, "_get_raw_data_with_metadata_at_date", _raw_at_date)

    # Override pricer to avoid network.
    def _fetch(tickers, start_date, end_date, progress_callback=None):
        s = pd.to_datetime(start_date).to_pydatetime()
        e = pd.to_datetime(end_date).to_pydatetime()
        return _fake_prices(s, e, list(tickers))

    monkeypatch.setattr(bt.pricer, "fetch_historical_data", _fetch)

    res = bt.run_rebalancing_backtest(strategy_name="Nancy Pelosi", start_date=start, end_date=end)
    assert "error" not in res
    # AAA last action is Sale -> excluded. BBB last action is Buy -> included.
    # The easiest assertion is: weights should never include AAA at the start of simulation window.
    # We check by looking at the first rebalance event weights through the engine's private method.
    events = bt._generate_rebalance_events("Nancy Pelosi", start, end)
    assert events
    w0 = events[0].weights
    assert "BBB" in w0
    assert "AAA" not in w0
    assert abs(sum(w0.values()) - 1.0) < 1e-9


def test_cagr_uses_intended_window_not_equity_span(monkeypatch):
    """
    CAGR should be computed using (end - start) to avoid inflation when early periods are skipped.
    """
    start = datetime(2020, 1, 1)
    end = start + timedelta(days=365)

    bt = RebalancingBacktestEngine(quiver_api_key="DUMMY", initial_capital=100000.0, transaction_cost_bps=0.0)

    # Produce weights only near the end, so most of the period has no returns.
    def _raw_at_date(strategy_name: str, as_of_date: datetime, lookback_days: int = 90):
        if as_of_date < (end - timedelta(days=30)):
            return pd.DataFrame(columns=["Ticker", "Transaction", "TransactionDate", "Amount"])
        return pd.DataFrame(
            {
                "Ticker": ["AAA"],
                "Transaction": ["Purchase"],
                "TransactionDate": [end - timedelta(days=10)],
                "Amount": [1000],
            }
        )

    monkeypatch.setattr(bt.quiver, "_get_raw_data_with_metadata_at_date", _raw_at_date)

    def _fetch(tickers, start_date, end_date, progress_callback=None):
        s = pd.to_datetime(start_date).to_pydatetime()
        e = pd.to_datetime(end_date).to_pydatetime()
        return _fake_prices(s, e, list(tickers))

    monkeypatch.setattr(bt.pricer, "fetch_historical_data", _fetch)

    res = bt.run_rebalancing_backtest(strategy_name="Nancy Pelosi", start_date=start, end_date=end)
    assert "error" not in res
    # Because we only have exposure for ~30 days, CAGR over the full year should be modest.
    assert res["cagr"] < 0.10

