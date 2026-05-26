"""
Track 1 — Multi-window backtests for best factor strategies.

Windows: 15yr (2011-06), 10yr (2016-05), 5yr (2021-05), 3yr (2023-05)
Factors: Momentum, Low Volatility, Mom+LowVol, Quality

Run inside Docker:
  docker exec ib_bot-worker-1 python3 /app/research/track1_backtest_runner.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

sys.path.insert(0, "/app")

from research.factor_backtest import FactorBacktest

END = "2026-05-18"

WINDOWS = [
    ("17yr", "2009-03-01"),
    ("15yr", "2011-06-01"),
    ("10yr", "2016-05-18"),
    ("5yr",  "2021-05-01"),
    ("3yr",  "2023-05-18"),
]

_HIST_FUND_AVAILABLE = os.path.exists("/app/.cache/factor_historical_fundamentals.pkl")

FACTORS = [
    ("Momentum",      "momentum",       False),
    ("Low Volatility","low_vol",         False),
    ("Mom+LowVol",    "momentum_lowvol", False),
    # look-ahead=False once historical fundamentals cache is built
    ("Quality",       "quality",         not _HIST_FUND_AVAILABLE),
]

OUT_PATH = os.path.join(os.path.dirname(__file__), "track1_results.json")


def fmt(m: dict) -> str:
    if "error" in m:
        return f"ERROR: {m['error']}"
    c = m.get("cagr", 0)
    s = m.get("sharpe", 0)
    d = m.get("max_drawdown", 0)
    a = m.get("alpha", 0)
    b = m.get("beta", 0)
    t = m.get("elapsed_sec", 0)
    return (f"CAGR={c*100:.1f}%  Sh={s:.2f}  DD={d*100:.1f}%"
            f"  α={a*100:.1f}%  β={b:.2f}  ({t:.0f}s)")


def main():
    total = len(WINDOWS) * len(FACTORS)
    print(f"Running {total} backtests (* = has look-ahead bias in fundamentals)")
    print("-" * 85)

    fb = FactorBacktest()
    results = {}

    for win_label, win_start in WINDOWS:
        results[win_label] = {}
        for factor_label, factor_key, look_ahead in FACTORS:
            bias = "*" if look_ahead else ""
            label = f"{factor_label}{bias} ({win_label})"
            print(f"  {label}...", end="", flush=True)
            t0 = time.time()
            try:
                m = fb.run(
                    factor=factor_key,
                    start=win_start,
                    end=END,
                    n=20,
                    cost_bps=10,
                )
                # Serialise equity curves (normalised to 100 at start)
                for key in ("equity_curve", "spy_curve"):
                    ec = m.pop(key, None)
                    if ec is not None and len(ec) > 0:
                        ec_norm = ec / ec.iloc[0] * 100
                        m[key] = {
                            "dates": [d.strftime("%Y-%m-%d") for d in ec_norm.index],
                            "values": [round(float(v), 2) for v in ec_norm.values],
                        }
                elapsed = time.time() - t0
                m["elapsed_sec"] = round(elapsed, 1)
                results[win_label][factor_label] = m
                print(f" {fmt(m)}")
            except Exception as e:
                elapsed = time.time() - t0
                err = {"error": f"{type(e).__name__}: {e}", "elapsed_sec": round(elapsed, 1)}
                results[win_label][factor_label] = err
                print(f" ERROR: {e}")
                traceback.print_exc()

    quality_look_ahead = next(la for lbl, _, la in FACTORS if lbl == "Quality")
    results["_meta"] = {"quality_look_ahead": quality_look_ahead}

    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved to {OUT_PATH}")
    print(f"Quality look-ahead bias: {'YES (static snapshot)' if quality_look_ahead else 'NO (historical data)'}")

    # Summary table
    print("\n── Summary ─────────────────────────────────────────────────────────────────────")
    print(f"{'Strategy':<22} {'15yr':>10} {'10yr':>10} {'5yr':>10} {'3yr':>10}")
    print("-" * 62)
    for factor_label, _, _ in FACTORS:
        row = f"{factor_label:<22}"
        for win_label, _ in WINDOWS:
            m = results.get(win_label, {}).get(factor_label, {})
            if "error" in m:
                row += f" {'ERR':>10}"
            else:
                c = m.get("cagr", 0) or 0
                row += f" {c*100:>9.1f}%"
        print(row)


if __name__ == "__main__":
    main()
