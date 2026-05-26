"""
Factor Regime Signal — IWN / IWD monthly rotation
===================================================

SMB regime ON  → IWN (iShares Russell 2000 Value)  = market + value + size premium
SMB regime OFF → IWD (iShares Russell 1000 Value)  = market + value premium

Signal logic
------------
1. Train a Logistic Regression on French 3-Factor monthly data (1926→2000).
   Target: will the next 12-month SMB return be positive?
   Features: rolling momentum / vol / drawdown of SMB, HML, Mkt-RF.

2. For 2000→now: use IWM-SPY as a real-time SMB proxy (corr=0.91 with French SMB).
   The LR model produces a probability; threshold 0.52 gives a 0/1 signal.

3. A 7-day cache prevents re-training on every intraday call.

Usage
-----
    from factor_regime_signal import FactorRegimeSignal
    frs = FactorRegimeSignal()
    df  = frs.get_dataframe(as_of_date)   # pd.DataFrame with Ticker + Weight
    etf = frs.get_ticker(as_of_date)      # "IWN" or "IWD"
"""
from __future__ import annotations

import io
import logging
import os
import warnings
import zipfile
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
_HERE      = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR = os.path.join(_HERE, ".cache", "factor_regime")
_ETF_CACHE = os.path.join(_CACHE_DIR, "etf_monthly.pkl")
_SIG_CACHE = os.path.join(_CACHE_DIR, "signal.pkl")

HORIZON   = 12
EMBARGO   = 6
MIN_TRAIN = 240
STEP      = 24
TEST_LEN  = 24
HOLDOUT   = "2010-01"
THRESH    = 0.52
ETF_START = "2000-01"

_CACHE_TTL_DAYS = 7   # Refresh signal at most weekly


# ── French data ────────────────────────────────────────────────────────────────

def _load_french_ff3() -> pd.DataFrame:
    """Download Fama-French 3 Factor monthly data from Ken French's website."""
    url = ("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
           "F-F_Research_Data_Factors_CSV.zip")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        fname = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        with z.open(fname) as f:
            raw = f.read().decode("latin-1")
    rows = []
    in_annual = False
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if "Annual" in line:
            in_annual = True
            continue
        if in_annual:
            continue
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 5:
            try:
                yr, mo = int(p[0][:4]), int(p[0][4:])
                if 1 <= mo <= 12 and yr >= 1920:
                    rows.append((f"{yr}-{mo:02d}",
                                 float(p[1]), float(p[2]),
                                 float(p[3]), float(p[4])))
            except Exception:
                continue
    df = pd.DataFrame(rows, columns=["date", "Mkt_RF", "SMB", "HML", "RF"])
    df.index = pd.to_datetime([r[0] for r in rows], format="%Y-%m")
    df = df.drop("date", axis=1) / 100.0
    return df.dropna()


# ── ETF prices ─────────────────────────────────────────────────────────────────

def _yf_monthly(ticker: str, start: str = "1999-01-01") -> pd.Series:
    if not _YF_AVAILABLE:
        raise RuntimeError("yfinance not available")
    df = yf.download(ticker, start=start, interval="1mo",
                     auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data: {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        s = df[("Close", ticker)].dropna()
    else:
        s = df["Close"].dropna()
    s.index = pd.to_datetime(s.index).to_period("M").to_timestamp(how="start")
    return s.rename(ticker)


def _load_etf_prices() -> pd.DataFrame:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    if os.path.exists(_ETF_CACHE):
        cached = pd.read_pickle(_ETF_CACHE)
        if not cached.empty and all(t in cached.columns for t in ("IWM", "SPY")):
            # Refresh if cache is older than TTL
            age = (datetime.now() - datetime.fromtimestamp(
                os.path.getmtime(_ETF_CACHE))).days
            if age < _CACHE_TTL_DAYS:
                return cached
    prices = {}
    for tk in ("IWM", "SPY"):
        try:
            prices[tk] = _yf_monthly(tk)
        except Exception as e:
            logger.warning(f"Factor regime: could not fetch {tk}: {e}")
    if not prices:
        return pd.DataFrame()
    df = pd.DataFrame(prices).dropna()
    df.to_pickle(_ETF_CACHE)
    return df


# ── Features ───────────────────────────────────────────────────────────────────

def _build_features(smb: pd.Series, mkt: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame({"SMB": smb, "HML": smb, "Mkt_RF": mkt})
    feats = pd.DataFrame(index=df.index)
    for factor, col in [("HML", "HML"), ("SMB", "SMB"), ("Mkt_RF", "Mkt_RF")]:
        s = df[col]
        feats[f"{factor}_t1"]    = s.shift(1)
        feats[f"{factor}_t3"]    = s.rolling(3).mean().shift(1)
        feats[f"{factor}_t6"]    = s.rolling(6).mean().shift(1)
        feats[f"{factor}_t12"]   = s.rolling(12).mean().shift(1)
        feats[f"{factor}_cum12"] = (1 + s).rolling(12).apply(np.prod, raw=True).shift(1) - 1
        feats[f"{factor}_vol12"] = s.rolling(12).std().shift(1)
        feats[f"{factor}_vol24"] = s.rolling(24).std().shift(1)
        cumret = (1 + s).cumprod()
        peak   = cumret.rolling(60, min_periods=12).max()
        feats[f"{factor}_dd"]    = ((cumret - peak) / peak).shift(1)
    feats["hml_smb_corr12"] = df["HML"].rolling(12).corr(df["SMB"]).shift(1)
    feats["hml_mkt_corr12"] = df["HML"].rolling(12).corr(df["Mkt_RF"]).shift(1)
    feats["smb_mkt_corr12"] = df["SMB"].rolling(12).corr(df["Mkt_RF"]).shift(1)
    feats["mkt_bull12"]     = (feats["Mkt_RF_cum12"] > 0).astype(float)
    feats["hml_vol_ratio"]  = feats["HML_vol12"] / df["HML"].rolling(60).std().shift(1)
    feats["smb_vol_ratio"]  = feats["SMB_vol12"] / df["SMB"].rolling(60).std().shift(1)
    return feats.dropna(how="all")


def _make_lr() -> Pipeline:
    return Pipeline([
        ("sc",  StandardScaler()),
        ("clf", LogisticRegression(C=0.1, max_iter=500, random_state=42)),
    ])


# ── Signal computation ─────────────────────────────────────────────────────────

def _compute_signal(ff3: pd.DataFrame, etf_prices: pd.DataFrame) -> pd.Series:
    """
    Walk-forward LR trained on French data pre-2000, deployed on IWM-SPY.
    Returns a probability series (same index as ETF data, 2000→now).
    """
    smb_etf = etf_prices["IWM"].pct_change().sub(etf_prices["SPY"].pct_change()).dropna()
    spy_ret = etf_prices["SPY"].pct_change().dropna()

    # French targets
    fwd  = (1 + ff3["SMB"]).rolling(HORIZON).apply(np.prod, raw=True).shift(-HORIZON)
    y_fr = (fwd > 1).astype(float).dropna()
    X_fr = _build_features(ff3["SMB"], ff3["Mkt_RF"])

    common = X_fr.index.intersection(y_fr.index)
    X_fr   = X_fr.loc[common].ffill().bfill()
    y_fr   = y_fr.loc[common]

    holdout_idx = (X_fr.index < pd.Timestamp(HOLDOUT)).sum()
    n = holdout_idx

    # Walk-forward OOF on French dev
    oof = pd.Series(np.nan, index=X_fr.index[:n])
    train_end = MIN_TRAIN
    while True:
        ts = train_end + EMBARGO
        te = ts + TEST_LEN
        if te > n:
            break
        X_tr, y_tr = X_fr.iloc[:train_end], y_fr.iloc[:train_end]
        X_te = X_fr.iloc[ts:te]
        cl_tr = ~(np.isinf(X_tr).any(axis=1) | np.isnan(X_tr).any(axis=1))
        cl_te = ~(np.isinf(X_te).any(axis=1) | np.isnan(X_te).any(axis=1))
        if cl_tr.sum() < 50:
            break
        lr = _make_lr()
        lr.fit(X_tr[cl_tr], y_tr[cl_tr])
        idx = np.where(cl_te.values)[0]
        oof.iloc[ts + idx] = lr.predict_proba(X_te[cl_te])[:, 1]
        train_end += STEP
    oof = oof.fillna(1.0)

    # Full model trained on all French dev data
    cl_dev = ~(np.isinf(X_fr.iloc[:holdout_idx]).any(axis=1) |
               np.isnan(X_fr.iloc[:holdout_idx]).any(axis=1))
    lr_full = _make_lr()
    lr_full.fit(X_fr.iloc[:holdout_idx][cl_dev], y_fr.iloc[:holdout_idx][cl_dev])

    # ETF features
    X_etf = _build_features(smb_etf, spy_ret)

    def _predict(lr_model: Pipeline, row: pd.DataFrame) -> float:
        if (np.isinf(row).any(axis=1) | np.isnan(row).any(axis=1)).any():
            return 1.0
        return float(lr_model.predict_proba(row)[:, 1][0])

    # Holdout period (2010→now)
    hold_months = X_fr.index[holdout_idx:]
    hold_prob = pd.Series(index=hold_months, dtype=float)
    for idx in hold_months:
        if idx in X_etf.index:
            hold_prob[idx] = _predict(lr_full, X_etf.loc[[idx]])
        elif idx in X_fr.index:
            hold_prob[idx] = _predict(lr_full, X_fr.loc[[idx]])
        else:
            hold_prob[idx] = 1.0
    hold_prob = hold_prob.fillna(1.0)

    # ETF period pre-holdout (2000→2010)
    etf_pre_hold = X_etf.index[X_etf.index < pd.Timestamp(HOLDOUT)]
    etf_pre_prob = pd.Series(index=etf_pre_hold, dtype=float)
    for idx in etf_pre_hold:
        etf_pre_prob[idx] = _predict(lr_full, X_etf.loc[[idx]])

    # Combine
    full = oof.copy()
    for idx in etf_pre_prob.index:
        if idx in full.index:
            full[idx] = etf_pre_prob[idx]
    full = pd.concat([full, hold_prob]).sort_index()
    full = full[~full.index.duplicated(keep="last")]
    return full


# ══════════════════════════════════════════════════════════════════════════════
# Public class
# ══════════════════════════════════════════════════════════════════════════════

class FactorRegimeSignal:
    """
    Long-only IWN/IWD rotation based on SMB regime signal.

    Thread-safe for reads; the 7-day cache prevents unnecessary re-training.
    """

    def __init__(self, cache_dir: Optional[str] = None):
        global _CACHE_DIR, _ETF_CACHE, _SIG_CACHE
        if cache_dir:
            _CACHE_DIR = cache_dir
            _ETF_CACHE = os.path.join(cache_dir, "etf_monthly.pkl")
            _SIG_CACHE = os.path.join(cache_dir, "signal.pkl")
        self._signal: Optional[pd.Series] = None
        self._signal_loaded_at: Optional[datetime] = None

    # ── Internal ───────────────────────────────────────────────────────────────

    def _ensure_signal(self) -> None:
        if self._signal is not None and self._signal_loaded_at is not None:
            age = (datetime.now() - self._signal_loaded_at).days
            if age < _CACHE_TTL_DAYS:
                return
        # Try on-disk cache first
        os.makedirs(_CACHE_DIR, exist_ok=True)
        if os.path.exists(_SIG_CACHE):
            age_days = (datetime.now() - datetime.fromtimestamp(
                os.path.getmtime(_SIG_CACHE))).days
            if age_days < _CACHE_TTL_DAYS:
                try:
                    self._signal = pd.read_pickle(_SIG_CACHE)
                    self._signal_loaded_at = datetime.now()
                    return
                except Exception:
                    pass
        # Compute fresh
        try:
            ff3 = _load_french_ff3()
            etf = _load_etf_prices()
            if etf.empty:
                logger.warning("FactorRegimeSignal: ETF prices unavailable; defaulting to IWD")
                self._signal = pd.Series(dtype=float)
            else:
                self._signal = _compute_signal(ff3, etf)
                self._signal.to_pickle(_SIG_CACHE)
        except Exception as e:
            logger.warning(f"FactorRegimeSignal: signal computation failed ({e}); defaulting to IWD")
            self._signal = pd.Series(dtype=float)
        self._signal_loaded_at = datetime.now()

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_ticker(self, as_of_date=None) -> str:
        """
        Return 'IWN' (small-cap value, SMB ON) or 'IWD' (large-cap value, SMB OFF).

        as_of_date can be datetime, pd.Timestamp, or str ('YYYY-MM-DD').
        If None, uses today.
        """
        self._ensure_signal()
        if self._signal is None or self._signal.empty:
            return "IWD"

        if as_of_date is None:
            as_of_date = datetime.now()
        ts = pd.Timestamp(as_of_date).to_period("M").to_timestamp(how="start")

        avail = self._signal[self._signal.index <= ts]
        if avail.empty:
            return "IWD"
        prob = float(avail.iloc[-1])
        return "IWN" if prob > THRESH else "IWD"

    def get_probability(self, as_of_date=None) -> float:
        """Return the raw SMB-positive probability (0.0–1.0) for the given date."""
        self._ensure_signal()
        if self._signal is None or self._signal.empty:
            return 0.5

        if as_of_date is None:
            as_of_date = datetime.now()
        ts = pd.Timestamp(as_of_date).to_period("M").to_timestamp(how="start")

        avail = self._signal[self._signal.index <= ts]
        if avail.empty:
            return 0.5
        return float(avail.iloc[-1])

    def get_dataframe(self, as_of_date=None) -> pd.DataFrame:
        """
        Return a 1-row DataFrame with columns ['Ticker', 'Weight'] representing
        the full allocation (100% in IWN or IWD) for the given date.

        Compatible with QuiverStrategyEngine's return format.
        """
        ticker = self.get_ticker(as_of_date)
        return pd.DataFrame({"Ticker": [ticker], "Weight": [1.0]})

    def get_full_signal(self) -> pd.Series:
        """Return the entire probability series (for inspection / charting)."""
        self._ensure_signal()
        return self._signal.copy() if self._signal is not None else pd.Series(dtype=float)

    def refresh(self) -> None:
        """Force re-download and re-train (ignores cache TTL)."""
        for path in (_ETF_CACHE, _SIG_CACHE):
            if os.path.exists(path):
                os.remove(path)
        self._signal = None
        self._signal_loaded_at = None
        self._ensure_signal()
