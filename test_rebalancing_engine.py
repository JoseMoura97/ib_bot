"""
Test suite for RebalancingBacktestEngine.

Runs a small set of strategies and prints our results vs Quiver published metrics.
"""

import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from quiver_signals import QuiverSignals
from rebalancing_backtest_engine import RebalancingBacktestEngine


def _pct_str(x: float) -> str:
    return f"{x * 100:.2f}%"


def _parse_pct_str(s: str) -> float | None:
    if not isinstance(s, str):
        return None
    s = s.strip()
    if not s.endswith("%"):
        return None
    try:
        return float(s[:-1])
    except Exception:
        return None


def main() -> None:
    load_dotenv()
    api_key = os.getenv("QUIVER_API_KEY")
    if not api_key:
        raise SystemExit("QUIVER_API_KEY is required")

    qs = QuiverSignals(api_key)
    engine = RebalancingBacktestEngine(quiver_api_key=api_key, initial_capital=100000, transaction_cost_bps=0.0)

    end = datetime.now()
    start = end - timedelta(days=365)

    strategies = [
        "Congress Buys",
        "Congress Sells",
        "Congress Long-Short",
        "U.S. House Long-Short",
        "Transportation and Infra. Committee (House)",
    ]

    print("=" * 110)
    print(f"Rebalancing backtests: {start.date()} to {end.date()}")
    print("=" * 110)
    print(f"{'Strategy':<40} {'Quiver_CAGR':>12} {'Our_CAGR':>12} {'Diff':>10} {'Our_Sharpe':>12} {'Quiver_Sharpe':>14}")
    print("-" * 110)

    for name in strategies:
        info = qs.get_strategy_info(name) or {}
        quiver_cagr_s = info.get("cagr")
        quiver_sharpe = info.get("sharpe")

        res = engine.run_rebalancing_backtest(
            strategy_name=name,
            start_date=start,
            end_date=end,
        )

        if "error" in res:
            print(f"{name:<40} {'N/A':>12} {'ERROR':>12} {'':>10} {'':>12} {'':>14}  ({res['error']})")
            continue

        our_cagr_pct = res["cagr"] * 100
        our_sharpe = res["sharpe_ratio"]

        q_cagr_pct = _parse_pct_str(quiver_cagr_s)
        diff = (our_cagr_pct - q_cagr_pct) if q_cagr_pct is not None else None

        diff_str = f"{diff:+.2f}%" if diff is not None else "N/A"
        print(
            f"{name:<40} "
            f"{(quiver_cagr_s or 'N/A'):>12} "
            f"{our_cagr_pct:>11.2f}% "
            f"{diff_str:>10} "
            f"{our_sharpe:>11.2f} "
            f"{(quiver_sharpe if quiver_sharpe is not None else 'N/A'):>14}"
        )

    print("-" * 110)
    print("Note: Quiver CAGR is full-period; this script uses a 1Y window for faster iteration.")


if __name__ == "__main__":
    main()

