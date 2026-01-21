from __future__ import annotations

import pandas as pd

from app.services.portfolio_math import nav_blend_equity_curves


def test_nav_blend_align_and_weight():
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    a = pd.Series([100, 110, 121], index=idx)
    b = pd.Series([100, 90, 81], index=idx)
    blended = nav_blend_equity_curves({"A": a, "B": b}, {"A": 0.75, "B": 0.25})
    assert blended.iloc[0] == 100
    assert abs(blended.iloc[1] - (110 * 0.75 + 90 * 0.25)) < 1e-9


def test_nav_blend_defaults_to_equal_when_zero_weights():
    idx = pd.date_range("2024-01-01", periods=2, freq="D")
    a = pd.Series([100, 120], index=idx)
    b = pd.Series([100, 80], index=idx)
    blended = nav_blend_equity_curves({"A": a, "B": b}, {"A": 0.0, "B": 0.0})
    assert blended.iloc[1] == 100  # (120+80)/2
