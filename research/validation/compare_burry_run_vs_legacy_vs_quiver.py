"""
Run a fresh Burry backtest and compare vs legacy plot_data + Quiver published metrics.

- "Run": uses current code + env vars in THIS process.
- "Legacy": reads `.cache/backups/plot_data_23strategies_FINAL.json`
            (the pre-fix backtest snapshot from earlier work).
- "Quiver": reads `.cache/quiver_strategies_site.json` (scraped strategy table).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class Metrics:
    cagr_pct: Optional[float]
    sharpe: Optional[float]
    max_dd_pct: Optional[float]
    start_date: Optional[str]
    points: Optional[int]


def _pct_to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if not s:
        return None
    if s.endswith("%"):
        s = s[:-1].strip()
    try:
        return float(s)
    except Exception:
        return None


def _fmt_pct(x: Optional[float]) -> str:
    return "N/A" if x is None else f"{x:.2f}%"


def _fmt_num(x: Optional[float]) -> str:
    return "N/A" if x is None else f"{x:.3f}"


def _load_quiver_burry() -> Metrics:
    p = ROOT / ".cache" / "quiver_strategies_site.json"
    q = json.loads(p.read_text(encoding="utf-8"))
    b = (q.get("strategies") or {}).get("Michael Burry") or {}
    return Metrics(
        cagr_pct=_pct_to_float(b.get("cagr")),
        sharpe=(float(b["sharpe"]) if "sharpe" in b and b["sharpe"] is not None else None),
        max_dd_pct=_pct_to_float(b.get("max_drawdown")),
        start_date=b.get("start_date"),
        points=None,
    )


def _load_legacy_burry() -> Metrics:
    p = ROOT / ".cache" / "backups" / "plot_data_23strategies_FINAL.json"
    legacy = json.loads(p.read_text(encoding="utf-8"))
    b = (legacy.get("strategies") or {}).get("Michael Burry") or {}
    # Legacy files in this repo store % already (not decimals). Keep as-is.
    return Metrics(
        cagr_pct=_pct_to_float(b.get("cagr")),
        sharpe=_pct_to_float(b.get("sharpe")),
        max_dd_pct=_pct_to_float(b.get("max_drawdown")),
        start_date=(b.get("start_date") or (b.get("dates") or [None])[0]),
        points=len(b.get("values") or []) if isinstance(b.get("values"), list) else None,
    )


def _run_burry(start_date: str) -> Metrics:
    from rebalancing_backtest_engine import RebalancingBacktestEngine

    end_date = date.today().strftime("%Y-%m-%d")
    eng = RebalancingBacktestEngine(quiver_api_key=os.getenv("QUIVER_API_KEY", ""), initial_capital=100000)
    res: Dict[str, Any] = eng.run_rebalancing_backtest("Michael Burry", start_date=start_date, end_date=end_date)
    if "error" in res:
        raise RuntimeError(str(res.get("error")))

    equity = res.get("equity_curve")
    points = None
    if isinstance(equity, (pd.DataFrame, pd.Series)):
        points = int(len(equity))
    elif isinstance(res.get("equity"), (list, tuple)):
        points = int(len(res.get("equity")))

    return Metrics(
        cagr_pct=float(res.get("cagr", 0.0)) * 100.0,
        sharpe=float(res.get("sharpe_ratio", 0.0)),
        max_dd_pct=float(res.get("max_drawdown", 0.0)) * 100.0,
        start_date=start_date,
        points=points,
    )


def main() -> None:
    quiver = _load_quiver_burry()
    legacy = _load_legacy_burry()

    start = quiver.start_date or "2016-02-17"
    run = _run_burry(start)

    cfg = {
        "SEC_13F_OPTIONS_MODE": os.getenv("SEC_13F_OPTIONS_MODE", ""),
        "SEC_13F_PUT_DELTA": os.getenv("SEC_13F_PUT_DELTA", ""),
        "SEC_13F_CALL_DELTA": os.getenv("SEC_13F_CALL_DELTA", ""),
        "USE_13F_FILED_DATES": os.getenv("USE_13F_FILED_DATES", ""),
        "SEC_13F_REBALANCE_OFFSET_DAYS": os.getenv("SEC_13F_REBALANCE_OFFSET_DAYS", ""),
        "SEC_13F_TOP_N": os.getenv("SEC_13F_TOP_N", ""),
    }

    print("Burry comparison (same Quiver start-date)")
    print(f"Run config env: {cfg}")
    print("")

    rows = [
        ("Run (current code)", run),
        ("Legacy backup", legacy),
        ("Quiver published", quiver),
    ]

    print(f"{'Source':<18} {'CAGR':>10} {'Sharpe':>10} {'MaxDD':>10} {'Start':>12} {'Points':>8}")
    print("-" * 74)
    for name, m in rows:
        print(
            f"{name:<18} "
            f"{_fmt_pct(m.cagr_pct):>10} "
            f"{_fmt_num(m.sharpe):>10} "
            f"{_fmt_pct(m.max_dd_pct):>10} "
            f"{(m.start_date or 'N/A'):>12} "
            f"{(str(m.points) if m.points is not None else 'N/A'):>8}"
        )


if __name__ == "__main__":
    main()

