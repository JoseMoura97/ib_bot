"""
Fetch point-in-time quarterly fundamentals for the Quality factor.

Eliminates look-ahead bias by storing historical ROE and gross margins per
quarter rather than a static today-snapshot.

Output: /app/.cache/factor_historical_fundamentals.pkl
Format: {ticker: DataFrame(index=period_end_dates, cols=['gross_margin','roe'])}

The index dates are *period end* dates (e.g. 2024-09-30).
score_quality() applies a 60-day reporting lag before using these, so
a 2024-09-30 quarter is only visible to rebalances on or after 2024-11-29.

Run inside Docker (takes 30-60 min for ~2600 tickers):
  docker exec ib_bot-worker-1 python3 /app/research/factor_fundamentals_historical_fetch.py

Re-run to refresh/extend.
"""
from __future__ import annotations

import math
import os
import pickle
import sys
import time
import traceback

sys.path.insert(0, "/app")

import pandas as pd
import yfinance as yf

CACHE_DIR = "/app/.cache/yf_prices"
OUT_PATH  = "/app/.cache/factor_historical_fundamentals.pkl"
DELAY     = 0.20  # seconds between tickers (stay under rate limits)


def get_tickers() -> list[str]:
    return sorted([
        f.replace(".pkl", "")
        for f in os.listdir(CACHE_DIR)
        if f.endswith(".pkl")
    ])


def _safe(df: pd.DataFrame, field: str, col) -> float | None:
    """Extract a single finite float from a DataFrame cell, or None."""
    if df is None or df.empty:
        return None
    if field not in df.index or col not in df.columns:
        return None
    v = df.loc[field, col]
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _first_match(df: pd.DataFrame, fields: list[str], col) -> float | None:
    for field in fields:
        v = _safe(df, field, col)
        if v is not None:
            return v
    return None


def fetch_ticker_history(ticker: str) -> pd.DataFrame | None:
    """
    Returns DataFrame(index=period_end_dates, cols=['gross_margin','roe'])
    using yfinance quarterly income statement + balance sheet.
    Returns None if no usable data.
    """
    try:
        tk = yf.Ticker(ticker)
        inc = tk.quarterly_income_stmt   # rows=items, cols=period dates
        bs  = tk.quarterly_balance_sheet

        if inc is None or inc.empty:
            return None

        rows = []
        for col in inc.columns:
            gm = roe = None

            # Gross margin
            gp = _first_match(inc, ["Gross Profit", "GrossProfit"], col)
            tr = _first_match(inc, ["Total Revenue", "TotalRevenue"], col)
            if gp is not None and tr is not None and tr != 0:
                gm = gp / tr

            # ROE = annualised quarterly Net Income / Stockholders Equity
            ni = _first_match(inc, ["Net Income", "NetIncome",
                                     "Net Income Common Stockholders"], col)
            eq = _first_match(bs, [
                "Stockholders Equity",
                "Common Stock Equity",
                "Total Equity Gross Minority Interest",
            ], col) if bs is not None else None
            if ni is not None and eq is not None and eq != 0:
                roe = (ni * 4) / eq  # annualise single quarter

            if gm is not None or roe is not None:
                rows.append({
                    "date": pd.Timestamp(col),
                    "gross_margin": gm,
                    "roe": roe,
                })

        if not rows:
            return None

        df = pd.DataFrame(rows).set_index("date").sort_index()
        return df

    except Exception:
        return None


def main():
    tickers = get_tickers()
    total   = len(tickers)
    print(f"Fetching historical fundamentals for {total} tickers → {OUT_PATH}")
    print(f"Delay {DELAY}s/ticker — estimated {total * DELAY / 60:.0f} min")

    # Load existing cache for incremental runs
    result: dict = {}
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH, "rb") as f:
                result = pickle.load(f)
            print(f"Loaded {len(result)} existing entries (will skip already fetched)")
        except Exception as e:
            print(f"Could not load existing cache: {e}")

    to_fetch = [t for t in tickers if t not in result]
    print(f"Need to fetch: {len(to_fetch)} tickers")

    for i, t in enumerate(to_fetch):
        try:
            df = fetch_ticker_history(t)
            result[t] = df
        except Exception as e:
            result[t] = None

        if (i + 1) % 200 == 0:
            with open(OUT_PATH, "wb") as f:
                pickle.dump(result, f, protocol=4)
            pct = (i + 1) / len(to_fetch) * 100
            covered = sum(1 for v in result.values() if v is not None)
            print(f"  [{i+1}/{len(to_fetch)}] {pct:.0f}% done — {covered} with data")

        time.sleep(DELAY)

    with open(OUT_PATH, "wb") as f:
        pickle.dump(result, f, protocol=4)

    covered = sum(1 for v in result.values() if v is not None and not v.empty)
    print(f"\nDone. {covered}/{total} tickers have historical fundamental data.")
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
