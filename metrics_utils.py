from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RegressionStats:
    beta: Optional[float]
    alpha_annual: Optional[float]
    info_ratio: Optional[float]
    treynor: Optional[float]


def win_loss_stats(daily_returns: np.ndarray) -> Tuple[float, float, float]:
    """Return (win_rate, avg_win, avg_loss) from a 1D array of daily returns."""
    if daily_returns is None:
        return 0.0, 0.0, 0.0
    r = np.asarray(daily_returns, dtype=float)
    if r.size == 0:
        return 0.0, 0.0, 0.0
    wins = r[r > 0]
    losses = r[r < 0]
    win_rate = float(wins.size / r.size)
    avg_win = float(np.mean(wins)) if wins.size else 0.0
    avg_loss = float(np.mean(losses)) if losses.size else 0.0
    return win_rate, avg_win, avg_loss


def period_return_from_equity(equity_curve: pd.DataFrame, days_back: int) -> Optional[float]:
    """
    Compute a calendar-lookback return from an equity curve DataFrame with 'portfolio_value'.

    - days_back=1 uses the last two trading days.
    - days_back>1 uses last value <= (last_date - days_back).
    """
    if equity_curve is None or equity_curve.empty or "portfolio_value" not in equity_curve.columns:
        return None
    ec = equity_curve.sort_index()
    if len(ec) < 2:
        return None
    if days_back <= 1:
        v1 = float(ec["portfolio_value"].iloc[-1])
        v0 = float(ec["portfolio_value"].iloc[-2])
        return (v1 / v0) - 1.0 if v0 != 0 else None

    last_dt = ec.index.max()
    target = pd.Timestamp(last_dt) - pd.Timedelta(days=int(days_back))
    hist = ec.loc[:target]
    if hist.empty:
        return None
    v1 = float(ec["portfolio_value"].iloc[-1])
    v0 = float(hist["portfolio_value"].iloc[-1])
    return (v1 / v0) - 1.0 if v0 != 0 else None


def regression_vs_benchmark(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    rf_annual: float = 0.02,
) -> RegressionStats:
    """
    Compute beta/alpha/info_ratio/treynor vs a benchmark.

    - Inputs are daily return series. They will be aligned by date (inner join).
    - Alpha is annualized from daily intercept of excess returns.
    - Info ratio is annualized mean(active)/std(active).
    - Treynor uses annualized excess return divided by beta.
    """
    if portfolio_returns is None or benchmark_returns is None:
        return RegressionStats(None, None, None, None)

    df = (
        portfolio_returns.dropna().to_frame("port")
        .join(benchmark_returns.dropna().to_frame("bench"), how="inner")
        .dropna()
    )
    if len(df) < 30:
        return RegressionStats(None, None, None, None)

    rf_daily = float(rf_annual) / 252.0
    port_ex = df["port"] - rf_daily
    bench_ex = df["bench"] - rf_daily

    # Use consistent (population) covariance/variance so beta is stable.
    bx = bench_ex.to_numpy(dtype=float)
    px = port_ex.to_numpy(dtype=float)
    bx_mean = float(np.mean(bx))
    px_mean = float(np.mean(px))
    cov_pb = float(np.mean((px - px_mean) * (bx - bx_mean)))
    var_b = float(np.mean((bx - bx_mean) ** 2))
    if var_b <= 0:
        return RegressionStats(None, None, None, None)

    beta = float(cov_pb / var_b)
    alpha_daily = float(np.mean(port_ex) - beta * np.mean(bench_ex))
    alpha_annual = float(alpha_daily * 252.0)

    active = df["port"] - df["bench"]
    active_std = float(np.std(active))
    info_ratio = float((np.mean(active) / active_std) * np.sqrt(252.0)) if active_std > 0 else None

    treynor = None
    if abs(beta) > 1e-12:
        treynor = float((np.mean(port_ex) * 252.0) / beta)

    return RegressionStats(beta=beta, alpha_annual=alpha_annual, info_ratio=info_ratio, treynor=treynor)

