"""
Fetch and cache fundamental data for all tickers in the price cache.
Saves to /app/.cache/factor_fundamentals.pkl

Run once (takes ~10–20 min for 2634 tickers due to rate limiting).
Re-run to refresh.

Fields fetched per ticker (from yfinance .info):
  trailingPE, priceToBook, returnOnEquity, grossMargins,
  marketCap, totalDebt, assetGrowth (computed from balance sheet)
"""
from __future__ import annotations

import os
import sys
import time
import pickle
import traceback
from datetime import datetime

sys.path.insert(0, "/app")

import pandas as pd
import numpy as np
import yfinance as yf

CACHE_DIR  = "/app/.cache/yf_prices"
FUND_CACHE = "/app/.cache/factor_fundamentals.pkl"
BATCH_SIZE = 50      # tickers per yf.Tickers batch
DELAY      = 0.10    # seconds between batches

INFO_FIELDS = [
    "trailingPE",
    "forwardPE",
    "priceToBook",
    "returnOnEquity",
    "grossMargins",
    "operatingMargins",
    "marketCap",
    "sharesOutstanding",
    "totalRevenue",
    "revenueGrowth",
    "earningsGrowth",
    "debtToEquity",
    "currentRatio",
    "returnOnAssets",
    "trailingEps",
    "sector",
    "industry",
]


def get_tickers():
    return sorted([
        f.replace(".pkl", "")
        for f in os.listdir(CACHE_DIR)
        if f.endswith(".pkl")
    ])


def fetch_batch_info(tickers: list[str]) -> dict:
    """Fetch .info for a batch of tickers. Returns dict of {ticker: info_dict}."""
    results = {}
    try:
        batch_str = " ".join(tickers)
        yt = yf.Tickers(batch_str)
        for t in tickers:
            try:
                info = yt.tickers[t].info
                results[t] = {k: info.get(k) for k in INFO_FIELDS}
            except Exception:
                results[t] = {}
    except Exception as e:
        print(f"  batch error: {e}")
        for t in tickers:
            results[t] = {}
    return results


def fetch_asset_growth(tickers: list[str]) -> dict:
    """
    Compute YoY asset growth from balance sheet.
    asset_growth = (totalAssets_t / totalAssets_{t-1}) - 1
    Returns {ticker: float}.
    """
    results = {}
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            bs = tk.balance_sheet
            if bs is None or bs.empty:
                continue
            if "Total Assets" in bs.index:
                assets = bs.loc["Total Assets"].dropna().sort_index(ascending=False)
            elif "TotalAssets" in bs.index:
                assets = bs.loc["TotalAssets"].dropna().sort_index(ascending=False)
            else:
                continue
            if len(assets) >= 2:
                ag = float(assets.iloc[0]) / float(assets.iloc[1]) - 1.0
                if abs(ag) < 5.0:  # sanity: >500% growth is likely data error
                    results[t] = ag
        except Exception:
            pass
    return results


def main():
    tickers = get_tickers()
    total = len(tickers)
    print(f"Fetching fundamentals for {total} tickers → {FUND_CACHE}")
    print(f"Batch size {BATCH_SIZE}, delay {DELAY}s — estimated {total*DELAY/60:.0f} min")

    # Load existing cache if present
    existing: dict = {}
    if os.path.exists(FUND_CACHE):
        try:
            with open(FUND_CACHE, "rb") as f:
                df_existing = pickle.load(f)
            existing = df_existing.to_dict(orient="index")
            print(f"Loaded {len(existing)} existing entries from cache")
        except Exception as e:
            print(f"Could not load existing cache: {e}")

    # Fetch info in batches
    all_info: dict = dict(existing)
    to_fetch = [t for t in tickers if t not in all_info or not all_info[t].get("marketCap")]
    print(f"Fetching {len(to_fetch)} tickers (skipping {len(tickers)-len(to_fetch)} cached)")

    batches = [to_fetch[i:i+BATCH_SIZE] for i in range(0, len(to_fetch), BATCH_SIZE)]
    for bi, batch in enumerate(batches, 1):
        result = fetch_batch_info(batch)
        all_info.update(result)
        if bi % 10 == 0 or bi == len(batches):
            pct = (bi * BATCH_SIZE / len(to_fetch) * 100) if to_fetch else 100
            print(f"  [{bi}/{len(batches)}] {pct:.0f}% info done")
        time.sleep(DELAY)

    # Fetch asset growth for tickers with market cap > $1B (others not worth it)
    liquid = [t for t in tickers
              if all_info.get(t, {}).get("marketCap") and
              all_info[t]["marketCap"] > 1e9]
    print(f"\nFetching asset growth for {len(liquid)} liquid tickers...")
    ag_map = {}
    for i, t in enumerate(liquid):
        if t in existing and existing[t].get("assetGrowth") is not None:
            ag_map[t] = existing[t]["assetGrowth"]
            continue
        try:
            ag_result = fetch_asset_growth([t])
            ag_map.update(ag_result)
        except Exception:
            pass
        if i % 100 == 0 and i > 0:
            print(f"  asset growth: {i}/{len(liquid)}")
        time.sleep(DELAY * 2)

    # Merge asset growth into all_info
    for t, ag in ag_map.items():
        if t in all_info:
            all_info[t]["assetGrowth"] = ag
        else:
            all_info[t] = {"assetGrowth": ag}

    # Convert to DataFrame and save
    df = pd.DataFrame.from_dict(all_info, orient="index")
    df.index.name = "ticker"
    print(f"\nFundamentals coverage:")
    for col in ["trailingPE", "priceToBook", "returnOnEquity", "grossMargins",
                "marketCap", "assetGrowth"]:
        if col in df.columns:
            n = df[col].notna().sum()
            print(f"  {col:25s}: {n:4d}/{len(df)} ({n/len(df)*100:.0f}%)")

    with open(FUND_CACHE, "wb") as f:
        pickle.dump(df, f, protocol=4)
    print(f"\nSaved {len(df)} tickers to {FUND_CACHE}")


if __name__ == "__main__":
    main()
