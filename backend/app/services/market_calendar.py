from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple

import pandas as pd


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
