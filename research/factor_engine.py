"""
Factor scoring engine for IB Bot factor investing strategies.

Factors implemented:
  - Momentum     : 12-1 month price return (ex last month)
  - Low Vol      : negative annualized realized volatility
  - Value        : earnings yield + book yield composite
  - Quality      : ROE + gross margin composite
  - Investment   : negative asset growth (CMA-style)
  - Size         : negative log market cap (small-cap premium)
  - Multi-factor : equal-weight z-score composite

All factor scores are oriented: HIGHER = MORE ATTRACTIVE.
"""
from __future__ import annotations

import math
import os
import pickle
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ── paths ──────────────────────────────────────────────────────────────────
CACHE_DIR = os.environ.get("PRICE_CACHE_DIR", "/app/.cache/yf_prices")
FUND_CACHE = os.environ.get("FUND_CACHE_PATH",
                             "/app/.cache/factor_fundamentals.pkl")
HIST_FUND_CACHE = os.environ.get("HIST_FUND_CACHE_PATH",
                                  "/app/.cache/factor_historical_fundamentals.pkl")

# ── helpers ────────────────────────────────────────────────────────────────

def _load_ticker(ticker: str) -> Optional[pd.Series]:
    """Return Close price Series from .pkl cache, or None if unavailable."""
    path = os.path.join(CACHE_DIR, f"{ticker}.pkl")
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_pickle(path)
        if isinstance(df.columns, pd.MultiIndex):
            # Batched yfinance download format
            if "Close" in df.columns.get_level_values(0):
                s = df["Close"].iloc[:, 0]
            else:
                return None
        else:
            s = df["Close"]
        s.index = pd.to_datetime(s.index)
        s = s.sort_index().astype(float)

        # Sanitize: remove extreme single-day price jumps and invalid prices.
        # Iterates until convergence to handle runs of consecutive bad values
        # (e.g. a ticker that alternates between a real price level and a bad one).
        # Each pass: replace prices ≤0 or >5x prior day with NaN and ffill.
        s = s.copy()
        for _ in range(20):
            ratios = s / s.shift(1)
            bad = (s <= 0) | (ratios > 5.0)
            if not bad.any():
                break
            s[bad] = np.nan
            s = s.ffill()
        s = s.dropna()

        return s
    except Exception:
        return None


def _prior_business_day(date: datetime, offset: int = 1) -> datetime:
    d = pd.Timestamp(date) - pd.offsets.BDay(offset)
    return d.to_pydatetime()


def _zscore(series: pd.Series) -> pd.Series:
    """Winsorize at 3σ then z-score."""
    s = series.dropna()
    if len(s) < 5:
        return series * 0.0
    std = s.std()
    if std == 0:
        return series * 0.0
    clipped = s.clip(s.mean() - 3 * std, s.mean() + 3 * std)
    return (clipped - clipped.mean()) / clipped.std()


# ── universe builder ───────────────────────────────────────────────────────

class FactorEngine:
    """Compute per-ticker factor scores as of a given date."""

    def __init__(
        self,
        cache_dir: str = CACHE_DIR,
        fund_cache_path: str = FUND_CACHE,
        hist_fund_cache_path: str = HIST_FUND_CACHE,
    ):
        self.cache_dir = cache_dir
        self.fund_cache_path = fund_cache_path
        self.hist_fund_cache_path = hist_fund_cache_path
        self._price_cache: Dict[str, pd.Series] = {}
        self._fundamentals: Optional[pd.DataFrame] = None
        self._hist_fundamentals: Optional[dict] = None

    # ── price loading ─────────────────────────────────────────────────────

    def get_available_tickers(self) -> List[str]:
        return [
            f.replace(".pkl", "")
            for f in os.listdir(self.cache_dir)
            if f.endswith(".pkl")
        ]

    def load_prices(self, tickers: List[str]) -> Dict[str, pd.Series]:
        """Load Close series for requested tickers; cache in memory."""
        for t in tickers:
            if t not in self._price_cache:
                s = _load_ticker(t)
                if s is not None:
                    self._price_cache[t] = s
        return {t: self._price_cache[t] for t in tickers if t in self._price_cache}

    def get_universe(
        self,
        as_of_date: datetime,
        min_history_days: int = 300,
        min_avg_volume: float = 200_000,
    ) -> List[str]:
        """Return tickers with sufficient price history as of date."""
        cutoff = pd.Timestamp(as_of_date) - pd.Timedelta(days=min_history_days + 60)
        result = []
        for ticker in self.get_available_tickers():
            s = _load_ticker(ticker)
            if s is None or len(s) < min_history_days:
                continue
            # Check eligibility using as-of slice (do NOT cache trimmed version)
            s_asof = s[s.index <= pd.Timestamp(as_of_date)]
            if len(s_asof) < min_history_days:
                continue
            if s_asof.index.min() > cutoff:
                continue
            # Check last close is recent (within 20 calendar days)
            last_date = s_asof.index.max()
            if (pd.Timestamp(as_of_date) - last_date).days > 20:
                continue
            # Minimum price filter: exclude penny stocks below $0.50
            # (these typically have data quality issues that survive sanitization)
            last_price = float(s_asof.iloc[-1])
            if last_price < 0.50:
                continue
            # Cache FULL price series (not trimmed) so mark-to-market works
            self._price_cache[ticker] = s
            result.append(ticker)
        return result

    # ── price factor scoring ──────────────────────────────────────────────

    def score_momentum(
        self,
        tickers: List[str],
        as_of_date: datetime,
        lookback_months: int = 12,
        skip_months: int = 1,
    ) -> pd.Series:
        """12-1 month price momentum (ex-last-month)."""
        date = pd.Timestamp(as_of_date)
        long_ago  = date - pd.DateOffset(months=lookback_months)
        short_ago = date - pd.DateOffset(months=skip_months)

        scores = {}
        for t in tickers:
            s = self._price_cache.get(t)
            if s is None:
                continue
            s = s[s.index <= date]
            # Price ~12m ago
            p_start = s[s.index <= long_ago]
            # Price ~1m ago (skip recent reversal)
            p_end   = s[s.index <= short_ago]
            if len(p_start) == 0 or len(p_end) == 0:
                continue
            ret = p_end.iloc[-1] / p_start.iloc[-1] - 1.0
            if math.isfinite(ret):
                scores[t] = ret
        return _zscore(pd.Series(scores))

    def score_low_vol(
        self,
        tickers: List[str],
        as_of_date: datetime,
        lookback_months: int = 12,
    ) -> pd.Series:
        """Negative annualized realized volatility (lower vol = higher score)."""
        date = pd.Timestamp(as_of_date)
        start = date - pd.DateOffset(months=lookback_months)

        scores = {}
        for t in tickers:
            s = self._price_cache.get(t)
            if s is None:
                continue
            window = s[(s.index >= start) & (s.index <= date)]
            if len(window) < 50:
                continue
            rets = window.pct_change().dropna()
            vol = rets.std() * math.sqrt(252)
            if math.isfinite(vol) and vol > 0:
                scores[t] = -vol  # negative: lower vol = better
        return _zscore(pd.Series(scores))

    def score_size(
        self,
        tickers: List[str],
        as_of_date: datetime,
    ) -> pd.Series:
        """
        Negative log market cap (small cap = higher score).
        Uses shares_outstanding from fundamentals × current price.
        Falls back to -log(price) as size proxy if no fundamental data.
        """
        date = pd.Timestamp(as_of_date)
        fund = self.get_fundamentals()
        scores = {}
        for t in tickers:
            s = self._price_cache.get(t)
            if s is None:
                continue
            avail = s[s.index <= date]
            if len(avail) == 0:
                continue
            price = avail.iloc[-1]
            mktcap = None
            if fund is not None and t in fund.index:
                mc = self._to_float(fund.loc[t, "marketCap"])
                if mc is not None and mc > 0:
                    mktcap = mc
            if mktcap is None:
                # Proxy: assume shares_outstanding via typical float
                # Just use price as rough inverse proxy (small price ≠ small cap, but partial signal)
                mktcap = price * 1e7  # placeholder
            score = -math.log(mktcap) if mktcap and mktcap > 0 else None
            if score is not None:
                scores[t] = score
        return _zscore(pd.Series(scores))

    # ── fundamental factor scoring ────────────────────────────────────────

    def get_fundamentals(self) -> Optional[pd.DataFrame]:
        """Load cached fundamentals DataFrame."""
        if self._fundamentals is not None:
            return self._fundamentals
        if os.path.exists(self.fund_cache_path):
            try:
                with open(self.fund_cache_path, "rb") as f:
                    self._fundamentals = pickle.load(f)
                return self._fundamentals
            except Exception:
                pass
        return None

    def get_historical_fundamentals(self) -> Optional[dict]:
        """Load point-in-time historical fundamentals dict.

        Format: {ticker: DataFrame(index=period_end_dates, cols=['gross_margin','roe'])}
        Built by factor_fundamentals_historical_fetch.py.
        """
        if self._hist_fundamentals is not None:
            return self._hist_fundamentals
        if os.path.exists(self.hist_fund_cache_path):
            try:
                with open(self.hist_fund_cache_path, "rb") as f:
                    self._hist_fundamentals = pickle.load(f)
                return self._hist_fundamentals
            except Exception:
                pass
        return None

    @staticmethod
    def _to_float(v) -> Optional[float]:
        """Safely coerce a fundamentals value to float, return None on failure."""
        if v is None:
            return None
        try:
            f = float(v)
            return f if math.isfinite(f) else None
        except (TypeError, ValueError):
            return None

    def score_value(
        self,
        tickers: List[str],
        as_of_date: datetime,
        min_market_cap: float = 0.0,
    ) -> pd.Series:
        """
        Earnings yield (1/PE) + book yield (1/PB) composite.
        Higher = cheaper = more attractive.
        min_market_cap: skip tickers below this market cap (e.g. 1e9 for large-cap only).
        """
        fund = self.get_fundamentals()
        if fund is None:
            return pd.Series(dtype=float)
        scores = {}
        for t in tickers:
            if t not in fund.index:
                continue
            row = fund.loc[t]
            # Market cap filter
            if min_market_cap > 0:
                mc = self._to_float(row.get("marketCap"))
                if mc is None or mc < min_market_cap:
                    continue
            ey = None  # earnings yield
            by = None  # book yield
            pe = self._to_float(row.get("trailingPE"))
            pb = self._to_float(row.get("priceToBook"))
            if pe is not None and pe > 0:
                ey = 1.0 / pe
            if pb is not None and pb > 0:
                by = 1.0 / pb
            vals = [v for v in [ey, by] if v is not None]
            if vals:
                scores[t] = float(np.mean(vals))
        return _zscore(pd.Series(scores))

    def score_quality(
        self,
        tickers: List[str],
        as_of_date: datetime,
    ) -> pd.Series:
        """
        ROE + gross margin composite. Higher = better quality = more attractive.

        Uses point-in-time historical quarterly fundamentals when available
        (built by factor_fundamentals_historical_fetch.py) with a 60-day
        reporting lag to avoid look-ahead bias.

        Falls back to static snapshot if historical cache is not present.
        """
        hist = self.get_historical_fundamentals()
        if hist is not None:
            return self._score_quality_historical(tickers, as_of_date, hist)
        return self._score_quality_static(tickers)

    def _score_quality_historical(
        self,
        tickers: List[str],
        as_of_date: datetime,
        hist: dict,
    ) -> pd.Series:
        # Use the most recent quarter whose period end is at least 60 days
        # before as_of_date (conservative reporting lag).
        cutoff = pd.Timestamp(as_of_date) - pd.Timedelta(days=60)
        scores = {}
        for t in tickers:
            df = hist.get(t)
            if df is None or df.empty:
                continue
            available = df[df.index <= cutoff]
            if available.empty:
                continue
            row = available.iloc[-1]
            vals = []
            gm  = self._to_float(row.get("gross_margin"))
            roe = self._to_float(row.get("roe"))
            if gm is not None and math.isfinite(gm) and abs(gm) < 2.0:
                vals.append(gm)
            if roe is not None and math.isfinite(roe) and abs(roe) < 5.0:
                vals.append(roe)
            if vals:
                scores[t] = float(np.mean(vals))
        return _zscore(pd.Series(scores))

    def _score_quality_static(self, tickers: List[str]) -> pd.Series:
        """Static snapshot fallback — has look-ahead bias for historical windows."""
        fund = self.get_fundamentals()
        if fund is None:
            return pd.Series(dtype=float)
        scores = {}
        for t in tickers:
            if t not in fund.index:
                continue
            row = fund.loc[t]
            vals = []
            roe = self._to_float(row.get("returnOnEquity"))
            gm  = self._to_float(row.get("grossMargins"))
            if roe is not None:
                vals.append(roe)
            if gm is not None:
                vals.append(gm)
            if vals:
                scores[t] = float(np.mean(vals))
        return _zscore(pd.Series(scores))

    def score_investment(
        self,
        tickers: List[str],
        as_of_date: datetime,
    ) -> pd.Series:
        """
        Negative asset growth (CMA-style: conservative investment = higher score).
        Low asset growth → companies not over-investing → outperform.
        """
        fund = self.get_fundamentals()
        if fund is None:
            return pd.Series(dtype=float)
        scores = {}
        for t in tickers:
            if t not in fund.index:
                continue
            row = fund.loc[t]
            ag = self._to_float(row.get("assetGrowth"))
            if ag is not None:
                scores[t] = -ag  # negative: lower growth = better
        return _zscore(pd.Series(scores))

    # ── composite scoring ─────────────────────────────────────────────────

    def score_multi_factor(
        self,
        factor_scores: List[pd.Series],
        weights: Optional[List[float]] = None,
    ) -> pd.Series:
        """
        Equal-weight (or custom-weight) z-score composite.
        Only combines tickers present in ALL factor scores.
        """
        if not factor_scores:
            return pd.Series(dtype=float)

        # Filter to non-empty series
        valid = [s for s in factor_scores if len(s) > 0]
        if not valid:
            return pd.Series(dtype=float)

        w = weights if weights else [1.0 / len(valid)] * len(valid)
        # Common universe
        common = valid[0].index
        for s in valid[1:]:
            common = common.intersection(s.index)

        if len(common) == 0:
            # Fall back to union with forward-fill
            all_idx = valid[0].index
            for s in valid[1:]:
                all_idx = all_idx.union(s.index)
            common = all_idx

        result = pd.Series(0.0, index=common)
        total_w = 0.0
        for s, wi in zip(valid, w):
            aligned = s.reindex(common)
            filled = aligned.fillna(0.0)
            result += wi * filled
            total_w += wi
        if total_w > 0:
            result /= total_w
        return _zscore(result)

    # ── selection ────────────────────────────────────────────────────────

    @staticmethod
    def select_top_n(scores: pd.Series, n: int = 20) -> Dict[str, float]:
        """Return top-N tickers with equal weights."""
        top = scores.nlargest(n).index.tolist()
        w = 1.0 / len(top) if top else 1.0
        return {t: w for t in top}
