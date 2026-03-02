from __future__ import annotations

import logging
from typing import Dict

import numpy as np
import pandas as pd
from scipy.optimize import minimize

logger = logging.getLogger(__name__)


def records_to_series(records: list[dict]) -> pd.Series:
    if not records:
        return pd.Series(dtype="float64")
    idx = pd.to_datetime([r["date"] for r in records], errors="coerce")
    vals = [r["value"] for r in records]
    s = pd.Series(vals, index=idx).dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.astype("float64")


def nav_blend_equity_curves(
    curves: Dict[str, pd.Series],
    weights: Dict[str, float],
) -> pd.Series:
    """
    Blend strategy equity curves by portfolio weights (NAV blend).
    - Aligns by date index (inner join).
    - Returns weighted sum of values.
    """
    if not curves:
        return pd.Series(dtype="float64")

    cols = {}
    for name, s in curves.items():
        if s is None or s.empty:
            continue
        cols[name] = s
    if not cols:
        return pd.Series(dtype="float64")

    df = pd.DataFrame(cols).dropna(how="any")
    if df.empty:
        return pd.Series(dtype="float64")

    w_sum = sum(float(weights.get(k, 0.0)) for k in df.columns)
    if w_sum == 0:
        w = {k: 1.0 / len(df.columns) for k in df.columns}
    else:
        w = {k: float(weights.get(k, 0.0)) / w_sum for k in df.columns}

    blended = sum(df[k] * w[k] for k in df.columns)
    blended.name = "portfolio_value"
    return blended


# ---------------------------------------------------------------------------
# Returns matrix from equity curves
# ---------------------------------------------------------------------------

def _build_returns_matrix(curves: Dict[str, pd.Series]) -> pd.DataFrame:
    """Align curves and compute daily returns. Drops any all-NaN rows."""
    df = pd.DataFrame(curves).dropna(how="any")
    if df.empty:
        return pd.DataFrame()
    return df.pct_change().dropna()


def _portfolio_stats(
    weights: np.ndarray, mean_returns: np.ndarray, cov_matrix: np.ndarray
) -> dict:
    """Annualized return, volatility, Sharpe for a weight vector."""
    port_return = float(np.dot(weights, mean_returns) * 252)
    port_vol = float(np.sqrt(np.dot(weights, np.dot(cov_matrix * 252, weights))))
    sharpe = port_return / port_vol if port_vol > 1e-12 else 0.0
    return {"annual_return": port_return, "annual_vol": port_vol, "sharpe": sharpe}


def _diversification_ratio(weights: np.ndarray, cov_matrix: np.ndarray) -> float:
    """Ratio of weighted-average vol to portfolio vol. Higher = more diversified."""
    vols = np.sqrt(np.diag(cov_matrix))
    weighted_avg_vol = np.dot(weights, vols)
    port_vol = np.sqrt(weights @ cov_matrix @ weights)
    if port_vol < 1e-12:
        return 1.0
    return float(weighted_avg_vol / port_vol)


def _max_pairwise_correlation(weights: np.ndarray, cov_matrix: np.ndarray, threshold: float = 0.0) -> float:
    """Max pairwise correlation among positions with weight > threshold."""
    n = len(weights)
    vols = np.sqrt(np.diag(cov_matrix))
    max_corr = 0.0
    for i in range(n):
        if weights[i] <= threshold:
            continue
        for j in range(i + 1, n):
            if weights[j] <= threshold:
                continue
            if vols[i] > 1e-12 and vols[j] > 1e-12:
                corr = cov_matrix[i, j] / (vols[i] * vols[j])
                max_corr = max(max_corr, abs(corr))
    return max_corr


# ---------------------------------------------------------------------------
# Optimization methods
# ---------------------------------------------------------------------------


def optimize_equal_weight(
    curves: Dict[str, pd.Series],
    *,
    max_weight: float = 0.30,
    min_weight: float = 0.02,
    min_diversification: float = 1.0,
    max_correlation: float = 0.95,
) -> dict:
    """Equal-weight across all strategies."""
    names = sorted(curves.keys())
    n = len(names)
    if n == 0:
        return {"error": "No curves provided"}
    w = 1.0 / n
    weights = {name: round(w, 6) for name in names}
    returns_df = _build_returns_matrix(curves)
    stats = {}
    if not returns_df.empty:
        mean_r = returns_df.mean().values
        cov = returns_df.cov().values
        w_arr = np.array([weights[n] for n in returns_df.columns])
        stats = _portfolio_stats(w_arr, mean_r, cov)
        cov_ann = returns_df.cov().values * 252
        stats["diversification_ratio"] = _diversification_ratio(w_arr, cov_ann)
        stats["max_pairwise_correlation"] = _max_pairwise_correlation(w_arr, cov_ann)
    return {"method": "equal_weight", "weights": weights, "stats": stats}


def optimize_inverse_volatility(
    curves: Dict[str, pd.Series],
    *,
    max_weight: float = 0.30,
    min_weight: float = 0.02,
    min_diversification: float = 1.0,
    max_correlation: float = 0.95,
) -> dict:
    """Weight inversely proportional to annualized volatility."""
    returns_df = _build_returns_matrix(curves)
    if returns_df.empty or returns_df.shape[1] == 0:
        return {"error": "Insufficient data for inverse-volatility optimization"}

    names = list(returns_df.columns)
    vols = returns_df.std() * np.sqrt(252)
    if (vols < 1e-12).any():
        return {"error": "One or more strategies have near-zero volatility"}

    inv_vol = 1.0 / vols
    raw = inv_vol / inv_vol.sum()
    raw = np.clip(raw.values, min_weight, max_weight)
    raw = raw / raw.sum()

    weights = {name: round(float(raw[i]), 6) for i, name in enumerate(names)}
    mean_r = returns_df.mean().values
    cov = returns_df.cov().values
    stats = _portfolio_stats(raw, mean_r, cov)
    if not returns_df.empty:
        cov_ann = returns_df.cov().values * 252
        stats["diversification_ratio"] = _diversification_ratio(raw, cov_ann)
        stats["max_pairwise_correlation"] = _max_pairwise_correlation(raw, cov_ann)
    return {"method": "inverse_volatility", "weights": weights, "stats": stats}


def optimize_risk_parity(
    curves: Dict[str, pd.Series],
    *,
    max_weight: float = 0.30,
    min_weight: float = 0.02,
    min_diversification: float = 1.0,
    max_correlation: float = 0.95,
) -> dict:
    """
    Risk-parity: equalize risk contribution per strategy.
    Uses iterative optimization to minimize the sum of squared differences
    between each asset's risk contribution and the target (1/n).
    """
    returns_df = _build_returns_matrix(curves)
    if returns_df.empty or returns_df.shape[1] == 0:
        return {"error": "Insufficient data for risk-parity optimization"}

    names = list(returns_df.columns)
    n = len(names)
    cov = returns_df.cov().values * 252
    mean_r = returns_df.mean().values

    target_risk = 1.0 / n

    def risk_contribution(w: np.ndarray) -> np.ndarray:
        port_vol = np.sqrt(w @ cov @ w)
        if port_vol < 1e-12:
            return np.zeros(n)
        marginal = cov @ w
        rc = w * marginal / port_vol
        return rc

    def objective(w: np.ndarray) -> float:
        rc = risk_contribution(w)
        total_rc = rc.sum()
        if total_rc < 1e-12:
            return 1e6
        rc_pct = rc / total_rc
        return float(np.sum((rc_pct - target_risk) ** 2))

    x0 = np.ones(n) / n
    bounds = [(min_weight, max_weight)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    result = minimize(
        objective, x0, method="SLSQP", bounds=bounds, constraints=constraints,
        options={"maxiter": 500, "ftol": 1e-12},
    )

    raw = result.x
    raw = np.clip(raw, min_weight, max_weight)
    raw = raw / raw.sum()

    weights = {name: round(float(raw[i]), 6) for i, name in enumerate(names)}
    stats = _portfolio_stats(raw, mean_r, cov / 252)
    if not returns_df.empty:
        cov_ann = returns_df.cov().values * 252
        stats["diversification_ratio"] = _diversification_ratio(raw, cov_ann)
        stats["max_pairwise_correlation"] = _max_pairwise_correlation(raw, cov_ann)
    return {"method": "risk_parity", "weights": weights, "stats": stats}


def optimize_max_sharpe(
    curves: Dict[str, pd.Series],
    *,
    max_weight: float = 0.30,
    min_weight: float = 0.02,
    risk_free_rate: float = 0.04,
    min_diversification: float = 1.0,
    max_correlation: float = 0.95,
) -> dict:
    """
    Mean-variance optimization: maximize Sharpe ratio.
    Uses scipy.optimize with bounded weights.
    """
    returns_df = _build_returns_matrix(curves)
    if returns_df.empty or returns_df.shape[1] == 0:
        return {"error": "Insufficient data for max-Sharpe optimization"}

    names = list(returns_df.columns)
    n = len(names)
    mean_r = returns_df.mean().values * 252
    cov = returns_df.cov().values * 252
    rf = risk_free_rate

    def neg_sharpe(w: np.ndarray) -> float:
        port_ret = np.dot(w, mean_r)
        port_vol = np.sqrt(w @ cov @ w)
        if port_vol < 1e-12:
            return 1e6
        return -float((port_ret - rf) / port_vol)

    x0 = np.ones(n) / n
    bounds = [(min_weight, max_weight)] * n
    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]

    result = minimize(
        neg_sharpe, x0, method="SLSQP", bounds=bounds, constraints=constraints,
        options={"maxiter": 500, "ftol": 1e-12},
    )

    raw = result.x
    raw = np.clip(raw, min_weight, max_weight)
    raw = raw / raw.sum()

    weights = {name: round(float(raw[i]), 6) for i, name in enumerate(names)}
    stats = _portfolio_stats(raw, returns_df.mean().values, returns_df.cov().values)
    if not returns_df.empty:
        cov_ann = returns_df.cov().values * 252
        stats["diversification_ratio"] = _diversification_ratio(raw, cov_ann)
        stats["max_pairwise_correlation"] = _max_pairwise_correlation(raw, cov_ann)
    return {"method": "max_sharpe", "weights": weights, "stats": stats}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

OPTIMIZATION_METHODS = {
    "equal_weight": optimize_equal_weight,
    "inverse_volatility": optimize_inverse_volatility,
    "risk_parity": optimize_risk_parity,
    "max_sharpe": optimize_max_sharpe,
}


def optimize_portfolio(
    curves: Dict[str, pd.Series],
    method: str = "equal_weight",
    *,
    max_weight: float = 0.30,
    min_weight: float = 0.02,
    min_diversification: float = 1.0,
    max_correlation: float = 0.95,
    risk_free_rate: float = 0.04,
) -> dict:
    """Run a single optimization method."""
    fn = OPTIMIZATION_METHODS.get(method)
    if fn is None:
        return {"error": f"Unknown method '{method}'. Available: {list(OPTIMIZATION_METHODS.keys())}"}
    kwargs: dict = {"max_weight": max_weight, "min_weight": min_weight, "min_diversification": min_diversification, "max_correlation": max_correlation}
    if method == "max_sharpe":
        kwargs["risk_free_rate"] = risk_free_rate
    return fn(curves, **kwargs)


def compare_all_methods(
    curves: Dict[str, pd.Series],
    *,
    max_weight: float = 0.30,
    min_weight: float = 0.02,
    min_diversification: float = 1.0,
    max_correlation: float = 0.95,
    risk_free_rate: float = 0.04,
) -> list[dict]:
    """Run all 4 optimization methods and return results side-by-side."""
    results = []
    for method_name in OPTIMIZATION_METHODS:
        r = optimize_portfolio(
            curves, method_name,
            max_weight=max_weight, min_weight=min_weight,
            min_diversification=min_diversification, max_correlation=max_correlation,
            risk_free_rate=risk_free_rate,
        )
        results.append(r)
    return results
