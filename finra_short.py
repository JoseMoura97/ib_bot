"""
FINRA Off-Exchange Short Volume client.

Source: https://cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt
Format: pipe-delim, columns Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market.

ShortVolume here is the FINRA-reported off-exchange short volume (ATS + OTC + wholesalers
like Citadel/Virtu). Total off-exchange share of consolidated NMS volume. Used by the
"Off-Exchange Short Squeeze" strategy.

Files exist for trading days only; weekends + market holidays return 403.
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

_BASE_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ymd}.txt"
_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache", "finra_short")
_DEFAULT_UA = "ib_bot/1.0 josemiguelmoura97@gmail.com"

# Common-stock symbol pattern.
# Allows up to 5 letters (e.g. AAPL, MSFT) plus optional class suffix (.A, .B, -A, -B).
# Filters out warrants (FOOW, FOOWS), rights (FOOR), units (FOOU/FOOUN), preferreds (FOO-PA).
_VALID_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}(?:[.\-][AB])?$")


_NASDAQ_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
_OTHER_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"


class FinraShortVolume:
    """Daily FINRA consolidated short-volume fetcher with on-disk cache."""

    def __init__(self, user_agent: Optional[str] = None):
        os.makedirs(_CACHE_DIR, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent or _DEFAULT_UA})
        self.session.mount(
            "https://",
            HTTPAdapter(
                max_retries=Retry(
                    total=3,
                    connect=3,
                    read=3,
                    backoff_factor=0.75,
                    status_forcelist=(429, 500, 502, 503, 504),
                    allowed_methods=frozenset(("GET",)),
                    respect_retry_after_header=True,
                )
            ),
        )
        self._last_request_time = 0.0
        self._min_request_delay = 0.05  # 20 req/s is plenty for FINRA CDN
        self._etf_symbols: Optional[set[str]] = None
        self._common_symbols: Optional[set[str]] = None

    # ---- ETF/common-stock universe via NASDAQ Trader ----

    def _load_universe(self) -> None:
        """Populate ETF + common-stock sets from NASDAQ Trader's symbol directory.

        The files are refreshed daily by NASDAQ and have a stable ETF flag column
        ('Y'/'N'). We cache the combined set for 7 days.
        """
        cache = os.path.join(_CACHE_DIR, "nasdaq_universe.csv")
        max_age = 7 * 24 * 3600
        try:
            stale = (
                not os.path.exists(cache)
                or (time.time() - os.path.getmtime(cache)) > max_age
            )
        except Exception:
            stale = True
        if stale:
            rows: list[dict] = []
            for url in (_NASDAQ_LISTED, _OTHER_LISTED):
                try:
                    self._rate_limit()
                    r = self.session.get(url, timeout=20)
                    if r.status_code != 200:
                        continue
                    text = r.text
                except Exception as e:
                    log.warning(f"NASDAQ universe fetch failed for {url}: {e}")
                    continue
                lines = text.strip().split("\n")
                # Last line is "File Creation Time: ..."; drop anything not pipe-delimited matching header width
                header = lines[0].split("|")
                # nasdaqlisted: Symbol, otherlisted: ACT Symbol — normalize
                sym_col = "ACT Symbol" if "ACT Symbol" in header else "Symbol"
                for line in lines[1:]:
                    parts = line.split("|")
                    if len(parts) != len(header):
                        continue
                    row = dict(zip(header, parts))
                    if row.get("Test Issue", "N") == "Y":
                        continue
                    sym = row.get(sym_col, "").strip()
                    is_etf = (row.get("ETF", "N") or "N").strip().upper() == "Y"
                    if sym:
                        rows.append({"Symbol": sym, "IsETF": is_etf})
            if rows:
                pd.DataFrame(rows).to_csv(cache, index=False)
        # Load the cache
        if os.path.exists(cache):
            try:
                df = pd.read_csv(cache)
                self._etf_symbols = set(df.loc[df["IsETF"], "Symbol"].astype(str).str.upper())
                self._common_symbols = set(
                    df.loc[~df["IsETF"], "Symbol"].astype(str).str.upper()
                )
            except Exception as e:
                log.warning(f"NASDAQ universe load failed: {e}")
        if self._etf_symbols is None:
            self._etf_symbols = set()
            self._common_symbols = None  # signal "no filter available"

    @property
    def etf_symbols(self) -> set:
        if self._etf_symbols is None:
            self._load_universe()
        return self._etf_symbols or set()

    @property
    def common_symbols(self) -> Optional[set]:
        if self._etf_symbols is None:
            self._load_universe()
        return self._common_symbols

    # ---- low-level fetch + cache ----

    def _cache_path(self, dt: datetime) -> str:
        return os.path.join(_CACHE_DIR, f"CNMSshvol{dt.strftime('%Y%m%d')}.txt")

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_delay:
            time.sleep(self._min_request_delay - elapsed)
        self._last_request_time = time.time()

    def get_daily(self, dt: datetime) -> pd.DataFrame:
        """Return one day's full short-volume table. Empty DataFrame if missing/holiday."""
        path = self._cache_path(dt)
        # Old code cached every 403 as an empty file.  FINRA also uses 403 for
        # transient CDN denials, so this permanently poisoned real weekdays.
        if os.path.exists(path) and os.path.getsize(path) == 0 and dt.weekday() < 5:
            try:
                os.unlink(path)
            except OSError:
                pass
        if not os.path.exists(path):
            self._rate_limit()
            url = _BASE_URL.format(ymd=dt.strftime("%Y%m%d"))
            try:
                r = self.session.get(url, timeout=20)
            except Exception as e:
                log.warning(f"FINRA fetch error for {dt:%Y-%m-%d}: {e}")
                return pd.DataFrame()
            if r.status_code == 403:
                # Cache only obvious weekend misses.  A weekday 403 can be a
                # transient CDN denial and must remain retryable on the next run.
                if dt.weekday() >= 5:
                    with open(path, "wb") as f:
                        f.write(b"")
                return pd.DataFrame()
            if r.status_code != 200:
                log.warning(f"FINRA status {r.status_code} for {dt:%Y-%m-%d}")
                return pd.DataFrame()
            with open(path, "wb") as f:
                f.write(r.content)

        try:
            if os.path.getsize(path) == 0:
                return pd.DataFrame()
            df = pd.read_csv(path, sep="|", dtype={"Symbol": str, "Market": str})
        except Exception as e:
            log.warning(f"FINRA parse error for {dt:%Y-%m-%d}: {e}")
            return pd.DataFrame()

        # FINRA appends a "footer" row "FileFormatVersion|..." at EOF; strip if present.
        if not df.empty and df.iloc[-1].get("Date") in (None, "FileFormatVersion") or (
            not df.empty and not str(df.iloc[-1]["Date"]).isdigit()
        ):
            df = df.iloc[:-1].copy()

        if df.empty:
            return df

        df["Date"] = pd.to_datetime(df["Date"], format="%Y%m%d", errors="coerce")
        df["ShortVolume"] = pd.to_numeric(df["ShortVolume"], errors="coerce")
        df["TotalVolume"] = pd.to_numeric(df["TotalVolume"], errors="coerce")
        df = df.dropna(subset=["Date", "ShortVolume", "TotalVolume"])

        tv = df["TotalVolume"].replace(0, pd.NA)
        df["ShortRatio"] = (df["ShortVolume"] / tv).replace([float("inf"), float("-inf")], pd.NA)

        df = df.rename(columns={"Symbol": "Ticker"})
        return df

    # ---- aggregation API used by the strategy engine ----

    def get_window(
        self,
        end_date: datetime,
        lookback_days: int = 5,
        min_avg_volume: int = 500_000,
        common_stock_only: bool = True,
    ) -> pd.DataFrame:
        """Aggregate `lookback_days` of trading data ending at `end_date`.

        Returns DataFrame with columns:
            Ticker, ShortRatio (mean over window), AvgVolume, ShortVolumeMean, DaysPresent
        Filtered to liquid common stocks present on every day in the window.
        """
        if not isinstance(end_date, datetime):
            end_date = pd.to_datetime(end_date).to_pydatetime()

        frames: list[pd.DataFrame] = []
        dt = end_date
        # Walk backward across calendar days; allow ~lookback × 2 calendar days
        # to accumulate `lookback_days` of real trading data (weekends/holidays).
        budget = lookback_days * 3 + 10
        while len(frames) < lookback_days and budget > 0:
            df = self.get_daily(dt)
            if not df.empty:
                frames.append(df)
            dt -= timedelta(days=1)
            budget -= 1

        if not frames:
            return pd.DataFrame()

        wide = pd.concat(frames, ignore_index=True)
        # Universe filter — common stocks only (drops warrants/rights/units/preferreds)
        if common_stock_only:
            tk_upper = wide["Ticker"].astype(str).str.upper()
            mask = tk_upper.str.match(_VALID_SYMBOL_RE)
            # If NASDAQ Trader directory is available, additionally drop ETFs
            etfs = self.etf_symbols
            commons = self.common_symbols
            if etfs:
                mask &= ~tk_upper.isin(etfs)
            if commons is not None and len(commons) > 0:
                # Require symbol to appear in the common-stock universe.
                # Skipped silently if the directory failed to load.
                mask &= tk_upper.isin(commons)
            wide = wide[mask]

        agg = (
            wide.groupby("Ticker")
            .agg(
                ShortRatio=("ShortRatio", "mean"),
                AvgVolume=("TotalVolume", "mean"),
                ShortVolumeMean=("ShortVolume", "mean"),
                DaysPresent=("Date", "nunique"),
            )
            .reset_index()
        )
        # Liquidity filter: must trade every day in window AND meet min volume
        agg = agg[
            (agg["DaysPresent"] >= lookback_days)
            & (agg["AvgVolume"] >= min_avg_volume)
        ]
        return agg.reset_index(drop=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    c = FinraShortVolume()
    today = datetime(2026, 5, 18)
    df = c.get_window(today, lookback_days=5)
    print(f"window n={len(df)}, top-10 by ShortRatio:")
    print(df.sort_values("ShortRatio", ascending=False).head(10).to_string())
