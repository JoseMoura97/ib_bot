from __future__ import annotations

from datetime import datetime

import pandas as pd

from quiver_engine import QuiverStrategyEngine


def test_13f_get_signals_uses_edgar_first(monkeypatch):
    eng = QuiverStrategyEngine(api_key="DUMMY")

    # Avoid any network attempts for "official strategies".
    monkeypatch.setattr(eng, "_fetch_official_strategy", lambda name: [])

    # Simulate "no Quiver premium" path by raising if called.
    if hasattr(eng, "quiver") and hasattr(eng.quiver, "sec13F"):
        monkeypatch.setattr(eng.quiver, "sec13F", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("no premium")))

    # Provide EDGAR holdings.
    df = pd.DataFrame(
        {
            "Ticker": ["AAPL", "MSFT", "GOOGL"],
            "Value": [3_000_000, 2_000_000, 1_000_000],
        }
    )
    monkeypatch.setattr(eng.sec_edgar, "get_latest_holdings", lambda fund_name: df)

    tickers = eng.get_signals("Michael Burry")
    assert set(tickers) == {"AAPL", "MSFT", "GOOGL"}


def test_13f_time_travel_uses_edgar(monkeypatch):
    eng = QuiverStrategyEngine(api_key="DUMMY")

    called: dict[str, object] = {}

    def _as_of(fund_name: str, as_of_date: datetime):
        called["fund_name"] = fund_name
        called["as_of_date"] = as_of_date
        return pd.DataFrame({"Ticker": ["AAPL"], "Value": [1_000_000]})

    monkeypatch.setattr(eng.sec_edgar, "get_holdings_as_of_date", _as_of)

    as_of = datetime(2022, 8, 15)
    df = eng._get_raw_data_with_metadata_at_date("Michael Burry", as_of_date=as_of, lookback_days=999)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert called["fund_name"] == "Scion Asset Management"
    assert called["as_of_date"] == as_of

