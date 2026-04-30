"""
Fit 13F option-handling models to Quiver's published strategy metrics.

Goal:
- User only has basic Quiver API tier; we use the locally-cached scrape:
  `.cache/quiver_strategies_site.json`
- Run our backtest under multiple option models and rebalance schedules
  and pick the closest match to Quiver's metrics for the SAME timeframe.

This is intentionally a standalone analysis script (no library deps beyond project deps).
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[2]  # repo root
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class QuiverTarget:
    start_date: str
    cagr_pct: float
    max_dd_pct: float
    sharpe: Optional[float]


def _pct_to_float(x: Any) -> float:
    """Parse '28.82%' -> 28.82, or numeric -> float."""
    if x is None:
        return float("nan")
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s.endswith("%"):
        s = s[:-1].strip()
    return float(s)


def _load_quiver_targets() -> Dict[str, QuiverTarget]:
    p = ROOT / ".cache" / "quiver_strategies_site.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    strategies = data.get("strategies", {})

    out: Dict[str, QuiverTarget] = {}
    for name in ["Michael Burry", "Bill Ackman", "Howard Marks"]:
        s = strategies.get(name, {})
        if not s:
            continue
        out[name] = QuiverTarget(
            start_date=str(s.get("start_date")),
            cagr_pct=_pct_to_float(s.get("cagr")),
            max_dd_pct=_pct_to_float(s.get("max_drawdown")),
            sharpe=(float(s["sharpe"]) if "sharpe" in s and s["sharpe"] is not None else None),
        )
    return out


def _clear_sec_cache() -> None:
    cache_dir = ROOT / ".cache" / "sec_edgar"
    if not cache_dir.exists():
        return
    for fp in cache_dir.glob("holdings_*.pkl"):
        try:
            fp.unlink()
        except Exception:
            pass


def _set_env(
    *,
    options_mode: str,
    put_delta: Optional[float],
    call_delta: Optional[float],
    use_filed_dates: bool,
) -> None:
    os.environ["SEC_13F_OPTIONS_MODE"] = options_mode
    if put_delta is not None:
        os.environ["SEC_13F_PUT_DELTA"] = str(put_delta)
    else:
        os.environ.pop("SEC_13F_PUT_DELTA", None)
    if call_delta is not None:
        os.environ["SEC_13F_CALL_DELTA"] = str(call_delta)
    else:
        os.environ.pop("SEC_13F_CALL_DELTA", None)

    if use_filed_dates:
        os.environ["USE_13F_FILED_DATES"] = "1"
    else:
        os.environ.pop("USE_13F_FILED_DATES", None)


def _run_backtest(
    *,
    strategy_name: str,
    start_date: str,
    end_date: str,
    options_mode: str,
    put_delta: Optional[float],
    call_delta: Optional[float],
    use_filed_dates: bool,
) -> Dict[str, Any]:
    # Configure environment for this run.
    _set_env(
        options_mode=options_mode,
        put_delta=put_delta,
        call_delta=call_delta,
        use_filed_dates=use_filed_dates,
    )
    _clear_sec_cache()

    from rebalancing_backtest_engine import RebalancingBacktestEngine

    api_key = os.getenv("QUIVER_API_KEY", "")
    eng = RebalancingBacktestEngine(quiver_api_key=api_key, initial_capital=100000)
    return eng.run_rebalancing_backtest(
        strategy_name=strategy_name,
        start_date=start_date,
        end_date=end_date,
    )


def _score_fit(result: Dict[str, Any], target: QuiverTarget) -> float:
    """
    Lower is better.

    We prioritize CAGR first, then Max DD, then Sharpe.
    """
    if "error" in result:
        return 1e9

    our_cagr = float(result.get("cagr", 0.0)) * 100.0
    our_max_dd = float(result.get("max_drawdown", 0.0)) * 100.0
    our_sharpe = float(result.get("sharpe_ratio", 0.0))

    cagr_err = abs(our_cagr - target.cagr_pct)
    dd_err = abs(our_max_dd - target.max_dd_pct)
    if target.sharpe is None:
        sharpe_err = 0.0
    else:
        sharpe_err = abs(our_sharpe - float(target.sharpe))

    # Sharpe is ~0-2 range; scale it so it matters but doesn't dominate.
    return (cagr_err * 1.0) + (dd_err * 0.35) + (sharpe_err * 5.0)


def _configs() -> Iterable[Tuple[str, Optional[float], Optional[float]]]:
    # (mode, put_delta, call_delta)
    yield ("filter", None, None)
    yield ("as_exposure", None, None)  # sign the option premium (PUT short, CALL long)

    # Delta-adjusted premium exposure (try a range).
    for d in [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00]:
        yield ("delta_adjusted", d, d)

    # Slightly asymmetric deltas (puts often have higher absolute delta than calls in hedges).
    for put_d, call_d in [(0.50, 0.35), (0.60, 0.40), (0.70, 0.45), (0.80, 0.50)]:
        yield ("delta_adjusted", put_d, call_d)


def main() -> None:
    targets = _load_quiver_targets()
    if "Michael Burry" not in targets:
        raise SystemExit("Missing Quiver target metrics for Michael Burry in cache.")

    end_date = date.today().strftime("%Y-%m-%d")

    burry_target = targets["Michael Burry"]
    start_date = burry_target.start_date

    print("=" * 80)
    print("Fitting models to Quiver 'Michael Burry' metrics")
    print("=" * 80)
    print(f"Backtest window: {start_date} -> {end_date}")
    print(f"Quiver target: CAGR={burry_target.cagr_pct:.2f}%, MaxDD={burry_target.max_dd_pct:.2f}%, Sharpe={burry_target.sharpe}")
    print("")

    best = None  # (score, config, use_filed_dates, result)
    rows: List[Tuple[float, str, str, str, float, float, float]] = []

    for use_filed_dates in [False, True]:
        for mode, put_d, call_d in _configs():
            t0 = time.time()
            res = _run_backtest(
                strategy_name="Michael Burry",
                start_date=start_date,
                end_date=end_date,
                options_mode=mode,
                put_delta=put_d,
                call_delta=call_d,
                use_filed_dates=use_filed_dates,
            )
            elapsed = time.time() - t0

            score = _score_fit(res, burry_target)
            if "error" in res:
                rows.append((score, mode, str(put_d), str(call_d), float("nan"), float("nan"), float("nan")))
            else:
                our_cagr = float(res.get("cagr", 0.0)) * 100.0
                our_dd = float(res.get("max_drawdown", 0.0)) * 100.0
                our_sh = float(res.get("sharpe_ratio", 0.0))
                rows.append((score, mode, str(put_d), str(call_d), our_cagr, our_dd, our_sh))

            tag = "filed_dates" if use_filed_dates else "fixed_dates"
            print(f"- {tag:10s} | {mode:13s} put={put_d} call={call_d} | score={score:7.3f} | {elapsed:5.1f}s")

            if best is None or score < best[0]:
                best = (score, (mode, put_d, call_d), use_filed_dates, res)

    assert best is not None
    best_score, (best_mode, best_put, best_call), best_filed, best_res = best

    print("")
    print("=" * 80)
    print("BEST FIT (Burry)")
    print("=" * 80)
    tag = "filed_dates" if best_filed else "fixed_dates"
    if "error" in best_res:
        print(f"{tag} | {best_mode} put={best_put} call={best_call} -> ERROR: {best_res.get('error')}")
        raise SystemExit(1)

    best_cagr = float(best_res.get("cagr", 0.0)) * 100.0
    best_dd = float(best_res.get("max_drawdown", 0.0)) * 100.0
    best_sh = float(best_res.get("sharpe_ratio", 0.0))
    print(f"{tag} | {best_mode} put={best_put} call={best_call}")
    print(f"Our:    CAGR={best_cagr:.2f}%  MaxDD={best_dd:.2f}%  Sharpe={best_sh:.3f}")
    print(f"Quiver: CAGR={burry_target.cagr_pct:.2f}%  MaxDD={burry_target.max_dd_pct:.2f}%  Sharpe={burry_target.sharpe}")
    print(f"Score:  {best_score:.3f}")

    # Validate on other 13F strategies (sanity check; options typically minimal).
    print("")
    print("=" * 80)
    print("SANITY CHECK (same model on other 13F strategies)")
    print("=" * 80)

    for name in ["Bill Ackman", "Howard Marks"]:
        if name not in targets:
            continue
        tgt = targets[name]
        res = _run_backtest(
            strategy_name=name,
            start_date=tgt.start_date,
            end_date=end_date,
            options_mode=best_mode,
            put_delta=best_put,
            call_delta=best_call,
            use_filed_dates=best_filed,
        )
        if "error" in res:
            print(f"- {name}: ERROR {res.get('error')}")
            continue
        our_cagr = float(res.get("cagr", 0.0)) * 100.0
        our_dd = float(res.get("max_drawdown", 0.0)) * 100.0
        our_sh = float(res.get("sharpe_ratio", 0.0))
        print(
            f"- {name}: Our CAGR={our_cagr:.2f}% vs Quiver {tgt.cagr_pct:.2f}% | "
            f"Our MaxDD={our_dd:.2f}% vs Quiver {tgt.max_dd_pct:.2f}% | "
            f"Our Sharpe={our_sh:.3f} vs Quiver {tgt.sharpe}"
        )


if __name__ == "__main__":
    main()

