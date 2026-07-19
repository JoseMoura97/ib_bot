from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import Mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import backtest_engine
from backtest_engine import BacktestEngine


def _price_frame() -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", "2020-02-01", freq="D")
    return pd.DataFrame(
        {
            "Open": range(100, 100 + len(dates)),
            "High": range(101, 101 + len(dates)),
            "Low": range(99, 99 + len(dates)),
            "Close": range(100, 100 + len(dates)),
            "Volume": [1_000] * len(dates),
        },
        index=dates,
    )


def test_large_yfinance_request_uses_complete_cache_without_download(
    tmp_path, monkeypatch
):
    backtest_engine._yf_ticker_cache.clear()
    yf_dir = tmp_path / "yf_prices"
    ib_dir = tmp_path / "ib_prices"
    yf_dir.mkdir()
    ib_dir.mkdir()

    tickers = [f"CACHE{i:02d}" for i in range(12)]
    for ticker in tickers:
        _price_frame().to_pickle(yf_dir / f"{ticker}.pkl")

    download = Mock(side_effect=AssertionError("warm cache must bypass Yahoo"))
    monkeypatch.setattr(backtest_engine.yf, "download", download)

    engine = BacktestEngine(price_source="yfinance")
    engine._yf_cache_dir = str(yf_dir)
    engine._ib_cache_dir = str(ib_dir)
    result = engine.fetch_historical_data(
        tickers,
        start_date="2020-01-02",
        end_date="2020-01-31",
    )

    assert set(result) == set(tickers)
    download.assert_not_called()
    assert engine.last_fallback_counts == {
        "ib_hit": 0,
        "yfinance_hit": 0,
        "cache_hit": len(tickers),
        "all_failed": 0,
    }


def test_yfinance_memory_cache_is_lru_bounded(tmp_path, monkeypatch):
    backtest_engine._yf_ticker_cache.clear()
    monkeypatch.setenv("YF_MEMORY_CACHE_MAX_TICKERS", "3")

    yf_dir = tmp_path / "yf_prices"
    yf_dir.mkdir()
    engine = BacktestEngine(price_source="yfinance")
    engine._yf_cache_dir = str(yf_dir)

    tickers = [f"LRU{i}" for i in range(5)]
    for ticker in tickers:
        _price_frame().to_pickle(yf_dir / f"{ticker}.pkl")
        assert engine._load_yf_cache(ticker) is not None

    assert list(backtest_engine._yf_ticker_cache) == tickers[-3:]
