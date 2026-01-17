"""
Validate replication: RebalancingBacktestEngine vs Quiver published metrics.

Runs each strategy from QuiverSignals.start_date through today (or a capped window)
and compares:
  - CAGR
  - Sharpe
  - Max Drawdown

Note: Some strategies may be skipped if underlying data is unavailable.
"""

import os
import sys
from datetime import datetime
import json
from pathlib import Path

from dotenv import load_dotenv

from quiver_signals import QuiverSignals
from quiver_engine import QuiverStrategyEngine
from rebalancing_backtest_engine import RebalancingBacktestEngine


def _parse_pct(s):
    if not isinstance(s, str):
        return None
    s = s.strip()
    if not s.endswith("%"):
        return None
    try:
        return float(s[:-1])
    except Exception:
        return None


def _fmt_pct(x):
    if x is None:
        return "N/A"
    return f"{x:.2f}%"


def _fmt_float(x):
    if x is None:
        return "N/A"
    return f"{x:.3f}"


def _parse_pct_any(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip()
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except Exception:
        return None


def main():
    load_dotenv()
    api_key = os.getenv("QUIVER_API_KEY")
    if not api_key:
        raise SystemExit("QUIVER_API_KEY is required")

    lookback_override = os.getenv("LOOKBACK_DAYS_OVERRIDE")
    lookback_days_override = int(lookback_override) if lookback_override and lookback_override.strip() else None

    qs = QuiverSignals(api_key)
    qeng = QuiverStrategyEngine(api_key)
    bt = RebalancingBacktestEngine(
        quiver_api_key=api_key,
        initial_capital=100000,
        transaction_cost_bps=0.0,
        price_source=os.getenv("PRICE_SOURCE"),
    )

    end = datetime.now()

    # Strategies to validate (focus on those with explicit rules + available underlying data)
    default_candidates = [
        "Congress Buys",
        "Congress Sells",
        "Congress Long-Short",
        "U.S. House Long-Short",
        "Transportation and Infra. Committee (House)",
        "Top Lobbying Spenders",
        "Lobbying Spending Growth",
        "Top Gov Contract Recipients",
        "Sector Weighted DC Insider",
        "Nancy Pelosi",
        "Dan Meuser",
        "Josh Gottheimer",
        "Sheldon Whitehouse",
        "Donald Beyer",
        "Insider Purchases",
        "WSB Top 10",
        "Analyst Long",
        "House Natural Resources",
        "Energy and Commerce Committee (House)",
        "Homeland Security Committee (Senate)",
    ]
    candidates = sys.argv[1:] if len(sys.argv) > 1 else default_candidates
    out_path = Path(".cache") / "last_validation_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Merge into an existing cache if present (so you can run strategies incrementally)
    if out_path.exists():
        try:
            results_payload = json.loads(out_path.read_text(encoding="utf-8"))
            if not isinstance(results_payload, dict):
                results_payload = {}
        except Exception:
            results_payload = {}
    else:
        results_payload = {}
    results_payload.setdefault("benchmark", "SPY")
    results_payload["generated_at"] = datetime.utcnow().isoformat() + "Z"
    results_payload.setdefault("strategies", {})

    def _checkpoint_write() -> None:
        # Write partial progress so long validations can be resumed safely.
        try:
            out_path.write_text(json.dumps(results_payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    print("=" * 140)
    if lookback_days_override is None:
        print(f"Validation window: strategy start_date -> {end.date()}")
    else:
        print(f"Validation window: strategy start_date -> {end.date()} (LOOKBACK_DAYS_OVERRIDE={lookback_days_override})")
    print("=" * 140)
    print(
        f"{'Strategy':<40} "
        f"{'Q_CAGR':>10} {'Our_CAGR':>10} {'Diff':>10} "
        f"{'Q_Sharpe':>10} {'Our_Sharpe':>10} {'Diff':>10} "
        f"{'Q_MaxDD':>10} {'Our_MaxDD':>10} {'Diff':>10} "
        f"{'Our_Beta':>8} {'Our_Alpha':>9} {'Our_IR':>7} {'Our_Tryn':>8} {'Our_Win%':>9} {'Our_Trd':>7}"
    )
    print("-" * 140)

    for name in candidates:
        info = qs.get_strategy_info(name) or {}
        start_s = info.get("start_date")
        if start_s:
            start = datetime.fromisoformat(start_s)
        else:
            # If we don't have a configured start_date, try deriving it from holdings time-series.
            holdings = qeng._get_holdings_data()
            api_name = qeng.STRATEGY_NAME_MAP.get(name, name)
            start = None
            if holdings is not None:
                try:
                    dfh = __import__("pandas").DataFrame(holdings)
                    if not dfh.empty and {"Strategy", "Date"}.issubset(set(dfh.columns)):
                        dfh = dfh[dfh["Strategy"] == api_name].copy()
                        dfh["Date"] = __import__("pandas").to_datetime(dfh["Date"], errors="coerce")
                        dfh = dfh.dropna(subset=["Date"])
                        if not dfh.empty:
                            start = dfh["Date"].min().to_pydatetime()
                except Exception:
                    start = None

            if start is None:
                print(f"{name:<40} {'SKIP':>10}")
                results_payload["strategies"][name] = {
                    "status": "SKIP",
                    "reason": "No start_date available (strategy info + holdings derivation failed)",
                }
                _checkpoint_write()
                continue

        res = bt.run_rebalancing_backtest(
            strategy_name=name,
            start_date=start,
            end_date=end,
            lookback_days_override=lookback_days_override,
        )

        if "error" in res:
            print(f"{name:<40} {'ERROR':>10} {res['error']}")
            results_payload["strategies"][name] = {
                "status": "ERROR",
                "start_date": str(start.date()) if start else None,
                "end_date": str(end.date()),
                "error": str(res.get("error")),
            }
            _checkpoint_write()
            continue

        q_cagr = _parse_pct(info.get("cagr"))
        q_sharpe = info.get("sharpe")
        q_dd = _parse_pct(info.get("max_drawdown"))

        our_cagr = res["cagr"] * 100
        our_sharpe = res["sharpe_ratio"]
        our_dd = res["max_drawdown"] * 100
        our_beta = res.get("beta")
        our_alpha = res.get("alpha")
        our_ir = res.get("info_ratio")
        our_treyn = res.get("treynor")
        our_wr = (res.get("win_rate") * 100) if isinstance(res.get("win_rate"), (int, float)) else None
        our_trades = res.get("trades") if isinstance(res.get("trades"), (int, float)) else None

        cagr_diff = (our_cagr - q_cagr) if q_cagr is not None else None
        sharpe_diff = (our_sharpe - q_sharpe) if isinstance(q_sharpe, (int, float)) else None
        dd_diff = (our_dd - q_dd) if q_dd is not None else None

        print(
            f"{name:<40} "
            f"{_fmt_pct(q_cagr):>10} {_fmt_pct(our_cagr):>10} {_fmt_pct(cagr_diff):>10} "
            f"{_fmt_float(q_sharpe if isinstance(q_sharpe, (int, float)) else None):>10} {_fmt_float(our_sharpe):>10} {_fmt_float(sharpe_diff):>10} "
            f"{_fmt_pct(q_dd):>10} {_fmt_pct(our_dd):>10} {_fmt_pct(dd_diff):>10} "
            f"{_fmt_float(our_beta):>8} {_fmt_float(our_alpha):>9} {_fmt_float(our_ir):>7} {_fmt_float(our_treyn):>8} "
            f"{_fmt_float(our_wr):>9} {_fmt_float(our_trades):>7}"
        )

        results_payload["strategies"][name] = {
            "status": "OK",
            "start_date": str(start.date()),
            "end_date": str(end.date()),
            "cagr": our_cagr,
            "sharpe": our_sharpe,
            "max_drawdown": our_dd,
            "beta": our_beta,
            "alpha": our_alpha,
            "info_ratio": our_ir,
            "treynor": our_treyn,
            "win_rate": our_wr,
            "avg_win": (res.get("avg_win") * 100) if isinstance(res.get("avg_win"), (int, float)) else None,
            "avg_loss": (res.get("avg_loss") * 100) if isinstance(res.get("avg_loss"), (int, float)) else None,
            "trades": our_trades,
            "volatility": (res.get("volatility") * 100) if isinstance(res.get("volatility"), (int, float)) else None,
            "std_dev": (res.get("std_dev") * 100) if isinstance(res.get("std_dev"), (int, float)) else None,
            "return_1d": (res.get("return_1d") * 100) if isinstance(res.get("return_1d"), (int, float)) else None,
            "return_30d": (res.get("return_30d") * 100) if isinstance(res.get("return_30d"), (int, float)) else None,
            "return_1y": (res.get("return_1y") * 100) if isinstance(res.get("return_1y"), (int, float)) else None,
        }
        _checkpoint_write()

    print("-" * 140)
    try:
        out_path.write_text(json.dumps(results_payload, indent=2), encoding="utf-8")
        print(f"Wrote {len(results_payload['strategies'])} results to {out_path.as_posix()}")
    except Exception:
        pass


if __name__ == "__main__":
    main()

