"""
Cost-sensitivity sweep for FINRA Off-Exchange Short Squeeze.

Engine defaults: 5bps round-trip commission + 2.5bps slippage per side = 10bps total per turnover.
We sweep round-trip commission ∈ {0, 5, 15, 30} (paired with 2.5bps slippage/side) to bracket:
  - 0bps total  → "gross" upper bound (no costs at all)
  - 10bps total → current default (realistic IB tiered for liquid mid-caps)
  - 20bps total → conservative (typical mid-cap spread + small-account commission)
  - 35bps total → pessimistic (sub-$1B microcap, wide spreads, $1 min commission drag)

Also re-runs Howard Marks (best baseline) at the same costs so the reader sees how
costs hit a low-turnover strategy vs the high-churn FINRA strategy.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, "/app")
os.environ.setdefault("PRICE_SOURCE", "cache_only")

from rebalancing_backtest_engine import RebalancingBacktestEngine  # noqa: E402

logging.basicConfig(level=logging.WARNING)

START = datetime(2023, 5, 18)
END = datetime(2026, 5, 18)
INITIAL = 100_000

# (label, transaction_cost_bps round-trip, slippage_bps_per_side)
COST_GRID = [
    ("gross (no costs)",        0.0,  0.0),
    ("default 10bps",           5.0,  2.5),
    ("conservative 20bps",     10.0,  5.0),
    ("pessimistic 35bps",      20.0,  7.5),
]

STRATEGIES = ["Off-Exchange Short Squeeze", "Howard Marks", "Seth Klarman", "Michael Burry"]


def summarize(r):
    if not r or r.get("error"):
        return {"error": r.get("error") if r else "no result"}
    trades = r.get("trades")
    n_trades = trades if isinstance(trades, int) else len(trades or [])
    return {
        "cagr": r.get("cagr"),
        "sharpe": r.get("sharpe_ratio"),
        "max_drawdown": r.get("max_drawdown"),
        "vol": r.get("volatility"),
        "return_1y": r.get("return_1y"),
        "alpha": r.get("alpha"),
        "beta": r.get("beta"),
        "final_value": r.get("final_value"),
        "n_trades": n_trades,
    }


def main():
    out = {"start": START.isoformat(), "end": END.isoformat(), "results": {}}
    for strat in STRATEGIES:
        out["results"][strat] = []
        print(f"\n{strat}")
        print("-" * 90)
        for label, cost_bps, slip_bps in COST_GRID:
            engine = RebalancingBacktestEngine(
                quiver_api_key=os.getenv("QUIVER_API_KEY", ""),
                initial_capital=INITIAL,
                price_source="cache_only",
                transaction_cost_bps=cost_bps,
                slippage_bps_per_side=slip_bps,
            )
            t0 = time.time()
            try:
                r = engine.run_rebalancing_backtest(strategy_name=strat, start_date=START, end_date=END)
            except Exception as e:
                r = {"error": f"{type(e).__name__}: {e}"}
            s = summarize(r)
            s["label"] = label
            s["total_cost_bps"] = cost_bps + 2 * slip_bps
            s["elapsed_sec"] = round(time.time() - t0, 1)
            out["results"][strat].append(s)
            cagr = s.get("cagr")
            shp = s.get("sharpe")
            cagr_s = f"{cagr*100:>6.2f}%" if isinstance(cagr, (int, float)) else " err  "
            shp_s = f"{shp:>5.2f}" if isinstance(shp, (int, float)) else " err"
            print(f"  {label:<24} cost={s['total_cost_bps']:>5.1f}bps  CAGR={cagr_s}  Sharpe={shp_s}  trades={s.get('n_trades')}  ({s['elapsed_sec']}s)")

    path = os.path.join(os.path.dirname(__file__), "cost_sensitivity_results.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
