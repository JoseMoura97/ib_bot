from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple

import pandas as pd


def shift_trading_days(date: datetime | pd.Timestamp | str, n: int = 1, calendar_name: str = "XNYS") -> pd.Timestamp:
    """Return the Nth NYSE trading day strictly after *date*.

    Friday + 1 → Monday (skipping weekend/holidays).  Raises ImportError if
    exchange_calendars is unavailable; callers should guard or fall back to
    calendar days when needed.

    Args:
        date: signal date (tz-naive or tz-aware; tz stripped internally).
        n: number of trading days to advance (default 1).
        calendar_name: exchange_calendars calendar name (default "XNYS").
    """
    try:
        import exchange_calendars as ec
    except ImportError:
        # Fallback: advance by n*2 calendar days (rough approximation)
        ts = pd.Timestamp(date)
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        return ts + pd.Timedelta(days=n * 2)

    ts = pd.Timestamp(date)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)

    cal = ec.get_calendar(calendar_name)
    # sessions_in_range requires tz-naive dates within calendar bounds
    search_start = ts + pd.Timedelta(days=1)
    search_end = min(search_start + pd.Timedelta(days=n * 4 + 15), pd.Timestamp(cal.last_session))
    if search_start > search_end:
        return ts

    sessions = cal.sessions_in_range(search_start, search_end)
    sessions_plain = [s.tz_localize(None) if s.tzinfo else s for s in sessions]
    if len(sessions_plain) >= n:
        return sessions_plain[n - 1]
    # Fallback if calendar horizon reached
    return ts + pd.Timedelta(days=n * 2)


def market_is_open(calendar_name: str = "XNYS", *, now: datetime | None = None) -> Tuple[bool, str | None]:
    """
    Returns (is_open, reason). Uses exchange_calendars for holiday + market hours checks.
    """
    try:
        import exchange_calendars as xc
    except Exception as e:  # pragma: no cover - dependency missing
        return False, f"exchange_calendars unavailable: {type(e).__name__}"

    dt = now or datetime.utcnow()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    try:
        cal = xc.get_calendar(calendar_name)
    except Exception as e:
        return False, f"unknown calendar {calendar_name}: {type(e).__name__}"

    ts = pd.Timestamp(dt)
    if cal.is_open_on_minute(ts):
        return True, None

    try:
        next_open = cal.next_open(ts)
        return False, f"market closed (next open: {next_open})"
    except Exception:
        return False, "market closed"
