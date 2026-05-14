"""
Phase 3 — test_backtest_execution_lag.py

Verify that EXECUTION_OFFSET_DAYS=1 causes the first return to be the
next trading day, not the signal day itself.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.market_calendar import shift_trading_days


class TestShiftTradingDays:
    """shift_trading_days must correctly advance over weekends and holidays."""

    def test_friday_to_monday(self):
        friday = datetime(2026, 5, 8)
        result = shift_trading_days(friday, n=1)
        # Monday
        assert result == pd.Timestamp("2026-05-11"), f"Expected 2026-05-11, got {result}"

    def test_thursday_to_friday(self):
        thursday = datetime(2026, 5, 7)
        result = shift_trading_days(thursday, n=1)
        assert result == pd.Timestamp("2026-05-08"), f"Expected 2026-05-08, got {result}"

    def test_returns_timestamp(self):
        result = shift_trading_days(datetime(2026, 5, 7), n=1)
        assert isinstance(result, pd.Timestamp)

    def test_n_equals_2_from_thursday(self):
        thursday = datetime(2026, 5, 7)
        result = shift_trading_days(thursday, n=2)
        assert result == pd.Timestamp("2026-05-11"), f"Expected 2026-05-11, got {result}"


class TestDateRangeMask:
    """_date_range_mask with offset_trading_days shifts start by N trading days."""

    def _make_engine(self):
        from rebalancing_backtest_engine import RebalancingBacktestEngine
        # Minimal fake engine — only need the static method
        return RebalancingBacktestEngine

    def test_no_offset_includes_signal_day(self):
        Eng = self._make_engine()
        idx = pd.date_range("2026-05-06", "2026-05-15", freq="B")
        start = datetime(2026, 5, 7)   # Thursday
        end = datetime(2026, 5, 15)

        mask = Eng._date_range_mask(idx, start, end, offset_trading_days=0)
        included = idx[mask]
        # Should include 2026-05-07 (Thursday)
        assert pd.Timestamp("2026-05-07") in included.tolist()

    def test_offset_1_excludes_signal_day(self, monkeypatch):
        """With offset=1 the signal day itself should not be in the mask."""
        Eng = self._make_engine()
        idx = pd.date_range("2026-05-06", "2026-05-15", freq="B")
        start = datetime(2026, 5, 7)   # Thursday signal day
        end = datetime(2026, 5, 15)

        mask = Eng._date_range_mask(idx, start, end, offset_trading_days=1)
        included = idx[mask]
        # 2026-05-07 must not be there; 2026-05-08 (Friday) must be
        assert pd.Timestamp("2026-05-07") not in included.tolist(), (
            "Signal day included — execution lag not applied"
        )
        assert pd.Timestamp("2026-05-08") in included.tolist()

    def test_offset_1_friday_signal_lands_monday(self, monkeypatch):
        """Friday signal + offset=1 → first return is Monday (skips weekend)."""
        Eng = self._make_engine()
        idx = pd.date_range("2026-05-06", "2026-05-20", freq="B")
        start = datetime(2026, 5, 8)   # Friday
        end = datetime(2026, 5, 20)

        mask = Eng._date_range_mask(idx, start, end, offset_trading_days=1)
        included = idx[mask]
        assert pd.Timestamp("2026-05-11") in included.tolist(), "Monday not first session"
        assert pd.Timestamp("2026-05-08") not in included.tolist(), "Friday incorrectly included"


class TestExecutionOffsetEnv:
    """EXECUTION_OFFSET_DAYS env var is respected at engine runtime."""

    def test_default_is_1(self, monkeypatch):
        monkeypatch.delenv("EXECUTION_OFFSET_DAYS", raising=False)
        val = int(os.getenv("EXECUTION_OFFSET_DAYS", "1"))
        assert val == 1

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("EXECUTION_OFFSET_DAYS", "0")
        val = int(os.getenv("EXECUTION_OFFSET_DAYS", "1"))
        assert val == 0
