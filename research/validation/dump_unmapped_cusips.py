"""
Dump unmapped CUSIPs for a fund to help improve coverage.

This is the practical way to "fix" alignment with Quiver without Premium:
Quiver has a big CUSIP->ticker mapping pipeline; we need one too.

Usage:
  python research/validation/dump_unmapped_cusips.py

Optional env:
  OPENFIGI_API_KEY=...  (if set, many CUSIPs will auto-map and be cached)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    from sec_edgar import SECEdgarClient

    fund = os.environ.get("FUND_NAME", "Scion Asset Management")
    as_of = os.environ.get("AS_OF_DATE")  # e.g. 2026-01-01
    as_of_date = pd.to_datetime(as_of).to_pydatetime() if as_of else datetime.now()

    client = SECEdgarClient()
    df = client.get_holdings_as_of_date(fund, as_of_date=as_of_date, search_limit=80)
    if df is None or df.empty:
        print(f"No holdings returned for {fund} as of {as_of_date:%Y-%m-%d}")
        return

    # Normalize columns
    for col in ["CUSIP", "Ticker", "Name", "Value", "PutCall", "TitleOfClass"]:
        if col not in df.columns:
            df[col] = None

    # Identify unmapped CUSIPs (Ticker missing)
    unmapped = df[df["CUSIP"].notna() & df["Ticker"].isna()].copy()
    if unmapped.empty:
        print(f"All holdings mapped to tickers for {fund} as of {as_of_date:%Y-%m-%d}")
        return

    unmapped["Value"] = pd.to_numeric(unmapped["Value"], errors="coerce")
    unmapped = unmapped.sort_values("Value", ascending=False, na_position="last")

    print(f"Fund: {fund}")
    print(f"As-of: {as_of_date:%Y-%m-%d}")
    print(f"Holdings rows: {len(df)} | Unmapped CUSIPs: {len(unmapped)}")
    print("")
    show = unmapped[["CUSIP", "Name", "TitleOfClass", "PutCall", "Value"]].head(50)
    with pd.option_context("display.max_colwidth", 40, "display.width", 140):
        print(show.to_string(index=False))


if __name__ == "__main__":
    main()

