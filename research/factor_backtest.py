"""
Standalone factor investing backtest engine.

Runs a monthly-rebalance long-only portfolio:
  - Universe: all cached tickers with sufficient history
  - Monthly rebalance on ~15th of each month
  - Top N by factor score, equal weight
  - 10 bps one-way transaction cost
  - SPY benchmark

Usage:
    from factor_backtest import FactorBacktest
    fb = FactorBacktest()
    result = fb.run(
        factor="momentum",
        start="2023-05-18",
        end="2026-05-18",
        n=20,
        cost_bps=10,
    )
"""
from __future__ import annotations

import math
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, "/app")

from research.factor_engine import FactorEngine, _load_ticker

INITIAL_CAPITAL = 100_000.0
SPY_TICKER = "SPY"


def _rebalance_dates(start: datetime, end: datetime) -> List[datetime]:
    """Monthly rebalance dates on 15th (or next business day)."""
    dates = []
    current = pd.Timestamp(start).replace(day=1)
    end_ts  = pd.Timestamp(end)
    while current <= end_ts:
        # Target: 15th of each month
        target = current.replace(day=15)
        if target >= pd.Timestamp(start) and target <= end_ts:
            # Round to nearest business day
            bd = target
            while bd.weekday() >= 5:
                bd += pd.Timedelta(days=1)
            dates.append(bd.to_pydatetime())
        current = (current + pd.DateOffset(months=1)).replace(day=1)
    return dates


def _compute_metrics(
    equity: pd.Series,
    benchmark: pd.Series,
) -> dict:
    """Compute CAGR, Sharpe, MaxDD, Alpha, Beta vs benchmark."""
    if len(equity) < 10:
        return {"error": "insufficient data"}

    equity = equity.sort_index().dropna()
    if len(equity) < 10:
        return {"error": "insufficient data after dropna"}
    benchmark = benchmark.reindex(equity.index, method="ffill").ffill().bfill()
    # Drop any remaining NaN rows from both sides
    valid_mask = benchmark.notna()
    benchmark = benchmark[valid_mask]
    equity = equity.reindex(benchmark.index).dropna()
    if len(equity) < 10:
        return {"error": "insufficient aligned data"}

    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0:
        return {"error": "zero duration"}

    total_ret = equity.iloc[-1] / equity.iloc[0] - 1
    cagr = (1 + total_ret) ** (1 / years) - 1

    daily_rets = equity.pct_change().dropna()
    sharpe = (daily_rets.mean() / daily_rets.std() * math.sqrt(252)
              if daily_rets.std() > 0 else 0.0)

    # Sortino
    neg = daily_rets[daily_rets < 0]
    sortino = (daily_rets.mean() / neg.std() * math.sqrt(252)
               if len(neg) > 0 and neg.std() > 0 else 0.0)

    # Max drawdown
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max
    max_dd = float(dd.min())

    # Alpha / Beta
    bench_rets = benchmark.pct_change().dropna()
    common = daily_rets.index.intersection(bench_rets.index)
    if len(common) > 30:
        p = daily_rets.reindex(common).values
        b = bench_rets.reindex(common).values
        cov_mat = np.cov(p, b)
        beta = cov_mat[0, 1] / cov_mat[1, 1] if cov_mat[1, 1] > 0 else 1.0
        alpha_ann = (np.mean(p) - beta * np.mean(b)) * 252
    else:
        beta, alpha_ann = 1.0, 0.0

    # Volatility
    vol = float(daily_rets.std() * math.sqrt(252))

    return {
        "cagr": round(cagr, 4),
        "total_return": round(total_ret, 4),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "max_drawdown": round(max_dd, 4),
        "alpha": round(alpha_ann, 4),
        "beta": round(beta, 3),
        "volatility": round(vol, 4),
        "years": round(years, 2),
        "n_rebalances": None,  # filled by caller
    }


class FactorBacktest:
    """Run a factor-based monthly-rebalance backtest."""

    def __init__(
        self,
        price_cache_dir: str = "/app/.cache/yf_prices",
        fund_cache_path: str = "/app/.cache/factor_fundamentals.pkl",
        min_universe_history_days: int = 300,
        min_avg_volume: float = 200_000,
    ):
        self.engine = FactorEngine(
            cache_dir=price_cache_dir,
            fund_cache_path=fund_cache_path,
        )
        self.min_history = min_universe_history_days
        self.min_volume = min_avg_volume
        self._spy: Optional[pd.Series] = None

    def _get_spy(self) -> pd.Series:
        if self._spy is None:
            self._spy = _load_ticker(SPY_TICKER)
        return self._spy

    def _get_factor_scores(
        self,
        factor: str,
        tickers: List[str],
        date: datetime,
        extra: dict,
    ) -> pd.Series:
        """Dispatch to the right scoring method."""
        e = self.engine
        f = factor.lower().replace("-", "_").replace(" ", "_")

        if f == "momentum":
            return e.score_momentum(tickers, date)
        elif f in ("low_vol", "low_volatility", "lowvol"):
            return e.score_low_vol(tickers, date)
        elif f == "value":
            return e.score_value(tickers, date)
        elif f == "quality":
            return e.score_quality(tickers, date)
        elif f in ("investment", "cma"):
            return e.score_investment(tickers, date)
        elif f in ("size", "smb"):
            return e.score_size(tickers, date)
        elif f in ("momentum_lowvol", "mom_lowvol", "mom_low_vol"):
            return e.score_multi_factor([
                e.score_momentum(tickers, date),
                e.score_low_vol(tickers, date),
            ])
        elif f in ("quality_value", "value_quality"):
            return e.score_multi_factor([
                e.score_quality(tickers, date),
                e.score_value(tickers, date),
            ])
        elif f in ("small_cap_value", "scv", "smb_value"):
            return e.score_multi_factor([
                e.score_size(tickers, date),
                e.score_value(tickers, date),
            ])
        elif f in ("small_cap_quality", "scq"):
            return e.score_multi_factor([
                e.score_size(tickers, date),
                e.score_quality(tickers, date),
            ])
        elif f in ("large_cap_value", "lcv"):
            # Value restricted to market cap > $2B (mid/large cap only)
            return e.score_value(tickers, date, min_market_cap=2e9)
        elif f in ("large_cap_quality_value", "lcqv"):
            return e.score_multi_factor([
                e.score_quality(tickers, date),
                e.score_value(tickers, date, min_market_cap=2e9),
            ])
        elif f in ("multi", "multi_factor", "all"):
            parts = [
                e.score_momentum(tickers, date),
                e.score_low_vol(tickers, date),
            ]
            for fn in [e.score_value, e.score_quality,
                       e.score_investment, e.score_size]:
                try:
                    s = fn(tickers, date)
                    if len(s) > 5:
                        parts.append(s)
                except Exception:
                    pass
            return e.score_multi_factor(parts)
        else:
            raise ValueError(f"Unknown factor: {factor}")

    def run(
        self,
        factor: str,
        start: str | datetime,
        end:   str | datetime,
        n: int = 20,
        cost_bps: float = 10.0,
        verbose: bool = False,
    ) -> dict:
        """
        Run the backtest. Returns result dict with equity curve + metrics.
        """
        start_dt = pd.Timestamp(start).to_pydatetime()
        end_dt   = pd.Timestamp(end).to_pydatetime()

        spy = self._get_spy()
        if spy is None:
            return {"error": "SPY price data not found"}

        spy = spy[
            (spy.index >= pd.Timestamp(start_dt)) &
            (spy.index <= pd.Timestamp(end_dt))
        ]

        # Preload universe from first rebalance date
        if verbose:
            print(f"  Building universe…", end="", flush=True)
        universe = self.engine.get_universe(
            start_dt, min_history_days=self.min_history
        )
        if verbose:
            print(f" {len(universe)} tickers")

        # Rebalance schedule
        rb_dates = _rebalance_dates(start_dt, end_dt)
        if not rb_dates:
            return {"error": "no rebalance dates in range"}

        # Preload all prices once
        if verbose:
            print(f"  Preloading {len(universe)} price series…", end="", flush=True)
        self.engine.load_prices(universe)
        if verbose:
            print(" done")

        # ── simulation ───────────────────────────────────────────────────
        capital      = INITIAL_CAPITAL
        holdings: Dict[str, float] = {}  # ticker → shares
        cash         = capital
        portfolio_values: Dict[pd.Timestamp, float] = {}
        n_rebalances = 0

        # Get all trading dates from SPY
        all_dates = spy.index[spy.index >= pd.Timestamp(start_dt)]

        prev_rb_idx = 0
        rb_ts = [pd.Timestamp(d) for d in rb_dates]

        for date in all_dates:
            # Mark-to-market current holdings (use last valid non-NaN price)
            port_val = cash
            for ticker, shares in holdings.items():
                s = self.engine._price_cache.get(ticker)
                if s is not None:
                    px = s[s.index <= date].dropna()
                    if len(px) > 0:
                        port_val += shares * px.iloc[-1]
            portfolio_values[date] = port_val

            # Check if today is a rebalance date
            if rb_ts and date >= rb_ts[0]:
                rb_ts.pop(0)
                n_rebalances += 1

                # Score and select
                try:
                    scores = self._get_factor_scores(factor, universe, date, {})
                except Exception as ex:
                    if verbose:
                        print(f"  score error on {date.date()}: {ex}")
                    continue

                if len(scores) < n:
                    if verbose:
                        print(f"  {date.date()}: only {len(scores)} scoreable, need {n}")
                    continue

                new_weights = FactorEngine.select_top_n(scores, n)

                # Compute new target values
                new_values = {t: w * port_val for t, w in new_weights.items()}

                # Transaction costs on turnover
                old_values: Dict[str, float] = {}
                for ticker, shares in holdings.items():
                    s = self.engine._price_cache.get(ticker)
                    if s is not None:
                        px = s[s.index <= date].dropna()
                        if len(px) > 0:
                            old_values[ticker] = shares * px.iloc[-1]

                all_tickers = set(old_values) | set(new_values)
                total_trade_value = 0.0
                for t in all_tickers:
                    old_v = old_values.get(t, 0.0)
                    new_v = new_values.get(t, 0.0)
                    total_trade_value += abs(new_v - old_v)

                cost = total_trade_value * (cost_bps / 10_000)
                port_val -= cost
                cash = port_val  # will be re-allocated

                # Buy new portfolio
                holdings = {}
                cash = 0.0
                for ticker, target_val in new_values.items():
                    adjusted = target_val * (1 - cost / port_val if port_val > 0 else 1)
                    s = self.engine._price_cache.get(ticker)
                    if s is not None:
                        px = s[s.index <= date].dropna()
                        if len(px) > 0 and px.iloc[-1] > 0:
                            holdings[ticker] = adjusted / px.iloc[-1]

                if verbose and n_rebalances <= 3:
                    top5 = list(new_weights.keys())[:5]
                    print(f"  {date.date()} rebalance #{n_rebalances}: top5={top5}, NAV={port_val:,.0f}")

        if not portfolio_values:
            return {"error": "no portfolio values computed"}

        equity = pd.Series(portfolio_values).sort_index()
        equity.name = "portfolio_value"

        # Align SPY to equity dates
        spy_aligned = spy.reindex(equity.index, method="ffill")
        spy_clean = spy_aligned.dropna()
        spy_first = spy_clean.iloc[0] if len(spy_clean) > 0 else 1.0
        spy_norm = spy_aligned.ffill().bfill() / spy_first * INITIAL_CAPITAL

        metrics = _compute_metrics(equity, spy_norm)
        metrics["n_rebalances"] = n_rebalances
        metrics["factor"] = factor
        metrics["n_holdings"] = n
        metrics["cost_bps"] = cost_bps
        metrics["start"] = str(start_dt.date())
        metrics["end"] = str(end_dt.date())
        metrics["trades"] = n_rebalances * n  # approximate

        # Attach equity curve and SPY curve
        metrics["equity_curve"] = equity
        metrics["spy_curve"] = spy_norm

        return metrics
