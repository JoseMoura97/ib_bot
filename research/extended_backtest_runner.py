"""
Extended backtest — maximum available history.

13F strategies:  2016-01-01 → 2026-05-18  (~10yr, ~40 quarterly rebalances)
FINRA Monthly:   2018-10-01 → 2026-05-18  (~7.5yr, ~90 monthly rebalances)

Price source: cache_only — tickers absent from cache are skipped (conservative bias).
13F data: fetched live from SEC EDGAR and cached locally on first access.

Outputs: research/extended_backtest_results.json
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime

sys.path.insert(0, "/app")
os.environ.setdefault("PRICE_SOURCE", "cache_only")

from rebalancing_backtest_engine import RebalancingBacktestEngine  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")

# 13F strategies — 2016 start covers Tepper/Li Lu from first filing,
# Druckenmiller/Marks from mid-career (plenty of history).
STRATEGIES_13F = [
    ("Howard Marks",          datetime(2016, 1, 1), datetime(2026, 5, 18)),
    ("Stanley Druckenmiller", datetime(2016, 1, 1), datetime(2026, 5, 18)),
    ("David Tepper",          datetime(2016, 1, 1), datetime(2026, 5, 18)),
    ("Li Lu",                 datetime(2016, 1, 1), datetime(2026, 5, 18)),
    ("Michael Burry",         datetime(2016, 1, 1), datetime(2026, 5, 18)),
]

# FINRA Monthly — FINRA CDN starts 2018-08-01; give 2-month buffer.
STRATEGIES_FINRA = [
    ("Off-Exchange Short Squeeze (Monthly)", datetime(2018, 10, 1), datetime(2026, 5, 18)),
]

ALL = STRATEGIES_13F + STRATEGIES_FINRA
INITIAL = 100_000


def summarize(res: dict, name: str, start: datetime, end: datetime) -> dict:
    if not res or res.get("error"):
        return {"error": res.get("error") if res else "no result",
                "start": start.isoformat(), "end": end.isoformat()}
    yrs = (end - start).days / 365.25
    trades = res.get("trades")
    n_trades = trades if isinstance(trades, int) else len(trades or [])
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "years": round(yrs, 2),
        "cagr": res.get("cagr"),
        "sharpe": res.get("sharpe_ratio"),
        "sortino": res.get("sortino_ratio"),
        "max_drawdown": res.get("max_drawdown"),
        "total_return": res.get("total_return"),
        "volatility": res.get("volatility"),
        "return_1y": res.get("return_1y"),
        "alpha": res.get("alpha"),
        "beta": res.get("beta"),
        "final_value": res.get("final_value"),
        "n_trades": n_trades,
    }


def run_one(engine, name, start, end) -> dict:
    t0 = time.time()
    try:
        res = engine.run_rebalancing_backtest(
            strategy_name=name, start_date=start, end_date=end
        )
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[:400]}
    s = summarize(res, name, start, end)
    s["elapsed_sec"] = round(time.time() - t0, 1)
    return s


def main():
    engine = RebalancingBacktestEngine(
        quiver_api_key=os.getenv("QUIVER_API_KEY", ""),
        initial_capital=INITIAL,
        price_source="cache_only",
    )

    out: dict[str, dict] = {}
    total = len(ALL)

    for i, (name, start, end) in enumerate(ALL, 1):
        yrs = (end - start).days / 365.25
        print(f"\n[{i}/{total}] {name}  ({start.date()} → {end.date()}, {yrs:.1f}yr)", flush=True)
        out[name] = run_one(engine, name, start, end)
        s = out[name]
        if "error" in s:
            print(f"    ERROR: {s['error'][:120]}")
        else:
            cagr = s.get("cagr")
            sh = s.get("sharpe")
            dd = s.get("max_drawdown")
            alpha = s.get("alpha")
            cagr_s = f"{cagr*100:.2f}%" if isinstance(cagr, (int, float)) else "—"
            sh_s   = f"{sh:.2f}"         if isinstance(sh, (int, float)) else "—"
            dd_s   = f"{dd*100:.2f}%"    if isinstance(dd, (int, float)) else "—"
            al_s   = f"{alpha*100:.1f}%" if isinstance(alpha, (int, float)) else "—"
            print(f"    CAGR={cagr_s}  Sharpe={sh_s}  MaxDD={dd_s}  Alpha={al_s}"
                  f"  trades={s.get('n_trades')}  ({s['elapsed_sec']}s)")

    path = os.path.join(os.path.dirname(__file__), "extended_backtest_results.json")
    with open(path, "w") as f:
        json.dump(
            {"as_of": datetime.utcnow().isoformat() + "Z",
             "initial_capital": INITIAL,
             "results": out},
            f, indent=2, default=str,
        )
    print(f"\nWrote {path}")

    # Summary table
    print(f"\n{'Strategy':<38} {'Yrs':>4} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} {'Alpha':>7}")
    print("-" * 74)
    for name, s in out.items():
        if "error" in s:
            print(f"{name:<38}  ERROR")
            continue
        yr  = s.get("years", "—")
        cagr = s.get("cagr"); sh = s.get("sharpe"); dd = s.get("max_drawdown"); al = s.get("alpha")
        print(f"{name:<38} {yr:>4.1f}"
              f"  {cagr*100:>6.2f}%" if isinstance(cagr,(int,float)) else f"{name:<38} {yr:>4}  —",
              end="")
        if isinstance(cagr,(int,float)):
            print(f"  {sh:>6.2f}  {dd*100:>6.2f}%  {al*100:>5.1f}%" if isinstance(sh,(int,float)) else "")


if __name__ == "__main__":
    main()
