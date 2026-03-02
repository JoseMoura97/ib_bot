"""
Compare equal-weight vs amount-weight portfolio mirror strategies.

Runs backtests for the 5 politician portfolio mirror strategies with both
weighting methods and prints a comparison table with QuiverQuant reference values.
"""

import json
import os
import sys
import time
import warnings
from datetime import datetime
from unittest.mock import patch

import pandas as pd
from dotenv import load_dotenv

from quiver_signals import QuiverSignals
from rebalancing_backtest_engine import RebalancingBacktestEngine
from strategy_replicator import StrategyReplicator

warnings.filterwarnings("ignore")

QUIVER_REFERENCE = {
    "Nancy Pelosi":       {"cagr": 34.99},
    "Dan Meuser":         {"cagr": 38.16},
    "Josh Gottheimer":    {"cagr": 23.48},
    "Donald Beyer":       {"cagr": 18.22},
    "Sheldon Whitehouse": {"cagr": 15.70},
    "Congress Buys":      {"cagr": 33.44},
    "Congress Sells":     {"cagr": 35.14},
    "Congress Long-Short":{"cagr": 20.17},
}

POLITICIAN_STRATEGIES = [
    "Nancy Pelosi",
    "Dan Meuser",
    "Josh Gottheimer",
    "Donald Beyer",
    "Sheldon Whitehouse",
]

OTHER_STRATEGIES = [
    "Congress Buys",
    "Congress Sells",
    "Congress Long-Short",
]


def run_backtest_with_weighting(bt, qs, strategy_name, weighting_mode):
    """Run a single backtest with the specified weighting mode."""
    info = qs.get_strategy_info(strategy_name)
    if not info or not info.get("start_date"):
        return None

    start_date = datetime.fromisoformat(info["start_date"])
    end_date = datetime.now()

    original_fn = StrategyReplicator.get_strategy_config.__func__

    def patched_config(strategy_nm):
        cfg = original_fn(strategy_nm)
        if strategy_nm == strategy_name and cfg.get("type") == "portfolio_mirror":
            cfg["weighting"] = weighting_mode
            cfg["mirror_mode"] = "latest_action"
        return cfg

    with patch.object(StrategyReplicator, "get_strategy_config", staticmethod(patched_config)):
        result = bt.run_rebalancing_backtest(
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
        )

    if result and "error" not in result:
        return {
            "strategy": strategy_name,
            "weighting": weighting_mode,
            "cagr": result.get("cagr", 0) * 100,
            "sharpe": result.get("sharpe_ratio", 0),
            "max_drawdown": result.get("max_drawdown", 0) * 100,
            "volatility": result.get("volatility", 0) * 100,
            "n_days": result.get("n_days", 0),
            "start_date": result.get("start_date", ""),
            "end_date": result.get("end_date", ""),
        }
    return None


def run_backtest_other(bt, qs, strategy_name):
    """Run backtest for non-politician strategies (no weighting override)."""
    info = qs.get_strategy_info(strategy_name)
    if not info or not info.get("start_date"):
        return None

    start_date = datetime.fromisoformat(info["start_date"])
    end_date = datetime.now()

    result = bt.run_rebalancing_backtest(
        strategy_name=strategy_name,
        start_date=start_date,
        end_date=end_date,
    )

    if result and "error" not in result:
        return {
            "strategy": strategy_name,
            "weighting": "default",
            "cagr": result.get("cagr", 0) * 100,
            "sharpe": result.get("sharpe_ratio", 0),
            "max_drawdown": result.get("max_drawdown", 0) * 100,
            "volatility": result.get("volatility", 0) * 100,
            "n_days": result.get("n_days", 0),
            "start_date": result.get("start_date", ""),
            "end_date": result.get("end_date", ""),
        }
    return None


def main():
    load_dotenv()
    api_key = os.getenv("QUIVER_API_KEY")
    if not api_key:
        print("ERROR: QUIVER_API_KEY not set in .env")
        sys.exit(1)

    os.environ.setdefault("PRICE_SOURCE", "auto")
    os.environ["PYTHONUNBUFFERED"] = "1"

    qs = QuiverSignals(api_key)
    bt = RebalancingBacktestEngine(
        quiver_api_key=api_key,
        initial_capital=100000,
        transaction_cost_bps=0.0,
        price_source="auto",
    )

    results = []
    total = len(POLITICIAN_STRATEGIES) * 2 + len(OTHER_STRATEGIES)
    done = 0

    print("=" * 100)
    print("WEIGHTING COMPARISON: Equal-Weight vs Amount-Weight")
    print("=" * 100)

    # Run politician strategies with both weightings
    for name in POLITICIAN_STRATEGIES:
        for mode in ("equal", "amount"):
            done += 1
            print(f"\n[{done}/{total}] {name} ({mode}-weight)...")
            t0 = time.time()
            r = run_backtest_with_weighting(bt, qs, name, mode)
            elapsed = time.time() - t0
            if r:
                results.append(r)
                print(f"  CAGR={r['cagr']:.1f}%  Sharpe={r['sharpe']:.2f}  MaxDD={r['max_drawdown']:.1f}%  ({elapsed:.0f}s)")
            else:
                print(f"  FAILED ({elapsed:.0f}s)")

    # Run other strategies with default config
    for name in OTHER_STRATEGIES:
        done += 1
        print(f"\n[{done}/{total}] {name} (default)...")
        t0 = time.time()
        r = run_backtest_other(bt, qs, name)
        elapsed = time.time() - t0
        if r:
            results.append(r)
            print(f"  CAGR={r['cagr']:.1f}%  Sharpe={r['sharpe']:.2f}  MaxDD={r['max_drawdown']:.1f}%  ({elapsed:.0f}s)")
        else:
            print(f"  FAILED ({elapsed:.0f}s)")

    # Print comparison table
    print("\n\n" + "=" * 100)
    print("COMPARISON TABLE")
    print("=" * 100)
    print(f"{'Strategy':<25} {'Weight':<10} {'CAGR':>8} {'Sharpe':>8} {'MaxDD':>8} {'Quiver':>8} {'Gap':>8}")
    print("-" * 100)

    # Group results by strategy
    by_strat = {}
    for r in results:
        by_strat.setdefault(r["strategy"], []).append(r)

    for name in POLITICIAN_STRATEGIES + OTHER_STRATEGIES:
        runs = by_strat.get(name, [])
        quiver_cagr = QUIVER_REFERENCE.get(name, {}).get("cagr")
        for r in runs:
            gap = ""
            if quiver_cagr is not None:
                gap_val = r["cagr"] - quiver_cagr
                gap = f"{gap_val:+.1f}pp"
            q_str = f"{quiver_cagr:.1f}%" if quiver_cagr is not None else "N/A"
            print(
                f"{r['strategy']:<25} {r['weighting']:<10} "
                f"{r['cagr']:>7.1f}% {r['sharpe']:>7.2f} {r['max_drawdown']:>7.1f}% "
                f"{q_str:>8} {gap:>8}"
            )
        if len(runs) > 1:
            print()

    # Determine winner for each politician strategy
    print("\n" + "=" * 100)
    print("RECOMMENDATION")
    print("=" * 100)
    for name in POLITICIAN_STRATEGIES:
        runs = by_strat.get(name, [])
        quiver_cagr = QUIVER_REFERENCE.get(name, {}).get("cagr")
        if len(runs) >= 2 and quiver_cagr is not None:
            equal_r = next((r for r in runs if r["weighting"] == "equal"), None)
            amount_r = next((r for r in runs if r["weighting"] == "amount"), None)
            if equal_r and amount_r:
                equal_gap = abs(equal_r["cagr"] - quiver_cagr)
                amount_gap = abs(amount_r["cagr"] - quiver_cagr)
                winner = "amount" if amount_gap < equal_gap else "equal"
                print(
                    f"  {name:<25} -> {winner:<8} "
                    f"(equal gap={equal_gap:.1f}pp, amount gap={amount_gap:.1f}pp)"
                )

    # Save results
    os.makedirs(".cache", exist_ok=True)
    output = {
        "generated_at": datetime.now().isoformat(),
        "results": results,
        "quiver_reference": {k: v for k, v in QUIVER_REFERENCE.items()},
    }
    with open(".cache/weighting_comparison.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to .cache/weighting_comparison.json")


if __name__ == "__main__":
    main()
