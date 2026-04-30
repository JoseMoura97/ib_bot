"""
Compare Burry metrics across multiple 13F rebalance offsets.

This tests the hypothesis that a different rebalance offset (days after quarter-end)
brings our backtest closer to Quiver's published metrics.

Defaults:
- SEC_13F_OPTIONS_MODE=filter (stock-only) unless already set
- OFFSETS env var can override, e.g. OFFSETS="0,15,30,45,60"
- Or use OFFSET_START/OFFSET_END/OFFSET_STEP (inclusive range),
  e.g. OFFSET_START=0 OFFSET_END=90 OFFSET_STEP=5
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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


def _load_quiver() -> Dict[str, Any]:
    p = ROOT / ".cache" / "quiver_strategies_site.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _load_legacy() -> Dict[str, Any]:
    p = ROOT / ".cache" / "backups" / "plot_data_23strategies_FINAL.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _run_burry(start_date: str, end_date: str) -> Dict[str, Any]:
    from rebalancing_backtest_engine import RebalancingBacktestEngine

    eng = RebalancingBacktestEngine(quiver_api_key=os.getenv("QUIVER_API_KEY", ""), initial_capital=100000)
    return eng.run_rebalancing_backtest("Michael Burry", start_date=start_date, end_date=end_date)


def _offsets() -> List[int]:
    # Explicit list wins.
    raw = os.getenv("OFFSETS", "").strip()
    if raw:
        out: List[int] = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                out.append(int(part))
            except Exception:
                pass
        if out:
            return out
    # Range form.
    s = os.getenv("OFFSET_START", "").strip()
    e = os.getenv("OFFSET_END", "").strip()
    st = os.getenv("OFFSET_STEP", "").strip()
    if s and e and st:
        try:
            start = int(s)
            end = int(e)
            step = int(st)
            if step == 0:
                raise ValueError("OFFSET_STEP cannot be 0")
            if start <= end and step > 0:
                return list(range(start, end + 1, step))
            if start >= end and step < 0:
                return list(range(start, end - 1, step))
        except Exception:
            pass

    return [0, 15, 30, 45, 60]


def _score_to_quiver(
    *,
    cagr: float,
    max_dd: float,
    sharpe: float,
    q_cagr: Optional[float],
    q_dd: Optional[float],
    q_sharpe: Optional[float],
) -> float:
    """
    Lower is better. Weighted to emphasize CAGR first, then drawdown, then Sharpe.
    """
    # If any Quiver target is missing, just ignore that component.
    score = 0.0
    if q_cagr is not None:
        score += abs(cagr - q_cagr) * 1.0
    if q_dd is not None:
        score += abs(max_dd - q_dd) * 0.35
    if q_sharpe is not None:
        score += abs(sharpe - float(q_sharpe)) * 5.0
    return score


def main() -> None:
    os.environ.setdefault("SEC_13F_OPTIONS_MODE", "filter")

    q = _load_quiver()
    qb = (q.get("strategies") or {}).get("Michael Burry") or {}
    start = str(qb.get("start_date") or "2016-02-17")
    end = date.today().strftime("%Y-%m-%d")

    q_cagr = _pct_to_float(qb.get("cagr"))
    q_dd = _pct_to_float(qb.get("max_drawdown"))
    q_sh = qb.get("sharpe")
    q_sh_f = float(q_sh) if q_sh is not None else None

    legacy = _load_legacy()
    lb = (legacy.get("strategies") or {}).get("Michael Burry") or {}
    legacy_row = {
        "cagr": _pct_to_float(lb.get("cagr")),
        "sharpe": _pct_to_float(lb.get("sharpe")),
        "max_dd": _pct_to_float(lb.get("max_drawdown")),
        "start": str(lb.get("start_date") or (lb.get("dates") or [None])[0]),
        "points": len(lb.get("values") or []) if isinstance(lb.get("values"), list) else None,
    }

    print("Burry offset sweep (same Quiver start-date)")
    print(f"Fixed settings: SEC_13F_OPTIONS_MODE={os.getenv('SEC_13F_OPTIONS_MODE')}")
    print(f"Window: {start} -> {end}")
    print(f"Quiver: CAGR={q_cagr}% MaxDD={q_dd}% Sharpe={q_sh}")
    print("")

    results: List[Dict[str, Any]] = []

    for off in _offsets():
        os.environ["SEC_13F_REBALANCE_OFFSET_DAYS"] = str(off)
        res = _run_burry(start, end)
        if "error" in res:
            results.append(
                {"offset": off, "error": str(res.get("error")), "cagr": None, "sharpe": None, "max_dd": None, "points": None, "score": float("inf")}
            )
            continue
        cagr = float(res.get("cagr", 0.0)) * 100.0
        sharpe = float(res.get("sharpe_ratio", 0.0))
        max_dd = float(res.get("max_drawdown", 0.0)) * 100.0
        eq = res.get("equity_curve")
        pts = None
        if isinstance(eq, (pd.DataFrame, pd.Series)):
            pts = int(len(eq))
        score = _score_to_quiver(cagr=cagr, max_dd=max_dd, sharpe=sharpe, q_cagr=q_cagr, q_dd=q_dd, q_sharpe=q_sh_f)
        results.append({"offset": off, "cagr": cagr, "sharpe": sharpe, "max_dd": max_dd, "points": pts, "score": score})

    # Print ranked results (best first)
    ranked = sorted(results, key=lambda r: float(r.get("score", float("inf"))))
    top_n = int(os.getenv("TOP_N", "10") or 10)

    print(f"Top {top_n} offsets by closest-to-Quiver score (lower is better):")
    print(f"{'Rank':>4} {'Offset':>6} {'Score':>10} {'CAGR':>10} {'Sharpe':>10} {'MaxDD':>10}")
    print("-" * 66)
    for i, r in enumerate(ranked[:top_n], start=1):
        if r.get("cagr") is None:
            print(f"{i:>4} {r['offset']:>6} {str(r.get('score')):>10} {'ERR':>10} {'ERR':>10} {'ERR':>10}")
        else:
            print(
                f"{i:>4} {r['offset']:>6} {float(r['score']):>10.3f} "
                f"{float(r['cagr']):>9.2f}% {float(r['sharpe']):>10.3f} {float(r['max_dd']):>9.2f}%"
            )

    print("")
    print("Full sweep (unsorted):")
    print(f"{'Offset':>6} {'Score':>10} {'CAGR':>10} {'Sharpe':>10} {'MaxDD':>10} {'Points':>8}")
    print("-" * 74)
    for r in results:
        if r.get("cagr") is None:
            print(f"{r['offset']:>6} {str(r.get('score')):>10} {'ERR':>10} {'ERR':>10} {'ERR':>10} {'-':>8}")
        else:
            print(
                f"{r['offset']:>6} {float(r['score']):>10.3f} {float(r['cagr']):>9.2f}% "
                f"{float(r['sharpe']):>10.3f} {float(r['max_dd']):>9.2f}% {str(r.get('points') or 'N/A'):>8}"
            )

    print("")
    print("Legacy backup (for reference):")
    print(
        f"  CAGR={legacy_row['cagr']}% Sharpe={legacy_row['sharpe']} "
        f"MaxDD={legacy_row['max_dd']}% Start={legacy_row['start']} Points={legacy_row['points']}"
    )


if __name__ == "__main__":
    main()

