"""
Targeted extra model tests for Burry to see what best matches Quiver metrics.

This complements `fit_quiver_13f_models.py` with a few hypotheses:
- Calls-only (ignore puts) might match Quiver if they don't model bearish option bets.
- Puts-only (ignore calls) is the opposite sanity check.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _pct_to_float(x: Any) -> float:
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s.endswith("%"):
        s = s[:-1].strip()
    return float(s)


def _clear_sec_cache() -> None:
    d = ROOT / ".cache" / "sec_edgar"
    if not d.exists():
        return
    for fp in d.glob("holdings_*.pkl"):
        try:
            fp.unlink()
        except Exception:
            pass


def _run(
    *,
    options_mode: str,
    put_delta: Optional[float],
    call_delta: Optional[float],
    use_filed_dates: bool,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    os.environ["SEC_13F_OPTIONS_MODE"] = options_mode
    if put_delta is None:
        os.environ.pop("SEC_13F_PUT_DELTA", None)
    else:
        os.environ["SEC_13F_PUT_DELTA"] = str(put_delta)
    if call_delta is None:
        os.environ.pop("SEC_13F_CALL_DELTA", None)
    else:
        os.environ["SEC_13F_CALL_DELTA"] = str(call_delta)

    if use_filed_dates:
        os.environ["USE_13F_FILED_DATES"] = "1"
    else:
        os.environ.pop("USE_13F_FILED_DATES", None)

    _clear_sec_cache()

    from rebalancing_backtest_engine import RebalancingBacktestEngine

    eng = RebalancingBacktestEngine(quiver_api_key=os.getenv("QUIVER_API_KEY", ""), initial_capital=100000)
    return eng.run_rebalancing_backtest(strategy_name="Michael Burry", start_date=start_date, end_date=end_date)


def main() -> None:
    quiver = json.loads((ROOT / ".cache" / "quiver_strategies_site.json").read_text(encoding="utf-8"))
    qb = quiver["strategies"]["Michael Burry"]
    q_cagr = _pct_to_float(qb["cagr"])
    q_dd = _pct_to_float(qb["max_drawdown"])
    q_sh = float(qb.get("sharpe") or 0.0)
    start = qb["start_date"]
    end = date.today().strftime("%Y-%m-%d")

    print(f"Quiver target: CAGR={q_cagr:.2f}%  MaxDD={q_dd:.2f}%  Sharpe={q_sh:.3f}")
    print(f"Window: {start} -> {end}")
    print("")

    tests: Tuple[Tuple[str, Optional[float], Optional[float]], ...] = (
        ("filter", None, None),
        ("as_exposure", None, None),
        # Calls-only / puts-only via delta_adjusted with one side set to 0
        ("delta_adjusted", 0.00, 1.00),  # ignore puts, full calls
        ("delta_adjusted", 0.00, 0.70),
        ("delta_adjusted", 0.00, 0.50),
        ("delta_adjusted", 0.00, 0.30),
        ("delta_adjusted", 1.00, 0.00),  # full puts, ignore calls
        ("delta_adjusted", 0.70, 0.00),
        ("delta_adjusted", 0.50, 0.00),
    )

    for use_filed in [False, True]:
        tag = "filed_dates" if use_filed else "fixed_dates"
        print(f"== {tag} ==")
        for mode, put_d, call_d in tests:
            t0 = time.time()
            res = _run(
                options_mode=mode,
                put_delta=put_d,
                call_delta=call_d,
                use_filed_dates=use_filed,
                start_date=start,
                end_date=end,
            )
            dt = time.time() - t0
            if "error" in res:
                print(f"- {mode:13s} put={put_d} call={call_d} -> ERROR {res.get('error')} ({dt:.1f}s)")
                continue
            our_cagr = float(res.get("cagr", 0.0)) * 100.0
            our_dd = float(res.get("max_drawdown", 0.0)) * 100.0
            our_sh = float(res.get("sharpe_ratio", 0.0))
            print(
                f"- {mode:13s} put={put_d} call={call_d} -> "
                f"CAGR={our_cagr:6.2f}% MaxDD={our_dd:7.2f}% Sharpe={our_sh:5.3f} ({dt:.1f}s)"
            )
        print("")


if __name__ == "__main__":
    main()

