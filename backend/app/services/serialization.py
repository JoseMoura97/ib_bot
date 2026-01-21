from __future__ import annotations

from typing import Any

import pandas as pd


def equity_curve_to_records(equity_curve: Any) -> list[dict]:
    """
    Convert various equity curve shapes (DataFrame/Series/list) into JSON-friendly records:
      [{"date":"YYYY-MM-DD", "value": 100000.0}, ...]
    """
    if equity_curve is None:
        return []

    if isinstance(equity_curve, list):
        # Assume already records or [date,value] tuples.
        if equity_curve and isinstance(equity_curve[0], dict):
            return equity_curve
        out = []
        for item in equity_curve:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                out.append({"date": str(pd.Timestamp(item[0]).date()), "value": float(item[1])})
        return out

    if isinstance(equity_curve, pd.Series):
        s = equity_curve.dropna()
        return [{"date": str(pd.Timestamp(idx).date()), "value": float(val)} for idx, val in s.items()]

    if isinstance(equity_curve, pd.DataFrame):
        df = equity_curve.copy()
        if "portfolio_value" in df.columns:
            s = df["portfolio_value"]
            return equity_curve_to_records(s)
        # fallback: first numeric column
        for c in df.columns:
            try:
                s = pd.to_numeric(df[c], errors="coerce").dropna()
                if not s.empty:
                    return equity_curve_to_records(s)
            except Exception:
                continue
        return []

    return []
