"""
Run all factor investing backtests.

Steps:
  1. Fetch fundamentals (if not cached)
  2. Run 9 factor variants × 3yr window
  3. Save results JSON
  4. Print summary table

Run inside Docker:
  docker exec ib_bot-worker-1 python3 /app/research/factor_backtest_runner.py
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, "/app")
os.environ.setdefault("PRICE_SOURCE", "cache_only")

import pandas as pd

from research.factor_engine import FactorEngine
from research.factor_backtest import FactorBacktest

START_3YR = "2023-05-18"
END_3YR   = "2026-05-18"

FACTORS = [
    ("Momentum",          "momentum"),
    ("Low Volatility",    "low_vol"),
    ("Value",             "value"),
    ("Quality",           "quality"),
    ("Investment (CMA)",  "investment"),
    ("Size (SMB)",        "size"),
    ("Mom + LowVol",      "momentum_lowvol"),
    ("Quality + Value",   "quality_value"),
    ("Multi-Factor",      "multi"),
]

SPY_3YR_CAGR   = 0.2228
SPY_3YR_SHARPE = 1.05
SPY_3YR_MAXDD  = -0.1876

FUND_CACHE = "/app/.cache/factor_fundamentals.pkl"
OUT_PATH   = os.path.join(os.path.dirname(__file__), "factor_backtest_results.json")


def ensure_fundamentals():
    if os.path.exists(FUND_CACHE):
        size_mb = os.path.getsize(FUND_CACHE) / 1e6
        print(f"Found fundamentals cache ({size_mb:.1f} MB) — skipping re-fetch")
        return

    print("No fundamentals cache found. Fetching from yfinance…")
    print("(This takes ~10-20 min for ~2600 tickers)")
    try:
        from research.factor_fundamentals_fetch import main as fetch_main
        fetch_main()
    except Exception as e:
        print(f"Fundamentals fetch failed: {e}")
        print("Continuing without fundamental factors (Value/Quality/Investment/Size will be skipped)")


def run_factor(fb: FactorBacktest, label: str, factor: str) -> dict:
    t0 = time.time()
    print(f"  Running {label}…", end="", flush=True)
    try:
        result = fb.run(
            factor=factor,
            start=START_3YR,
            end=END_3YR,
            n=20,
            cost_bps=10,
            verbose=False,
        )
    except Exception as ex:
        result = {"error": str(ex)}
    elapsed = time.time() - t0

    if "error" in result:
        print(f" ERROR: {result['error'][:80]}")
    else:
        print(
            f" CAGR={result.get('cagr',0)*100:.2f}%"
            f"  Sharpe={result.get('sharpe',0):.2f}"
            f"  MaxDD={result.get('max_drawdown',0)*100:.2f}%"
            f"  α={result.get('alpha',0)*100:.1f}%"
            f"  ({elapsed:.1f}s)"
        )

    # Drop equity curve from JSON (too large)
    result.pop("equity_curve", None)
    result["label"] = label
    result["elapsed_sec"] = round(elapsed, 1)
    return result


def main():
    ensure_fundamentals()

    fb = FactorBacktest(
        min_universe_history_days=300,
        min_avg_volume=0,   # don't filter by volume (we have diverse cache)
    )

    print(f"\nRunning {len(FACTORS)} factor backtests ({START_3YR} → {END_3YR})")
    print("-" * 70)

    results = {}
    for label, factor in FACTORS:
        r = run_factor(fb, label, factor)
        results[label] = r

    # Save JSON
    out = {
        "as_of": pd.Timestamp.utcnow().isoformat() + "Z",
        "window": {"start": START_3YR, "end": END_3YR},
        "spy_benchmark": {
            "cagr": SPY_3YR_CAGR,
            "sharpe": SPY_3YR_SHARPE,
            "max_drawdown": SPY_3YR_MAXDD,
        },
        "results": results,
    }

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWrote {OUT_PATH}")

    # Summary table
    print(f"\n{'Factor':25s} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} {'Alpha':>7} {'Beta':>6}")
    print("-" * 64)
    sorted_results = sorted(
        [(k, v) for k, v in results.items() if "error" not in v],
        key=lambda x: x[1].get("cagr", -99),
        reverse=True,
    )
    for label, r in sorted_results:
        cagr  = r.get("cagr", 0) * 100
        sh    = r.get("sharpe", 0)
        dd    = r.get("max_drawdown", 0) * 100
        alpha = r.get("alpha", 0) * 100
        beta  = r.get("beta", 0)
        print(f"{label:25s} {cagr:7.2f}%  {sh:6.2f}  {dd:7.2f}%  {alpha:6.1f}%  {beta:5.2f}")

    for label, r in results.items():
        if "error" in r:
            print(f"{label:25s}  ERROR: {r['error'][:60]}")

    print(f"\nSPY benchmark:          {SPY_3YR_CAGR*100:7.2f}%  {SPY_3YR_SHARPE:6.2f}  {SPY_3YR_MAXDD*100:7.2f}%")


if __name__ == "__main__":
    main()
