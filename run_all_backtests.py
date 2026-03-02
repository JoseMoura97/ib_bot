#!/usr/bin/env python3
"""
Unified Backtest Runner — Single Source of Truth
=================================================
Runs all strategies through one consistent pipeline and produces
a standardized comparison report.

Usage:
    python run_all_backtests.py                     # Run all strategies (cache-only prices)
    python run_all_backtests.py --strategies "Michael Burry,Bill Ackman"
    python run_all_backtests.py --start 2020-01-01 --end 2026-01-30
    python run_all_backtests.py --report-only        # Just show data coverage, no backtests
    python run_all_backtests.py --output results.json # Save results to JSON

Environment:
    QUIVER_API_KEY   — QuiverQuant API key (needed for most strategies)
    PRICE_SOURCE     — auto / yfinance / ib / cache_only (default: cache_only)
    IB_HOST / IB_PORT — Interactive Brokers connection
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# ── Project imports ────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from backtest_engine import BacktestEngine
from metrics_utils import RegressionStats, period_return_from_equity, regression_vs_benchmark, win_loss_stats

# ── Strategy Registry ──────────────────────────────────────────────────────────
# This is THE canonical list.  Every strategy that exists in the system
# is listed here with its data-source type, default date range, and status.

@dataclass
class StrategySpec:
    """Canonical specification for a single strategy."""
    name: str
    data_source: str          # 'quiver_api', 'sec_edgar', 'quiver_premium'
    category: str             # 'core', 'experimental'
    default_start: str        # Earliest reasonable start date
    enabled: bool = True      # Whether to include in default runs
    notes: str = ""


STRATEGY_REGISTRY: List[StrategySpec] = [
    # ── Core (5) ───────────────────────────────────────────────────────────
    StrategySpec("Congress Buys",                  "quiver_api",     "core",         "2020-04-01"),
    StrategySpec("Dan Meuser",                     "quiver_api",     "core",         "2019-08-14"),
    StrategySpec("Sector Weighted DC Insider",     "quiver_api",     "core",         "2020-04-01"),
    StrategySpec("Michael Burry",                  "sec_edgar",      "core",         "2016-02-17"),
    StrategySpec("Lobbying Spending Growth",       "quiver_api",     "core",         "2020-01-01"),

    # ── Experimental: Congressional ────────────────────────────────────────
    StrategySpec("Congress Sells",                             "quiver_api", "experimental", "2020-04-01"),
    StrategySpec("Congress Long-Short",                        "quiver_api", "experimental", "2020-04-01"),
    StrategySpec("U.S. House Long-Short",                      "quiver_api", "experimental", "2020-04-01"),
    StrategySpec("Transportation and Infra. Committee (House)","quiver_api", "experimental", "2020-04-01"),
    StrategySpec("Energy and Commerce Committee (House)",      "quiver_api", "experimental", "2020-04-01"),
    StrategySpec("Homeland Security Committee (Senate)",       "quiver_api", "experimental", "2020-04-01"),
    StrategySpec("Nancy Pelosi",                               "quiver_api", "experimental", "2014-05-16"),
    StrategySpec("Donald Beyer",                               "quiver_api", "experimental", "2016-05-09"),
    StrategySpec("Josh Gottheimer",                            "quiver_api", "experimental", "2019-01-01"),
    StrategySpec("Sheldon Whitehouse",                         "quiver_api", "experimental", "2014-02-28"),

    # ── Experimental: Alternative Data ─────────────────────────────────────
    StrategySpec("Top Lobbying Spenders",      "quiver_api",     "experimental", "2020-01-01"),
    StrategySpec("Top Gov Contract Recipients", "quiver_api",    "experimental", "2020-01-01"),
    StrategySpec("Insider Purchases",           "quiver_api",    "experimental", "2020-01-01"),

    # ── Experimental: Hedge Fund 13F ───────────────────────────────────────
    StrategySpec("Bill Ackman",    "sec_edgar",  "experimental", "2015-02-18"),
    StrategySpec("Howard Marks",   "sec_edgar",  "experimental", "2015-02-17"),

    # ── Premium / Subscription Required ────────────────────────────────────
    StrategySpec("Wall Street Conviction", "quiver_premium", "experimental", "2017-01-01",
                 enabled=False, notes="Requires premium Quiver subscription"),
    StrategySpec("Analyst Buys",           "quiver_api",     "experimental", "2023-02-01",
                 enabled=False, notes="Requires active Quiver subscription"),
]


# ── Extended metrics calculator ────────────────────────────────────────────────

def compute_extended_metrics(
    equity_values: List[float],
    equity_dates: List,
    daily_returns: np.ndarray,
    initial_capital: float,
    start_date: str,
    end_date: str,
    benchmark_ticker: str = "SPY",
    price_source: str = "cache_only",
) -> Dict[str, Any]:
    """
    Compute a comprehensive, standardized metrics dict from raw backtest output.
    This is the ONLY place metrics are calculated — no duplication.
    """
    n = len(daily_returns)
    if n < 2:
        return {"error": "Insufficient data for metrics"}

    # ── Basic returns ──────────────────────────────────────────────────────
    total_return = float(equity_values[-1] / initial_capital - 1.0)
    elapsed_days = max(1, (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days)
    n_years = elapsed_days / 365.25
    cagr = float((equity_values[-1] / initial_capital) ** (1.0 / n_years) - 1.0) if n_years > 0 else 0.0
    volatility = float(np.std(daily_returns) * np.sqrt(252))

    # ── Risk-adjusted returns ──────────────────────────────────────────────
    rf = 0.02
    sharpe = (cagr - rf) / volatility if volatility > 0 else 0.0

    neg_ret = daily_returns[daily_returns < 0]
    downside_std = float(np.std(neg_ret) * np.sqrt(252)) if len(neg_ret) > 0 else 0.0
    sortino = (cagr - rf) / downside_std if downside_std > 0 else 0.0

    # ── Drawdown ───────────────────────────────────────────────────────────
    eq_arr = np.array(equity_values, dtype=float)
    peak = np.maximum.accumulate(eq_arr)
    drawdown = (eq_arr - peak) / peak
    max_drawdown = float(np.min(drawdown))
    calmar = cagr / abs(max_drawdown) if abs(max_drawdown) > 1e-9 else 0.0

    # Max drawdown duration (in trading days)
    in_dd = drawdown < 0
    max_dd_duration = 0
    current_dd_duration = 0
    for v in in_dd:
        if v:
            current_dd_duration += 1
            max_dd_duration = max(max_dd_duration, current_dd_duration)
        else:
            current_dd_duration = 0

    # ── Drawdown recovery time (days from trough to next new high) ────────
    recovery_time = 0
    if len(eq_arr) > 1:
        trough_idx = int(np.argmin(drawdown))
        recovered = False
        for j in range(trough_idx + 1, len(eq_arr)):
            if eq_arr[j] >= peak[trough_idx]:
                recovery_time = j - trough_idx
                recovered = True
                break
        if not recovered:
            recovery_time = len(eq_arr) - trough_idx

    # ── Rolling Sharpe (12-month / 252-day window) ────────────────────────
    rolling_sharpe_latest = None
    if n >= 252:
        window = daily_returns[-252:]
        rs_mean = float(np.mean(window)) * 252
        rs_std = float(np.std(window)) * np.sqrt(252)
        rolling_sharpe_latest = float((rs_mean - rf) / rs_std) if rs_std > 1e-12 else 0.0

    # ── Distribution stats ────────────────────────────────────────────────
    from scipy.stats import skew as _skew, kurtosis as _kurtosis
    skewness = float(_skew(daily_returns)) if n > 2 else 0.0
    excess_kurtosis = float(_kurtosis(daily_returns, fisher=True)) if n > 3 else 0.0

    # ── Win/Loss stats ─────────────────────────────────────────────────────
    win_rate, avg_win, avg_loss = win_loss_stats(daily_returns)
    profit_factor = (avg_win * np.sum(daily_returns > 0)) / (abs(avg_loss) * np.sum(daily_returns < 0)) \
        if avg_loss != 0 and np.sum(daily_returns < 0) > 0 else 0.0

    # ── Equity curve for period returns ────────────────────────────────────
    equity_curve = pd.DataFrame(
        {"portfolio_value": equity_values},
        index=pd.DatetimeIndex(equity_dates, name="date"),
    )
    ret_1d = period_return_from_equity(equity_curve, 1)
    ret_30d = period_return_from_equity(equity_curve, 30)
    ret_90d = period_return_from_equity(equity_curve, 90)
    ret_1y = period_return_from_equity(equity_curve, 365)

    # ── Monthly returns for heatmap ────────────────────────────────────────
    if len(equity_dates) > 1 and len(daily_returns) == len(equity_dates) - 1:
        ret_idx = pd.DatetimeIndex(equity_dates[1:])
    else:
        ret_idx = pd.DatetimeIndex(equity_dates[-len(daily_returns):])
    returns_series = pd.Series(daily_returns, index=ret_idx).sort_index()

    monthly_returns = {}
    try:
        grouped = returns_series.groupby([returns_series.index.year, returns_series.index.month])
        for (year, month), group in grouped:
            monthly_ret = float((1 + group).prod() - 1)
            monthly_returns[f"{year}-{month:02d}"] = round(monthly_ret * 100, 2)
    except Exception:
        pass

    # ── Benchmark comparison ───────────────────────────────────────────────
    beta = alpha = info_ratio = treynor = None
    bench_cagr = bench_total_return = None
    try:
        pricer = BacktestEngine(initial_capital=initial_capital, price_source=price_source)
        bench_data = pricer.fetch_historical_data(
            [benchmark_ticker],
            start_date=start_date,
            end_date=end_date,
        )
        if bench_data and benchmark_ticker in bench_data:
            bclose = pricer._extract_series(bench_data[benchmark_ticker], "Close", benchmark_ticker).sort_index()
            bret = bclose.pct_change().dropna()

            if len(bclose) >= 2:
                bench_total_return = float(bclose.iloc[-1] / bclose.iloc[0] - 1.0)
                b_years = len(bret) / 252.0
                bench_cagr = float((1 + bench_total_return) ** (1 / b_years) - 1.0) if b_years > 0 else 0.0

            stats = regression_vs_benchmark(returns_series, bret, rf_annual=rf)
            beta = stats.beta
            alpha = stats.alpha_annual
            info_ratio = stats.info_ratio
            treynor = stats.treynor
    except Exception:
        pass

    return {
        # ── Identification ─────────────────────────────────────────────────
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": initial_capital,
        "final_value": float(equity_values[-1]),
        "n_days": n,

        # ── Returns ────────────────────────────────────────────────────────
        "total_return": total_return,
        "cagr": cagr,
        "return_1d": ret_1d,
        "return_30d": ret_30d,
        "return_90d": ret_90d,
        "return_1y": ret_1y,

        # ── Risk ───────────────────────────────────────────────────────────
        "volatility": volatility,
        "max_drawdown": max_drawdown,
        "max_drawdown_duration_days": max_dd_duration,
        "drawdown_recovery_days": recovery_time,
        "rolling_sharpe_12m": rolling_sharpe_latest,
        "skewness": skewness,
        "excess_kurtosis": excess_kurtosis,

        # ── Risk-adjusted ──────────────────────────────────────────────────
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,

        # ── Win/Loss ───────────────────────────────────────────────────────
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,

        # ── Benchmark ──────────────────────────────────────────────────────
        "benchmark": benchmark_ticker,
        "benchmark_total_return": bench_total_return,
        "benchmark_cagr": bench_cagr,
        "alpha": alpha,
        "beta": beta,
        "info_ratio": info_ratio,
        "treynor": treynor,

        # ── Detailed data ──────────────────────────────────────────────────
        "monthly_returns": monthly_returns,
    }


# ── Unified Runner ─────────────────────────────────────────────────────────────

@dataclass
class BacktestResult:
    strategy: str
    category: str
    data_source: str
    status: str               # 'success', 'error', 'skipped'
    metrics: Dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    elapsed_seconds: float = 0.0


def _load_plot_data_cache() -> Dict[str, Dict]:
    """Load cached equity curves from plot_data.json as fallback."""
    cache_path = ROOT_DIR / ".cache" / "plot_data.json"
    if not cache_path.exists():
        return {}
    try:
        with open(cache_path, "r") as f:
            data = json.load(f)
        return data.get("strategies", {})
    except Exception:
        return {}


def _metrics_from_plot_data(cached: Dict, strategy_name: str, price_source: str) -> Dict[str, Any]:
    """
    Reconstruct full metrics from a cached plot_data equity curve.
    This allows us to produce consistent stats even when the API is down.
    """
    dates_raw = cached.get("dates", [])
    values_raw = cached.get("values", [])
    if not dates_raw or not values_raw or len(dates_raw) != len(values_raw):
        return {"error": "Invalid cached data"}

    # Convert to proper types
    dates = [pd.Timestamp(d) for d in dates_raw]
    values = [float(v) for v in values_raw]
    initial_capital = values[0]

    # Compute daily returns from the equity curve
    eq = np.array(values, dtype=float)
    daily_returns = np.diff(eq) / eq[:-1]
    daily_returns = np.nan_to_num(daily_returns, nan=0.0, posinf=0.0, neginf=0.0)

    return compute_extended_metrics(
        equity_values=values,
        equity_dates=dates,
        daily_returns=daily_returns,
        initial_capital=initial_capital,
        start_date=str(dates[0].date()),
        end_date=str(dates[-1].date()),
        price_source=price_source,
    )


def run_single_strategy(
    spec: StrategySpec,
    start_date: str,
    end_date: str,
    price_source: str,
    quiver_api_key: Optional[str],
    use_cache_fallback: bool = True,
) -> BacktestResult:
    """Run a single strategy backtest, with graceful fallback."""

    t0 = time.time()

    # ── Skip disabled strategies ───────────────────────────────────────────
    if not spec.enabled:
        return BacktestResult(
            strategy=spec.name,
            category=spec.category,
            data_source=spec.data_source,
            status="skipped",
            error_message=spec.notes or "Disabled",
            elapsed_seconds=time.time() - t0,
        )

    # ── Check prerequisites ────────────────────────────────────────────────
    if spec.data_source == "quiver_api" and not quiver_api_key:
        # Try cache fallback
        if use_cache_fallback:
            return _try_cache_fallback(spec, price_source, t0)
        return BacktestResult(
            strategy=spec.name,
            category=spec.category,
            data_source=spec.data_source,
            status="error",
            error_message="QUIVER_API_KEY not set",
            elapsed_seconds=time.time() - t0,
        )

    # ── Attempt live backtest via RebalancingBacktestEngine ─────────────────
    try:
        from rebalancing_backtest_engine import RebalancingBacktestEngine

        effective_start = max(spec.default_start, start_date) if start_date else spec.default_start

        bt = RebalancingBacktestEngine(
            quiver_api_key=quiver_api_key or "",
            initial_capital=100000.0,
            transaction_cost_bps=0.0,
            price_source=price_source,
        )

        result = bt.run_rebalancing_backtest(
            strategy_name=spec.name,
            start_date=effective_start,
            end_date=end_date,
        )

        if "error" in result:
            # Live backtest failed — try cache fallback
            if use_cache_fallback:
                cached_result = _try_cache_fallback(spec, price_source, t0)
                if cached_result.status == "success":
                    cached_result.error_message = f"Live failed ({result['error']}), used cached data"
                    return cached_result
            return BacktestResult(
                strategy=spec.name,
                category=spec.category,
                data_source=spec.data_source,
                status="error",
                error_message=result["error"],
                elapsed_seconds=time.time() - t0,
            )

        # ── Extract raw data and compute standardized metrics ──────────────
        equity_curve = result.get("equity_curve")
        returns_series = result.get("returns_series")

        if equity_curve is not None and not equity_curve.empty:
            eq_values = equity_curve["portfolio_value"].tolist()
            eq_dates = equity_curve.index.tolist()
            daily_rets = returns_series.values if returns_series is not None else np.diff(np.array(eq_values)) / np.array(eq_values[:-1])
        else:
            return BacktestResult(
                strategy=spec.name,
                category=spec.category,
                data_source=spec.data_source,
                status="error",
                error_message="No equity curve in result",
                elapsed_seconds=time.time() - t0,
            )

        metrics = compute_extended_metrics(
            equity_values=eq_values,
            equity_dates=eq_dates,
            daily_returns=np.asarray(daily_rets, dtype=float),
            initial_capital=100000.0,
            start_date=result.get("start_date", effective_start),
            end_date=result.get("end_date", end_date),
            price_source=price_source,
        )

        # Carry forward engine-computed fields not in our metrics
        for key in ["trades", "rebalance_events"]:
            if key in result:
                metrics[key] = result[key]

        return BacktestResult(
            strategy=spec.name,
            category=spec.category,
            data_source=spec.data_source,
            status="success",
            metrics=metrics,
            elapsed_seconds=time.time() - t0,
        )

    except Exception as e:
        # Live backtest crashed — try cache fallback
        if use_cache_fallback:
            cached_result = _try_cache_fallback(spec, price_source, t0)
            if cached_result.status == "success":
                cached_result.error_message = f"Live crashed ({type(e).__name__}: {e}), used cached data"
                return cached_result
        return BacktestResult(
            strategy=spec.name,
            category=spec.category,
            data_source=spec.data_source,
            status="error",
            error_message=f"{type(e).__name__}: {e}",
            elapsed_seconds=time.time() - t0,
        )


def _try_cache_fallback(spec: StrategySpec, price_source: str, t0: float) -> BacktestResult:
    """Attempt to produce results from cached plot_data.json."""
    plot_cache = _load_plot_data_cache()
    if spec.name in plot_cache:
        metrics = _metrics_from_plot_data(plot_cache[spec.name], spec.name, price_source)
        if "error" not in metrics:
            metrics["_data_source"] = "cached_plot_data"
            return BacktestResult(
                strategy=spec.name,
                category=spec.category,
                data_source=spec.data_source,
                status="success",
                metrics=metrics,
                error_message="Using cached equity curve (API unavailable)",
                elapsed_seconds=time.time() - t0,
            )
    return BacktestResult(
        strategy=spec.name,
        category=spec.category,
        data_source=spec.data_source,
        status="error",
        error_message="No cached data available and live backtest failed",
        elapsed_seconds=time.time() - t0,
    )


# ── Data Coverage Report ──────────────────────────────────────────────────────

def generate_coverage_report() -> str:
    """Generate a data coverage report showing what's available for each strategy."""
    lines = []
    lines.append("=" * 110)
    lines.append("DATA COVERAGE REPORT")
    lines.append("=" * 110)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Price cache stats
    ib_dir = ROOT_DIR / ".cache" / "ib_prices"
    yf_dir = ROOT_DIR / ".cache" / "yf_prices"
    ib_count = len(list(ib_dir.glob("*.pkl"))) if ib_dir.exists() else 0
    yf_count = len(list(yf_dir.glob("*.pkl"))) if yf_dir.exists() else 0
    lines.append(f"Price Cache: {ib_count} IB tickers, {yf_count} YF tickers")
    lines.append("")

    # Plot data cache
    plot_cache = _load_plot_data_cache()
    lines.append(f"Cached Equity Curves (plot_data.json): {len(plot_cache)} strategies")
    lines.append("")

    # SEC EDGAR cache
    sec_dir = ROOT_DIR / ".cache" / "sec_edgar"
    sec_filings = list(sec_dir.glob("filings_*.json")) if sec_dir.exists() else []
    sec_holdings = list(sec_dir.glob("holdings_*.pkl")) if sec_dir.exists() else []
    lines.append(f"SEC EDGAR Cache: {len(sec_filings)} filing lists, {len(sec_holdings)} holdings snapshots")
    lines.append("")

    # QuiverQuant API status
    api_key = os.getenv("QUIVER_API_KEY", "")
    lines.append(f"QuiverQuant API Key: {'SET' if api_key else 'NOT SET'}")
    lines.append("")

    # Latest backtest results (if available)
    latest_results: Dict[str, Dict] = {}
    latest_path = ROOT_DIR / ".cache" / "all_results_combined.json"
    # Also check all_fresh_results.json (newer)
    for candidate in ["all_fresh_results.json", "all_results_combined.json"]:
        p = ROOT_DIR / ".cache" / candidate
        if p.exists():
            try:
                with open(p) as f:
                    lr = json.load(f)
                for r in lr.get("results", []):
                    if r.get("status") == "success" and r.get("metrics"):
                        latest_results[r["strategy"]] = r["metrics"]
            except Exception:
                pass
            break

    # Per-strategy coverage
    lines.append("-" * 140)
    lines.append(f"{'Strategy':<45} {'Source':<14} {'Cat':<6} {'Cached':<7} {'Date Range':<25} {'Pts':>5} {'Status'}")
    lines.append("-" * 140)

    for spec in STRATEGY_REGISTRY:
        has_cache = spec.name in plot_cache
        cached_str = "YES" if has_cache else "NO"

        # Date range and points from cached data
        date_range = ""
        pts = ""
        if has_cache:
            cd = plot_cache[spec.name]
            dates = cd.get("dates", [])
            if dates:
                date_range = f"{dates[0]} to {dates[-1]}"
                pts = str(len(dates))

        if not spec.enabled:
            status = f"DISABLED ({spec.notes})"
        elif spec.data_source == "sec_edgar":
            status = "READY (SEC EDGAR)"
        elif spec.data_source == "quiver_api" and api_key:
            status = "READY (Quiver API)"
        elif spec.data_source == "quiver_api" and not api_key:
            status = "CACHED ONLY" if has_cache else "BLOCKED (no API key)"
        elif spec.data_source == "quiver_premium":
            status = "BLOCKED (premium required)"
        else:
            status = "UNKNOWN"

        lines.append(f"{spec.name:<45} {spec.data_source:<14} {spec.category:<6} {cached_str:<7} {date_range:<25} {pts:>5} {status}")

    lines.append("-" * 140)

    # Data quality warnings
    lines.append("")
    lines.append("DATA QUALITY FLAGS:")
    quality_flags = []
    for spec in STRATEGY_REGISTRY:
        if spec.name in plot_cache:
            cd = plot_cache[spec.name]
            values = cd.get("values", [])
            if values and len(values) > 1:
                eq = [float(v) for v in values]
                # Check for suspicious single-period jumps (>200%)
                for i in range(1, len(eq)):
                    if eq[i-1] > 0:
                        ret = eq[i] / eq[i-1] - 1
                        if abs(ret) > 2.0:
                            quality_flags.append(f"  WARNING: {spec.name} - {ret*100:.0f}% single-period jump at index {i} (likely data error)")
                            break
                # Check for suspiciously high total return
                total_ret = eq[-1] / eq[0] - 1 if eq[0] > 0 else 0
                if total_ret > 50:  # >5000% total return
                    quality_flags.append(f"  WARNING: {spec.name} - {total_ret*100:.0f}% total return (likely data error)")
        # Check latest backtest results for anomalies
        if spec.name in latest_results:
            m = latest_results[spec.name]
            cagr = m.get("cagr", 0)
            if cagr > 1.0:
                quality_flags.append(f"  WARNING: {spec.name} - CAGR {cagr*100:.1f}% is suspiciously high")

    if quality_flags:
        for f in quality_flags:
            lines.append(f)
    else:
        lines.append("  No quality flags detected.")

    # Summary counts
    lines.append("")
    total = len(STRATEGY_REGISTRY)
    enabled = sum(1 for s in STRATEGY_REGISTRY if s.enabled)
    sec_edgar = sum(1 for s in STRATEGY_REGISTRY if s.data_source == "sec_edgar" and s.enabled)
    quiver_ready = sum(1 for s in STRATEGY_REGISTRY if s.data_source == "quiver_api" and s.enabled and api_key)
    cached_available = sum(1 for s in STRATEGY_REGISTRY if s.name in plot_cache and s.enabled)

    lines.append(f"Total: {total} strategies ({enabled} enabled)")
    lines.append(f"  SEC EDGAR (always available):  {sec_edgar}")
    lines.append(f"  Quiver API (if key set):       {quiver_ready}")
    lines.append(f"  Cached equity curves:          {cached_available}")
    lines.append("")
    lines.append("=" * 140)

    return "\n".join(lines)


# ── Results Formatting ─────────────────────────────────────────────────────────

def format_results_table(results: List[BacktestResult]) -> str:
    """Format results into a readable comparison table."""
    lines = []
    lines.append("")
    lines.append("=" * 160)
    lines.append("BACKTEST RESULTS — ALL STRATEGIES")
    lines.append("=" * 160)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Successful results
    success = [r for r in results if r.status == "success"]
    errors = [r for r in results if r.status == "error"]
    skipped = [r for r in results if r.status == "skipped"]

    if success:
        lines.append(f"{'Strategy':<45} {'CAGR':>8} {'Sharpe':>8} {'Sortino':>8} {'MaxDD':>8} {'DDDur':>6} {'WinR%':>7} {'Alpha':>8} {'Beta':>6} {'Calmar':>8} {'Source':<12}")
        lines.append("-" * 160)

        # Sort by CAGR descending
        success.sort(key=lambda r: r.metrics.get("cagr", 0), reverse=True)

        for r in success:
            m = r.metrics
            cagr = f"{m.get('cagr', 0) * 100:.1f}%" if m.get('cagr') is not None else "N/A"
            sharpe = f"{m.get('sharpe_ratio', 0):.3f}" if m.get('sharpe_ratio') is not None else "N/A"
            sortino = f"{m.get('sortino_ratio', 0):.3f}" if m.get('sortino_ratio') is not None else "N/A"
            max_dd = f"{m.get('max_drawdown', 0) * 100:.1f}%" if m.get('max_drawdown') is not None else "N/A"
            dd_dur = f"{m.get('max_drawdown_duration_days', 0)}" if m.get('max_drawdown_duration_days') is not None else "N/A"
            win_r = f"{m.get('win_rate', 0) * 100:.1f}%" if m.get('win_rate') is not None else "N/A"
            alpha_v = m.get('alpha')
            alpha_s = f"{alpha_v * 100:.1f}%" if alpha_v is not None else "N/A"
            beta_v = m.get('beta')
            beta_s = f"{beta_v:.2f}" if beta_v is not None else "N/A"
            calmar = f"{m.get('calmar_ratio', 0):.3f}" if m.get('calmar_ratio') is not None else "N/A"
            source = m.get("_data_source", "live")[:12]
            note = f" *{r.error_message}" if r.error_message else ""

            lines.append(f"{r.strategy:<45} {cagr:>8} {sharpe:>8} {sortino:>8} {max_dd:>8} {dd_dur:>6} {win_r:>7} {alpha_s:>8} {beta_s:>6} {calmar:>8} {source:<12}{note}")

        lines.append("-" * 160)
        lines.append("")

    if errors:
        lines.append("FAILED STRATEGIES:")
        for r in errors:
            lines.append(f"  {r.strategy:<45} — {r.error_message}")
        lines.append("")

    if skipped:
        lines.append("SKIPPED STRATEGIES:")
        for r in skipped:
            lines.append(f"  {r.strategy:<45} — {r.error_message}")
        lines.append("")

    # Summary
    lines.append(f"Summary: {len(success)} succeeded, {len(errors)} failed, {len(skipped)} skipped")
    total_time = sum(r.elapsed_seconds for r in results)
    lines.append(f"Total time: {total_time:.1f}s")
    lines.append("=" * 160)

    return "\n".join(lines)


def save_results_json(results: List[BacktestResult], output_path: str):
    """Save results to a JSON file for programmatic consumption."""
    output = {
        "generated_at": datetime.now().isoformat(),
        "results": [],
    }
    for r in results:
        entry = {
            "strategy": r.strategy,
            "category": r.category,
            "data_source": r.data_source,
            "status": r.status,
            "error_message": r.error_message,
            "elapsed_seconds": r.elapsed_seconds,
        }
        if r.metrics:
            # Remove non-serializable items
            clean_metrics = {}
            for k, v in r.metrics.items():
                if isinstance(v, (int, float, str, bool, type(None), list, dict)):
                    clean_metrics[k] = v
            entry["metrics"] = clean_metrics
        output["results"].append(entry)

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to: {output_path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Unified Backtest Runner — Single Source of Truth",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--strategies", type=str, default=None,
                        help="Comma-separated list of strategy names to run (default: all enabled)")
    parser.add_argument("--start", type=str, default=None,
                        help="Start date (YYYY-MM-DD). Default: strategy-specific")
    parser.add_argument("--end", type=str, default=None,
                        help="End date (YYYY-MM-DD). Default: 2026-01-30")
    parser.add_argument("--price-source", type=str, default=None,
                        help="Price source: cache_only, yfinance, ib, auto (default: cache_only)")
    parser.add_argument("--output", type=str, default=None,
                        help="Save results to JSON file")
    parser.add_argument("--report-only", action="store_true",
                        help="Only show data coverage report, don't run backtests")
    parser.add_argument("--category", type=str, default=None,
                        help="Filter by category: core, experimental")
    parser.add_argument("--include-disabled", action="store_true",
                        help="Include disabled strategies")
    parser.add_argument("--no-cache-fallback", action="store_true",
                        help="Don't use cached plot_data as fallback")
    parser.add_argument("--sec-edgar-only", action="store_true",
                        help="Only run SEC EDGAR strategies (no API key needed)")

    args = parser.parse_args()

    # ── Always show coverage report ────────────────────────────────────────
    print(generate_coverage_report())

    if args.report_only:
        return

    # ── Configure ──────────────────────────────────────────────────────────
    end_date = args.end or "2026-01-30"
    start_date = args.start  # None means use strategy-specific defaults
    price_source = args.price_source or os.getenv("PRICE_SOURCE", "cache_only")
    quiver_api_key = os.getenv("QUIVER_API_KEY", "")

    # ── Select strategies ──────────────────────────────────────────────────
    specs = list(STRATEGY_REGISTRY)

    if args.strategies:
        names = [n.strip() for n in args.strategies.split(",")]
        specs = [s for s in specs if s.name in names]
        if not specs:
            print(f"\nERROR: No matching strategies found for: {args.strategies}")
            print(f"Available: {', '.join(s.name for s in STRATEGY_REGISTRY)}")
            return

    if args.category:
        specs = [s for s in specs if s.category == args.category]

    if args.sec_edgar_only:
        specs = [s for s in specs if s.data_source == "sec_edgar"]

    if not args.include_disabled:
        specs = [s for s in specs if s.enabled]

    print(f"\nRunning {len(specs)} strategies...")
    print(f"Price source: {price_source}")
    print(f"End date: {end_date}")
    if quiver_api_key:
        print("QuiverQuant API: ACTIVE")
    else:
        print("QuiverQuant API: DOWN (using cache fallback where available)")
    print("")

    # ── Run backtests ──────────────────────────────────────────────────────
    results: List[BacktestResult] = []
    for i, spec in enumerate(specs):
        effective_start = start_date or spec.default_start
        print(f"[{i+1}/{len(specs)}] {spec.name} ({spec.data_source})...", end=" ", flush=True)

        result = run_single_strategy(
            spec=spec,
            start_date=effective_start,
            end_date=end_date,
            price_source=price_source,
            quiver_api_key=quiver_api_key,
            use_cache_fallback=not args.no_cache_fallback,
        )
        results.append(result)

        if result.status == "success":
            cagr = result.metrics.get("cagr", 0)
            print(f"OK (CAGR: {cagr*100:.1f}%, {result.elapsed_seconds:.1f}s)")
        elif result.status == "skipped":
            print(f"SKIPPED ({result.error_message})")
        else:
            print(f"FAILED ({result.error_message[:80]})")

    # ── Output ─────────────────────────────────────────────────────────────
    print(format_results_table(results))

    if args.output:
        save_results_json(results, args.output)

    # ── Save latest results to cache for UI consumption ────────────────────
    results_cache_path = ROOT_DIR / ".cache" / "latest_backtest_results.json"
    save_results_json(results, str(results_cache_path))


if __name__ == "__main__":
    main()
