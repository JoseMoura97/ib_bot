"""
Preliminary 3yr backtest runner for the 12 new Tier 2 13F mirror strategies.
Cached prices only (PRICE_SOURCE=cache_only), no Quiver historical re-fetch.

Outputs:
  research/tier2_backtest_results.json
  research/tier2_backtest_report.html  (dark theme)
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
log = logging.getLogger(__name__)

STRATEGIES = [
    "Stanley Druckenmiller",
    "David Tepper",
    "Seth Klarman",
    "Mohnish Pabrai",
    "Li Lu",
    "Chuck Akre",
    "Warren Buffett",
    "David Einhorn",
    "Dan Loeb",
    "Tiger Global",
    "Coatue",
    "Sequoia Fund",
]

# Existing baselines for comparison
BASELINES = ["Michael Burry", "Bill Ackman", "Howard Marks"]

END = datetime(2026, 5, 18)
START = datetime(2023, 5, 18)
INITIAL_CAPITAL = 100_000


def summarize(res: dict) -> dict:
    """Pull the headline metrics out of the engine's run dict."""
    if not res or res.get("error"):
        return {"error": res.get("error") if res else "no result"}
    return {
        "cagr": res.get("cagr"),
        "sharpe": res.get("sharpe_ratio"),
        "sortino": res.get("sortino_ratio"),
        "max_drawdown": res.get("max_drawdown"),
        "total_return": res.get("total_return"),
        "volatility": res.get("volatility"),
        "return_1y": res.get("return_1y"),
        "alpha": res.get("alpha"),
        "beta": res.get("beta"),
        "info_ratio": res.get("info_ratio"),
        "win_rate": res.get("win_rate"),
        "benchmark_return_1y": res.get("benchmark_return_1y"),
        "n_trades": res.get("trades") if isinstance(res.get("trades"), int) else len(res.get("trades") or []),
        "n_days": res.get("n_days"),
        "final_value": res.get("final_value"),
    }


def run_one(engine: RebalancingBacktestEngine, name: str) -> dict:
    t0 = time.time()
    try:
        res = engine.run_rebalancing_backtest(
            strategy_name=name,
            start_date=START,
            end_date=END,
        )
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}
    sm = summarize(res)
    sm["elapsed_sec"] = round(time.time() - t0, 2)
    return sm


def main() -> None:
    engine = RebalancingBacktestEngine(
        quiver_api_key=os.getenv("QUIVER_API_KEY", ""),
        initial_capital=INITIAL_CAPITAL,
        price_source="cache_only",
    )

    out: dict[str, dict] = {}
    all_names = STRATEGIES + BASELINES

    for i, name in enumerate(all_names, start=1):
        print(f"[{i}/{len(all_names)}] {name} ...", flush=True)
        out[name] = run_one(engine, name)
        s = out[name]
        if "error" in s:
            print(f"    ERROR: {s['error']}")
        else:
            cagr = s.get("cagr")
            sh = s.get("sharpe")
            dd = s.get("max_drawdown")
            cagr_s = f"{cagr*100:.2f}%" if isinstance(cagr, (int, float)) else str(cagr)
            sh_s = f"{sh:.2f}" if isinstance(sh, (int, float)) else str(sh)
            dd_s = f"{dd*100:.2f}%" if isinstance(dd, (int, float)) else str(dd)
            print(f"    CAGR={cagr_s} Sharpe={sh_s} maxDD={dd_s} rebs={s.get('n_rebalances')} ({s['elapsed_sec']}s)")

    out_path = os.path.join(os.path.dirname(__file__), "tier2_backtest_results.json")
    with open(out_path, "w") as f:
        json.dump(
            {
                "as_of": datetime.utcnow().isoformat() + "Z",
                "start": START.isoformat(),
                "end": END.isoformat(),
                "initial_capital": INITIAL_CAPITAL,
                "price_source": "cache_only",
                "results": out,
            },
            f,
            indent=2,
            default=str,
        )
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
