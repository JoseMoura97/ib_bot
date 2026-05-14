"""
Annual-FD loader: glue between the cached `annual_fd_parser` output and the
rebalancing engine's signal flow.

Why
---
Quiver's per-politician strategies (Nancy Pelosi, Dan Meuser, Donald Beyer,
Josh Gottheimer, Sheldon Whitehouse) are enriched with **annual FD holdings**
on top of PTRs. Our engine only saw PTRs, so we dramatically under-counted
the portfolio (e.g., Meuser had 74 PTR rows vs 158 tickered Schedule-A
positions in a single annual FD).

This loader exposes a snapshot — at a given "as of" date, what does the
politician's annual FD say they held (as a Ticker → weight DataFrame)? The
rebalancing engine can then concat this with PTR-derived deltas to produce
a more faithful portfolio mirror.

Conventions
-----------
- Annual FDs cover **calendar year N** and are typically filed by mid-year of
  year N+1. We treat the FD as the "known" portfolio for any rebalance date
  on or after the FD's filing date (we approximate filing date as Jun 30 of
  year N+1 if we don't have a precise filing date in cache).
- Weight: each holding's midpoint dollar value, normalized to sum to 1.0
  across **publicly-tradeable equities only** (asset_type in
  {ST, ETF, MF}). Non-tradeable assets (RP=real estate, OL=other long-term,
  OT=other, BD=bonds, CASH) are excluded from the weight basis.
- Subholding rollup: many lines are nested like "Schwab Account ⇒ AAPL".
  We dedupe on ticker; if a ticker appears multiple times, midpoint values
  are summed.

Coverage
--------
We currently parse FDs for these politicians (year 2019+):
    Daniel Meuser, Nancy Pelosi, Donald Beyer, Josh Gottheimer,
    Sheldon Whitehouse
Cached under `.cache/annual_fd/{lastname}_{firstname}_{year}.json`.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_ROOT = PROJECT_ROOT / ".cache" / "annual_fd"

# Politician strategy → (last_name, first_name) registered for annual-FD enrichment.
POLITICIAN_REGISTRY = {
    "Nancy Pelosi":       ("pelosi",       "nancy"),
    "Dan Meuser":         ("meuser",       "daniel"),
    "Donald Beyer":       ("beyer",        "donald"),
    "Josh Gottheimer":    ("gottheimer",   "josh"),
    "Sheldon Whitehouse": ("whitehouse",   "sheldon"),
}

# Per-politician opt-out: FDs for these names degraded CAGR vs PTR-only baseline,
# typically because their disclosed Schedule-A is dominated by mutual funds /
# trust accounts whose tickers our pricer can't resolve. Set
# ANNUAL_FD_DISABLED="Name1,Name2" in env to override the default. Set to ""
# to enable for everyone. (FD HELPS Gottheimer and Whitehouse — keep them OUT
# of this list.)
# Beyer is intentionally NOT in this list: his PTR filings stop on 2022-03-07,
# so without FD-enrichment we hold his March-2022 portfolio forever. The FD
# data is fund-heavy from 2022 on, but that's still more current than frozen
# PTR positions.
_DEFAULT_FD_DISABLED = {"Nancy Pelosi", "Dan Meuser"}


def _fd_disabled() -> set[str]:
    env = os.environ.get("ANNUAL_FD_DISABLED")
    if env is None:
        return set(_DEFAULT_FD_DISABLED)
    if env.strip() == "":
        return set()
    return {n.strip() for n in env.split(",") if n.strip()}

# Asset types eligible for tradeable-equity weight basis.
_TRADEABLE_TYPES = {"ST", "ETF", "MF"}

# Approximate annual-FD filing date (mid-year of the following calendar year).
# Used as the "known as of" date when we don't have a precise filing date.
def _approx_filing_date(year: int) -> datetime:
    return datetime(year + 1, 6, 30)


def _cache_key(strategy_name: str) -> Optional[tuple[str, str]]:
    """Strip (equal)/(size) suffix from a per-politician strategy name and
    look up the canonical (lastname, firstname) for cache file naming."""
    base = strategy_name
    for suf in [" (equal)", " (size)", " (alpha only)"]:
        if base.endswith(suf):
            base = base[: -len(suf)]
    return POLITICIAN_REGISTRY.get(base)


def _load_cached_holdings(last: str, first: str, year: int) -> Optional[list[dict]]:
    """Return cached holdings JSON for a (politician, year) — or None if missing."""
    # File written by annual_fd_parser uses bioguide_id when present, else
    # f"{lastname}_{firstname}". We don't have bioguide here so try the name form.
    for fn in (f"{last}_{first}_{year}.json", f"{last.title()}_{first.title()}_{year}.json"):
        p = CACHE_ROOT / fn
        if p.exists():
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
                return payload.get("holdings", [])
            except Exception as e:
                logger.warning("Bad annual FD cache %s: %s", p, e)
    return None


def annual_fd_snapshot(
    strategy_name: str,
    as_of_date: datetime,
    *,
    weighting: str = "size",
) -> Optional[pd.DataFrame]:
    """Build a DataFrame `[Ticker, Weight, Date, source]` representing the
    politician's most recent known annual FD as of `as_of_date`.

    Returns None if no FD is available (e.g. politician not in registry, or
    no parsed FD before as_of_date).
    """
    key = _cache_key(strategy_name)
    if key is None:
        return None
    last, first = key

    # Honor per-politician opt-out (default disables Pelosi + Beyer).
    base = strategy_name
    for suf in [" (equal)", " (size)", " (alpha only)"]:
        if base.endswith(suf):
            base = base[: -len(suf)]
    if base in _fd_disabled():
        return None

    # Find the most recent FD whose approximate filing date is <= as_of_date.
    candidates: list[tuple[int, list[dict]]] = []
    for year in range(2018, as_of_date.year + 1):
        if _approx_filing_date(year) > as_of_date:
            continue
        h = _load_cached_holdings(last, first, year)
        if h:
            candidates.append((year, h))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    year, holdings = candidates[0]

    # Roll up tradeable equities, dedupe on ticker.
    by_ticker: dict[str, float] = {}
    for row in holdings:
        if row.get("asset_type") not in _TRADEABLE_TYPES:
            continue
        t = (row.get("ticker") or "").strip().upper()
        if not t:
            continue
        lo, hi = row.get("value_low"), row.get("value_high")
        if lo is None or hi is None:
            continue
        midpoint = (float(lo) + float(hi)) / 2.0
        if midpoint <= 0:
            continue
        by_ticker[t] = by_ticker.get(t, 0.0) + midpoint

    if not by_ticker:
        return None

    if weighting == "equal":
        n = len(by_ticker)
        weights = {t: 1.0 / n for t in by_ticker}
    else:
        total = sum(by_ticker.values())
        weights = {t: v / total for t, v in by_ticker.items()}

    filing_date = _approx_filing_date(year)
    df = pd.DataFrame(
        [{"Ticker": t, "Weight": w, "Date": filing_date} for t, w in weights.items()]
    )
    df.attrs["source"] = "annual_fd"
    df.attrs["fd_year"] = year
    logger.info(
        "Annual FD snapshot: %s as of %s → %d tickers from FY%d filing",
        strategy_name, as_of_date.date(), len(df), year,
    )
    return df


def merge_fd_with_ptr_weights(
    strategy_name: str,
    as_of_date: datetime,
    ptr_weights: Optional[pd.DataFrame],
    *,
    fd_weight: float = 0.7,
    ptr_weight: float = 0.3,
    weighting: str = "size",
) -> Optional[pd.DataFrame]:
    """Blend annual-FD snapshot with PTR-derived weights.

    The FD captures full portfolio at year-end; PTRs capture mid-year deltas.
    We default to 70% FD / 30% PTR weight on the assumption that the FD is
    the more comprehensive source. Override via env if needed.

    Returns the FD-only snapshot if PTR data is empty, the PTR-only weights
    if no FD is cached, or a blended set if both are available.
    """
    # Allow override via env.
    fd_weight = float(os.environ.get("ANNUAL_FD_WEIGHT", fd_weight))
    ptr_weight = float(os.environ.get("PTR_WEIGHT", ptr_weight))
    total = fd_weight + ptr_weight
    if total <= 0:
        return ptr_weights
    fd_weight /= total
    ptr_weight /= total

    fd = annual_fd_snapshot(strategy_name, as_of_date, weighting=weighting)
    has_ptr = ptr_weights is not None and isinstance(ptr_weights, pd.DataFrame) and not ptr_weights.empty

    if fd is None and not has_ptr:
        return None
    if fd is None:
        return ptr_weights
    if not has_ptr:
        return fd

    # Both present — blend.
    # Normalize PTR weights to sum to 1 if they don't already.
    p = ptr_weights.copy()
    if "Weight" not in p.columns:
        # No weight column → can't blend.
        return fd
    p_total = p["Weight"].abs().sum()
    if p_total > 0:
        p["Weight"] = p["Weight"] / p_total

    f = fd.copy()
    f["Weight"] = f["Weight"] * fd_weight
    p["Weight"] = p["Weight"] * ptr_weight

    merged = pd.concat([f[["Ticker", "Weight"]], p[["Ticker", "Weight"]]], ignore_index=True)
    merged = merged.groupby("Ticker", as_index=False)["Weight"].sum()
    merged["Date"] = as_of_date
    merged.attrs["source"] = "annual_fd+ptr"
    return merged
