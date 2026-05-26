"""
Full cost-sensitivity sweep for the top strategies by risk-adjusted alpha.

Selection criteria: positive CAPM alpha + defensible interpretation
(excludes high-beta tech-concentration outliers Coatue/Tiger/Klarman).

Strategies:
  Howard Marks       — alpha +8.1%,  beta 0.84  (defensive, genuine alpha)
  Michael Burry      — alpha +13.1%, beta 0.73  (low beta, concentrated value)
  Stanley Druckenmiller — alpha +14.5%, beta 1.12 (CINS-fixed, macro)
  Li Lu              — alpha +9.6%,  beta 0.98  (concentrated long-term value)
  David Tepper       — alpha +9.6%,  beta 1.15  (macro, diversified)
  FINRA Monthly      — alpha +6.7%,  beta 0.63  (uncorrelated signal)

Cost grid:
  gross (0 bps)       → upper bound, no costs at all
  default (10 bps)    → 5 bps commission + 2.5 bps slippage/side
  conservative (20 bps)
  pessimistic (35 bps)

Runs sequentially with a short pause between strategies to avoid
saturating the EPYC (current load ~101/96 cores).

Output: research/cost_sweep_top_results.json
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

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")

START = datetime(2023, 5, 18)
END = datetime(2026, 5, 18)
INITIAL = 100_000

# (label, commission_bps_round_trip, slippage_bps_per_side)
COST_GRID = [
    ("gross (0 bps)",        0.0,  0.0),
    ("default (10 bps)",     5.0,  2.5),
    ("conservative (20 bps)",10.0, 5.0),
    ("pessimistic (35 bps)", 20.0, 7.5),
]

STRATEGIES = [
    "Howard Marks",
    "Michael Burry",
    "Stanley Druckenmiller",
    "Li Lu",
    "David Tepper",
    "Off-Exchange Short Squeeze (Monthly)",
]

# Seconds to sleep between strategies — gives the OS scheduler time to
# breathe on a loaded EPYC; backtest is mostly single-threaded so this
# doesn't change wall-clock much but keeps load spikes from stacking.
INTER_STRATEGY_PAUSE = 3


def summarize(r: dict) -> dict:
    if not r or r.get("error"):
        return {"error": r.get("error") if r else "no result"}
    trades = r.get("trades")
    n_trades = trades if isinstance(trades, int) else len(trades or [])
    return {
        "cagr": r.get("cagr"),
        "sharpe": r.get("sharpe_ratio"),
        "sortino": r.get("sortino_ratio"),
        "max_drawdown": r.get("max_drawdown"),
        "volatility": r.get("volatility"),
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
        print(f"\n{'='*70}")
        print(f"  {strat}")
        print(f"{'='*70}")
        print(f"  {'Label':<26} {'Cost':>6} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} {'Trades':>7} {'Time':>6}")
        print(f"  {'-'*68}")

        for label, comm_bps, slip_bps in COST_GRID:
            engine = RebalancingBacktestEngine(
                quiver_api_key=os.getenv("QUIVER_API_KEY", ""),
                initial_capital=INITIAL,
                price_source="cache_only",
                transaction_cost_bps=comm_bps,
                slippage_bps_per_side=slip_bps,
            )
            t0 = time.time()
            try:
                r = engine.run_rebalancing_backtest(
                    strategy_name=strat, start_date=START, end_date=END
                )
            except Exception as e:
                r = {"error": f"{type(e).__name__}: {e}"}

            s = summarize(r)
            s["label"] = label
            s["total_cost_bps"] = comm_bps + 2 * slip_bps
            s["elapsed_sec"] = round(time.time() - t0, 1)
            out["results"][strat].append(s)

            cagr = s.get("cagr")
            sh = s.get("sharpe")
            dd = s.get("max_drawdown")
            cagr_s = f"{cagr*100:>6.2f}%" if isinstance(cagr, (int, float)) else "  err  "
            sh_s = f"{sh:>6.2f}" if isinstance(sh, (int, float)) else "  err "
            dd_s = f"{dd*100:>6.2f}%" if isinstance(dd, (int, float)) else "  err  "
            print(
                f"  {label:<26} {s['total_cost_bps']:>5.0f}bp"
                f"  {cagr_s}  {sh_s}  {dd_s}"
                f"  {str(s.get('n_trades','—')):>6}"
                f"  {s['elapsed_sec']:>4.1f}s"
            )

        # Pause between strategies to avoid piling up load
        if strat != STRATEGIES[-1]:
            time.sleep(INTER_STRATEGY_PAUSE)

    path = os.path.join(os.path.dirname(__file__), "cost_sweep_top_results.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
