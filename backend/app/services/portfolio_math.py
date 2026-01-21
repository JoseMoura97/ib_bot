from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

import pandas as pd


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
        # default equal weights across available strategies
        w = {k: 1.0 / len(df.columns) for k in df.columns}
    else:
        w = {k: float(weights.get(k, 0.0)) / w_sum for k in df.columns}

    blended = sum(df[k] * w[k] for k in df.columns)
    blended.name = "portfolio_value"
    return blended
