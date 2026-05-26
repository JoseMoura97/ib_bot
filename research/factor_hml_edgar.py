"""
HML Factor Proxy from EDGAR + ib_bot Price Cache
=================================================

Builds a monthly HML-like factor (High minus Low book-to-market) using:
  - Book equity: SEC EDGAR companyconcept API (quarterly, free, no auth)
  - Market equity: ib_bot price cache × shares outstanding

Output:
  - Monthly pd.Series of HML_edgar returns (top-30% BE/ME minus bottom-30%)
  - Comparison with French HML (correlation, rolling 36m corr)
  - factor_hml_edgar.pkl — drop-in replacement for French HML in live model

Timeline: 2009-2026 (constrained by ib_bot price history)

Run:
  python3 research/factor_hml_edgar.py
"""
from __future__ import annotations

import json, math, os, pickle, time, warnings
from datetime import datetime, date
from typing import Any

import numpy as np
import pandas as pd
import requests

warnings.filterwarnings("ignore")

# ── paths ─────────────────────────────────────────────────────────────────────
OUT_DIR     = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR   = os.path.join(OUT_DIR, ".french_cache")
PRICE_DIR   = os.path.join(os.path.dirname(OUT_DIR), "ib_bot", ".cache", "yf_prices")
if not os.path.exists(PRICE_DIR):
    PRICE_DIR = os.path.join(os.path.dirname(OUT_DIR), ".cache", "yf_prices")
EDGAR_DIR   = os.path.join(CACHE_DIR, "edgar_be")
OUT_PKL     = os.path.join(CACHE_DIR, "hml_edgar.pkl")
OUT_CSV     = os.path.join(CACHE_DIR, "hml_edgar.csv")
os.makedirs(EDGAR_DIR, exist_ok=True)

# ── params ────────────────────────────────────────────────────────────────────
N_UNIVERSE      = 400    # top-N tickers by coverage (price history length)
QUINTILE_PCT    = 0.30   # top/bottom 30% for HML spread
RATE_LIMIT_SECS = 0.12   # stay under 10 req/s EDGAR rate limit
MIN_STOCKS      = 30     # minimum stocks per month to include in factor

EDGAR_BASE      = "https://data.sec.gov"
TICKERS_URL     = "https://www.sec.gov/files/company_tickers.json"
HEADERS         = {"User-Agent": "ib_bot-research/1.0 contact@example.com"}

# ── BE XBRL concept priority list ─────────────────────────────────────────────
BE_CONCEPTS = [
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "CommonStockholdersEquity",
    "TotalEquityAttributableToOwnersOfParent",
]


# ══════════════════════════════════════════════════════════════════════════════
# 1. EDGAR TICKER → CIK MAP
# ══════════════════════════════════════════════════════════════════════════════

def load_ticker_cik_map(force: bool = False) -> dict[str, int]:
    cache_path = os.path.join(CACHE_DIR, "ticker_cik_map.json")
    if os.path.exists(cache_path) and not force:
        with open(cache_path) as f:
            return json.load(f)

    print("  Downloading EDGAR ticker→CIK map...")
    r = requests.get(TICKERS_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    raw = r.json()
    # Format: {idx: {cik_str, ticker, title}}
    mapping = {}
    for v in raw.values():
        mapping[v["ticker"].upper()] = int(v["cik_str"])

    with open(cache_path, "w") as f:
        json.dump(mapping, f)
    print(f"  Mapped {len(mapping)} tickers")
    return mapping


# ══════════════════════════════════════════════════════════════════════════════
# 2. PRICE CACHE LOADER
# ══════════════════════════════════════════════════════════════════════════════

def load_price_close(ticker: str) -> pd.Series | None:
    """Load close price from ib_bot pickle cache."""
    path = os.path.join(PRICE_DIR, f"{ticker}.pkl")
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_pickle(path)
        # Handle both flat and MultiIndex columns
        if isinstance(df.columns, pd.MultiIndex):
            if ("Close", ticker) in df.columns:
                s = df[("Close", ticker)]
            elif "Close" in df.columns.get_level_values(0):
                s = df.xs("Close", axis=1, level=0).iloc[:, 0]
            else:
                return None
        elif "Close" in df.columns:
            s = df["Close"]
        else:
            return None
        s = s.dropna()
        return s.rename(ticker)
    except Exception:
        return None


def load_shares_outstanding(ticker: str) -> float | None:
    """Get shares outstanding from fundamentals cache."""
    fund_path = os.path.join(os.path.dirname(PRICE_DIR), "factor_fundamentals.pkl")
    if not os.path.exists(fund_path):
        return None
    try:
        df = pd.read_pickle(fund_path)
        if ticker in df.index and "sharesOutstanding" in df.columns:
            v = df.loc[ticker, "sharesOutstanding"]
            if pd.notna(v) and v > 0:
                return float(v)
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 3. EDGAR BOOK EQUITY FETCHER
# ══════════════════════════════════════════════════════════════════════════════

SHARES_DIR = os.path.join(CACHE_DIR, "edgar_shares")
os.makedirs(SHARES_DIR, exist_ok=True)

SHARES_CONCEPTS = [
    "CommonStockSharesOutstanding",
    "CommonSharesOutstanding",
    "SharesOutstanding",
]


def fetch_shares_series(cik: int, ticker: str) -> pd.Series | None:
    """
    Fetch historical shares outstanding from EDGAR for one company.
    Returns pd.Series indexed by period end date, values in shares.
    Cached per-ticker.
    """
    cache_path = os.path.join(SHARES_DIR, f"{ticker}_{cik}.pkl")
    if os.path.exists(cache_path):
        return pd.read_pickle(cache_path)

    for concept in SHARES_CONCEPTS:
        url = f"{EDGAR_BASE}/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{concept}.json"
        try:
            time.sleep(RATE_LIMIT_SECS)
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            data = r.json()

            units = data.get("units", {})
            shares_data = units.get("shares", [])
            if not shares_data:
                continue

            records = []
            for item in shares_data:
                form = item.get("form", "")
                if form not in ("10-K", "10-Q", "10-K/A", "10-Q/A"):
                    continue
                end = item.get("end")
                val = item.get("val")
                if end and val is not None and float(val) > 0:
                    records.append((pd.to_datetime(end), float(val)))

            if not records:
                continue

            s = pd.Series(dict(records))
            s = s[~s.index.duplicated(keep="last")].sort_index()
            s.to_pickle(cache_path)
            return s

        except requests.exceptions.RequestException:
            time.sleep(1.0)
            continue
        except Exception:
            continue

    s = pd.Series(dtype=float)
    s.to_pickle(cache_path)
    return s


def fetch_be_series(cik: int, ticker: str) -> pd.Series | None:
    """
    Fetch quarterly book equity from EDGAR for one company.
    Returns pd.Series indexed by period end date, values in USD.
    Cached per-ticker.
    """
    cache_path = os.path.join(EDGAR_DIR, f"{ticker}_{cik}.pkl")
    if os.path.exists(cache_path):
        return pd.read_pickle(cache_path)

    for concept in BE_CONCEPTS:
        url = f"{EDGAR_BASE}/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{concept}.json"
        try:
            time.sleep(RATE_LIMIT_SECS)
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            data = r.json()

            units = data.get("units", {})
            usd_data = units.get("USD", [])
            if not usd_data:
                continue

            # Keep only 10-K / 10-Q filings (annual or quarterly)
            records = []
            for item in usd_data:
                form = item.get("form", "")
                if form not in ("10-K", "10-Q", "10-K/A", "10-Q/A"):
                    continue
                end = item.get("end")
                val = item.get("val")
                if end and val is not None:
                    records.append((pd.to_datetime(end), float(val)))

            if not records:
                continue

            s = pd.Series(dict(records))
            s = s[~s.index.duplicated(keep="last")].sort_index()
            s.to_pickle(cache_path)
            return s

        except requests.exceptions.RequestException:
            time.sleep(1.0)
            continue
        except Exception:
            continue

    # Cache empty result to avoid re-fetching
    s = pd.Series(dtype=float)
    s.to_pickle(cache_path)
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 4. BUILD MONTHLY BE/ME PANEL
# ══════════════════════════════════════════════════════════════════════════════

def build_monthly_beme(tickers: list[str], cik_map: dict[str, int],
                        price_cache: dict[str, pd.Series]) -> pd.DataFrame:
    """
    For each month t, compute BE/ME for each ticker as:
      BE/ME = last_reported_book_equity / market_cap_t

    Returns wide DataFrame: rows=months, cols=tickers, values=BE/ME.
    """
    # Get all months from price data
    all_months = pd.date_range(start="2009-01-01", end=pd.Timestamp.now(), freq="MS")

    beme_panel = {}
    n = len(tickers)

    for i, ticker in enumerate(tickers):
        if i % 50 == 0:
            print(f"    [{i}/{n}] {ticker}...", flush=True)

        if ticker not in cik_map:
            continue
        cik = cik_map[ticker]

        price = price_cache.get(ticker)
        if price is None or len(price) < 120:
            continue

        be = fetch_be_series(cik, ticker)
        if be is None or len(be) == 0:
            continue

        # Resample BE to monthly: use last known value (no look-ahead)
        be_monthly = be.resample("MS").last().reindex(all_months, method="ffill")

        # Market cap: monthly close price × HISTORICAL shares outstanding from EDGAR
        price_monthly = price.resample("MS").last().reindex(all_months)
        shares_hist = fetch_shares_series(cik, ticker)

        if shares_hist is not None and len(shares_hist) > 4:
            # Use historical shares — resample to monthly, forward-fill
            shares_monthly = (shares_hist.resample("MS").last()
                              .reindex(all_months, method="ffill"))
            mktcap = price_monthly * shares_monthly
        else:
            # Fallback to static shares if EDGAR shares unavailable
            shares_static = load_shares_outstanding(ticker)
            if shares_static is None or shares_static <= 0:
                continue
            mktcap = price_monthly * shares_static

        # BE/ME ratio (book equity / market equity)
        beme = be_monthly / mktcap
        # Filter: BE/ME in reasonable range (0.001 to 50)
        beme = beme.where((beme > 0.001) & (beme < 50))

        beme_panel[ticker] = beme

    if not beme_panel:
        return pd.DataFrame()

    panel = pd.DataFrame(beme_panel).dropna(how="all", axis=0)
    print(f"  BE/ME panel: {panel.shape[0]} months × {panel.shape[1]} tickers")
    return panel


# ══════════════════════════════════════════════════════════════════════════════
# 5. CONSTRUCT HML FACTOR
# ══════════════════════════════════════════════════════════════════════════════

def build_hml_factor(beme_panel: pd.DataFrame,
                     price_cache: dict[str, pd.Series]) -> pd.Series:
    """
    At each month t:
      1. Sort stocks by BE/ME as of t-1 (avoid look-ahead)
      2. Top-30% = value, Bottom-30% = growth
      3. HML_t = equal-weight return of value − growth

    Returns monthly HML factor series.
    """
    tickers = beme_panel.columns.tolist()
    # Build return panel (monthly)
    all_months = beme_panel.index

    ret_panel = {}
    for tk in tickers:
        p = price_cache.get(tk)
        if p is not None and len(p) > 24:
            r = p.resample("MS").last().pct_change()
            ret_panel[tk] = r

    ret_panel = pd.DataFrame(ret_panel).reindex(all_months)

    hml_series = {}

    for i, month in enumerate(all_months[1:], 1):
        prev_month = all_months[i - 1]

        # BE/ME as of previous month end (no look-ahead)
        beme_t = beme_panel.loc[prev_month].dropna()
        if len(beme_t) < MIN_STOCKS:
            continue

        # Current month returns
        if month not in ret_panel.index:
            continue
        ret_t = ret_panel.loc[month].dropna()

        # Stocks with both BE/ME signal and return
        common = beme_t.index.intersection(ret_t.index)
        if len(common) < MIN_STOCKS:
            continue

        beme_sort = beme_t.loc[common].sort_values()
        n = len(beme_sort)

        q_lo = int(n * QUINTILE_PCT)
        q_hi = int(n * (1 - QUINTILE_PCT))

        growth_tickers = beme_sort.iloc[:q_lo].index     # low BE/ME = growth
        value_tickers  = beme_sort.iloc[q_hi:].index     # high BE/ME = value

        ret_value  = ret_t.loc[value_tickers].mean()
        ret_growth = ret_t.loc[growth_tickers].mean()
        hml_series[month] = ret_value - ret_growth

    return pd.Series(hml_series, name="HML_edgar").sort_index()


# ══════════════════════════════════════════════════════════════════════════════
# 6. LOAD FRENCH HML FOR COMPARISON
# ══════════════════════════════════════════════════════════════════════════════

def load_french_hml() -> pd.Series:
    import io, zipfile
    cache_path = os.path.join(CACHE_DIR, "3factor.csv")
    url = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip"
    if not os.path.exists(cache_path):
        r = requests.get(url, timeout=60)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        csv = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        with open(cache_path, "w") as f:
            f.write(z.read(csv).decode("utf-8", errors="replace"))

    rows = []
    with open(cache_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4 and len(parts[0]) == 6 and parts[0].isdigit():
                    yr, mo = int(parts[0][:4]), int(parts[0][4:])
                    if 1 <= mo <= 12 and yr >= 1920:
                        rows.append((f"{yr}-{mo:02d}", float(parts[3])))
            except (ValueError, IndexError):
                continue

    s = pd.Series(dict(rows))
    s.index = pd.to_datetime(s.index, format="%Y-%m").to_period("M").to_timestamp()
    return (s / 100.0).rename("HML_french")


# ══════════════════════════════════════════════════════════════════════════════
# 7. VALIDATE + REPORT
# ══════════════════════════════════════════════════════════════════════════════

def report_comparison(hml_edgar: pd.Series, hml_french: pd.Series) -> None:
    common = hml_edgar.index.intersection(hml_french.index)
    he = hml_edgar.loc[common]
    hf = hml_french.loc[common]

    full_corr = he.corr(hf)
    roll_corr = he.rolling(36).corr(hf)

    print(f"\n  Validation: French HML vs EDGAR HML")
    print(f"    Period:     {common[0].strftime('%Y-%m')} → {common[-1].strftime('%Y-%m')}")
    print(f"    N months:   {len(common)}")
    print(f"    Full corr:  {full_corr:.3f}")
    print(f"    36m corr:   min={roll_corr.min():.3f} mean={roll_corr.mean():.3f} max={roll_corr.max():.3f}")

    # CAGR comparison
    def cagr(s):
        s = s.dropna()
        years = len(s) / 12
        return float((1 + s).prod() ** (1/years) - 1)

    print(f"    French CAGR: {cagr(hf):.1%}")
    print(f"    Edgar  CAGR: {cagr(he):.1%}")


# ══════════════════════════════════════════════════════════════════════════════
# 8. MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("HML Factor Proxy from EDGAR + ib_bot Price Cache")
    print("=" * 60)

    # 1. Ticker universe — use ib_bot price files sorted by size
    print(f"\n[1/5] Building ticker universe from {PRICE_DIR}...")
    price_files = [f for f in os.listdir(PRICE_DIR) if f.endswith(".pkl")]
    all_tickers = [f.replace(".pkl", "") for f in price_files]
    print(f"  Found {len(all_tickers)} tickers in cache")

    # Load fundamentals to filter to US large-cap only
    fund_path = os.path.join(os.path.dirname(PRICE_DIR), "factor_fundamentals.pkl")
    fund_df = pd.read_pickle(fund_path) if os.path.exists(fund_path) else None

    # Score tickers: prefer US large-cap with good price coverage
    ticker_scores = {}
    print(f"  Scoring tickers (loading prices for {min(len(all_tickers),N_UNIVERSE*3)} candidates)...")

    price_cache: dict[str, pd.Series] = {}
    checked = 0
    for tk in sorted(all_tickers):
        p = load_price_close(tk)
        if p is None or len(p) < 120:
            continue
        # Prefer tickers in fundamentals cache (US listed)
        score = len(p)
        if fund_df is not None and tk in fund_df.index:
            mc = fund_df.loc[tk, "marketCap"] if "marketCap" in fund_df.columns else 0
            if pd.notna(mc) and mc > 0:
                score += min(int(math.log10(mc + 1)) * 100, 1000)

        # Skip obvious non-US (tickers with many non-alpha chars)
        if len(tk) > 5 or "." in tk or not tk.replace("-", "").isalpha():
            continue

        ticker_scores[tk] = score
        price_cache[tk] = p
        checked += 1

    # Select top-N by score
    universe = sorted(ticker_scores, key=ticker_scores.get, reverse=True)[:N_UNIVERSE]
    print(f"  Selected {len(universe)} tickers")

    # 2. Ticker → CIK map
    print(f"\n[2/5] Loading EDGAR CIK mapping...")
    cik_map = load_ticker_cik_map()
    mapped = [tk for tk in universe if tk in cik_map]
    print(f"  {len(mapped)}/{len(universe)} tickers have EDGAR CIK")

    # 3. Fetch book equity from EDGAR
    print(f"\n[3/5] Fetching book equity from EDGAR (cached: {len(os.listdir(EDGAR_DIR))} files)...")
    beme_panel = build_monthly_beme(mapped, cik_map, price_cache)

    if beme_panel.empty:
        print("  ERROR: Could not build BE/ME panel")
        return

    # 4. Build HML factor
    print(f"\n[4/5] Building monthly HML factor...")
    hml_edgar = build_hml_factor(beme_panel, price_cache)
    print(f"  HML_edgar: {len(hml_edgar)} months | {hml_edgar.index[0].strftime('%Y-%m')} → {hml_edgar.index[-1].strftime('%Y-%m')}")
    print(f"  Mean: {hml_edgar.mean():.4f}  Std: {hml_edgar.std():.4f}")

    # 5. Validate against French HML
    print(f"\n[5/5] Validating against French HML...")
    hml_french = load_french_hml()
    report_comparison(hml_edgar, hml_french)

    # Save outputs
    hml_edgar.to_pickle(OUT_PKL)
    hml_edgar.to_csv(OUT_CSV)
    print(f"\n  Saved {OUT_PKL}")
    print(f"  Saved {OUT_CSV}")
    print("\nDone. Use hml_edgar as drop-in for French HML in factor_regime_live.py")
    return hml_edgar


if __name__ == "__main__":
    main()
