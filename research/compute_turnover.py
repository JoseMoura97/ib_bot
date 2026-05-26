"""
Compute per-strategy turnover stats from existing backtest result JSON.

Output: research/turnover_stats.json
    strategy -> {
        n_trades, n_rebalances (est.), avg_trades_per_rebalance,
        rebalance_frequency, basket_size_est
    }

This isn't perfect because the engine returns "trades" as a number that conflates
buy + sell legs, but it's enough to flag which strategies are turnover-heavy.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(__file__)

# Coarse rebalance-event count per strategy, given a 3yr window (2023-05 → 2026-05).
# Sources: quiver_strategy_rules.STRATEGY_RULES.rebalance_frequency
N_EVENTS_3YR = {
    # 13F mirrors — quarterly, ~12 events over 3yr (more if filed-date schedule splits)
    "Michael Burry": 12, "Bill Ackman": 12, "Howard Marks": 12,
    "Stanley Druckenmiller": 12, "David Tepper": 12, "Seth Klarman": 12,
    "Mohnish Pabrai": 12, "Li Lu": 12, "Chuck Akre": 12,
    "Warren Buffett": 12, "David Einhorn": 12, "Dan Loeb": 12,
    "Tiger Global": 12, "Coatue": 12, "Sequoia Fund": 12,
    # Weekly Mon rebalance
    "Off-Exchange Short Squeeze": 156,
}

# Approximate basket sizes (target top-N per strategy)
BASKET_SIZE = {
    "Off-Exchange Short Squeeze": 20,
    "Warren Buffett": 20, "Tiger Global": 25, "Coatue": 25,
    # default for un-capped 13F mirrors — actual count varies by filing
    "_default_13f": 30,
}


def main():
    with open(os.path.join(HERE, "tier2_backtest_results.json")) as f:
        backtest = json.load(f)
    finra_path = os.path.join(HERE, "finra_short_result.json")
    if os.path.exists(finra_path):
        with open(finra_path) as f:
            finra = json.load(f)
        backtest["results"]["Off-Exchange Short Squeeze"] = finra

    out = {}
    for name, r in backtest["results"].items():
        if r.get("error"):
            continue
        n_trades = r.get("n_trades")
        if not isinstance(n_trades, int):
            continue
        n_events = N_EVENTS_3YR.get(name)
        basket = BASKET_SIZE.get(name, BASKET_SIZE["_default_13f"])
        avg_per_event = n_trades / n_events if n_events else None
        # Turnover% = (trades_per_event / 2) / basket_size — divide by 2 because n_trades
        # appears to count buy+sell legs together; this gives the fraction of basket churned.
        turnover_pct = (avg_per_event / 2 / basket * 100) if avg_per_event else None
        out[name] = {
            "n_trades": n_trades,
            "n_events_est": n_events,
            "basket_size_est": basket,
            "avg_trades_per_rebalance": round(avg_per_event, 1) if avg_per_event else None,
            "turnover_pct_per_rebal": round(turnover_pct, 1) if turnover_pct else None,
        }

    path = os.path.join(HERE, "turnover_stats.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {path}")
    # Sorted preview
    rows = sorted(out.items(), key=lambda kv: kv[1].get("turnover_pct_per_rebal") or 0, reverse=True)
    print(f"\n{'Strategy':<28} {'trades':>8} {'/rebal':>8} {'turnover/rebal':>16}")
    print("-" * 64)
    for name, s in rows:
        tu = s.get("turnover_pct_per_rebal")
        tu_s = f"{tu:.0f}%" if tu else "—"
        print(f"{name:<28} {s['n_trades']:>8} {s.get('avg_trades_per_rebalance','—'):>8} {tu_s:>16}")


if __name__ == "__main__":
    main()
