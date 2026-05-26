"""
Backfill FINRA CNMS short-volume daily files for the gap
2018-08-01 → 2023-04-19 (the cache currently starts 2023-04-20).

Downloads ~1 200 business-day files from the FINRA CDN.
I/O-bound only — does NOT touch the price cache or run any backtest.

Rate: ~1 req / 0.25s  →  ~300 req/min, well within CDN limits.
Each file is 50-200 KB compressed text.
Estimated time: 8-15 min.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, "/app")

import requests

CACHE_DIR = "/app/.cache/finra_short"
START = date(2018, 8, 1)
END   = date(2023, 4, 19)          # day before existing cache
CDN   = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{}.txt"
HEADERS = {"User-Agent": "Mozilla/5.0"}
DELAY = 0.25                        # seconds between requests

os.makedirs(CACHE_DIR, exist_ok=True)

def trading_days(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:         # Mon–Fri only; skip weekends
            yield d
        d += timedelta(days=1)

def main():
    days = list(trading_days(START, END))
    total = len(days)
    downloaded = 0
    skipped = 0
    missing = 0

    print(f"Backfilling FINRA {START} → {END}  ({total} weekdays)")

    for i, d in enumerate(days, 1):
        ds = d.strftime("%Y%m%d")
        out_path = os.path.join(CACHE_DIR, f"CNMSshvol{ds}.txt")

        if os.path.exists(out_path):
            skipped += 1
            if i % 100 == 0:
                print(f"  [{i}/{total}] {ds} already cached — skipping")
            continue

        url = CDN.format(ds)
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
        except Exception as e:
            print(f"  [{i}/{total}] {ds} network error: {e}")
            time.sleep(DELAY)
            continue

        if r.status_code == 200 and r.content:
            with open(out_path, "wb") as f:
                f.write(r.content)
            downloaded += 1
            if i % 50 == 0 or i <= 5:
                kb = len(r.content) // 1024
                print(f"  [{i}/{total}] {ds} OK  {kb} KB  (total downloaded: {downloaded})")
        elif r.status_code == 403:
            # Holiday or market-closed day — write empty sentinel
            with open(out_path, "wb") as f:
                f.write(b"")
            missing += 1
        else:
            print(f"  [{i}/{total}] {ds} HTTP {r.status_code} — skipping")

        time.sleep(DELAY)

    print(f"\nDone. Downloaded={downloaded}  Skipped(already cached)={skipped}  "
          f"Missing/holiday={missing}  Total processed={i}")

if __name__ == "__main__":
    main()
