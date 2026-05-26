"""
Track 2 — Factor Regime: Live Signal via ETF Proxies
=====================================================

Problem: Ken French data has ~2 month lag → can't trade live.

Solution (Hybrid):
  1. Train LR model on French monthly data 1926→ETF-start (pre-2000 dev set).
  2. Build identical feature vector using ETF monthly returns as factor proxies.
  3. Evaluate OOS performance 2000-2026 using ETF features + French-trained model.
  4. Report feature correlation (French vs ETF) and OOS AUC.
  5. Serialize production model + feature transform for live ib_bot inference.

ETF proxies:
  SMB_proxy = IWM - SPY  (Russell 2000 minus S&P 500)
  HML_proxy = IWD - IWF  (iShares Value minus Growth)

Run:
  python3 research/factor_regime_live.py
"""
from __future__ import annotations

import io, json, math, os, pickle, sys, warnings, zipfile
from typing import Any

import numpy as np
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, accuracy_score, brier_score_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb

warnings.filterwarnings("ignore")

# ── paths ─────────────────────────────────────────────────────────────────────
OUT_DIR    = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(OUT_DIR, ".french_cache")
ETF_CACHE  = os.path.join(CACHE_DIR, "etf_monthly.pkl")
OUT_JSON   = os.path.join(OUT_DIR, "factor_regime_live_results.json")
OUT_HTML   = os.path.join(OUT_DIR, "factor_regime_live.html")
OUT_MODEL  = os.path.join(OUT_DIR, "factor_regime_model.pkl")

# ── hyperparams ───────────────────────────────────────────────────────────────
HORIZON   = 12
EMBARGO   = 6
MIN_TRAIN = 240   # ~20 years for French training
STEP      = 24
TEST_LEN  = 24
N_SEEDS   = 5
ETF_START  = "2000-07"   # IWD inception 2000-05; IWM 2000-05; use 2000-07 for safe 3m runway
EDGAR_START = "2009-04"  # ib_bot price cache starts 2009; EDGAR HML available from here

LGBM_BASE = dict(
    n_estimators=200, max_depth=3, learning_rate=0.03,
    subsample=0.8, colsample_bytree=0.7,
    min_child_samples=15, reg_lambda=2.0, verbose=-1,
)

FRENCH_URLS = {
    "3factor": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip",
}


# ══════════════════════════════════════════════════════════════════════════════
# 1. DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_zip(url: str, cache_name: str) -> str:
    path = os.path.join(CACHE_DIR, cache_name)
    if os.path.exists(path):
        return path
    print(f"  Downloading {cache_name}...", end="", flush=True)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    csv_name = [n for n in z.namelist() if n.endswith(".CSV") or n.endswith(".csv")][0]
    content = z.read(csv_name).decode("utf-8", errors="replace")
    with open(path, "w") as f:
        f.write(content)
    print(f" {len(content)//1024}KB")
    return path


def load_french_3factor() -> pd.DataFrame:
    path = _fetch_zip(FRENCH_URLS["3factor"], "3factor.csv")
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4 and len(parts[0]) == 6 and parts[0].isdigit():
                    year, month = int(parts[0][:4]), int(parts[0][4:])
                    if 1 <= month <= 12 and year >= 1920:
                        rows.append((f"{year}-{month:02d}",
                                     float(parts[1]), float(parts[2]),
                                     float(parts[3]), float(parts[4])))
            except (ValueError, IndexError):
                continue
    df = pd.DataFrame(rows, columns=["date", "Mkt_RF", "SMB", "HML", "RF"])
    df = df.set_index("date")
    df.index = pd.to_datetime(df.index, format="%Y-%m")
    df = df / 100.0
    return df.dropna()


def _yf_monthly(ticker: str, start: str = "1999-01-01") -> pd.Series:
    """Download monthly adj-close from Yahoo Finance via yfinance library."""
    import yfinance as yf
    df = yf.download(ticker, start=start, interval="1mo", auto_adjust=True,
                     progress=False)
    if df.empty:
        raise ValueError(f"No data returned for {ticker}")
    # yfinance returns MultiIndex columns (Price, Ticker); extract Close for this ticker
    if isinstance(df.columns, pd.MultiIndex):
        s = df[("Close", ticker)].dropna()
    else:
        close_col = "Close" if "Close" in df.columns else df.columns[0]
        s = df[close_col].dropna()
    # Shift index to month-start for alignment with French data
    s.index = pd.to_datetime(s.index).to_period("M").to_timestamp(how="start")
    return s.rename(ticker)


def load_etf_monthly(force: bool = False) -> pd.DataFrame:
    """Load IWM, SPY, IWD, IWF monthly prices, cache result."""
    if os.path.exists(ETF_CACHE) and not force:
        df = pd.read_pickle(ETF_CACHE)
        if not df.empty and len(df.columns) >= 4:
            return df

    tickers = ["IWM", "SPY", "IWD", "IWF"]
    prices = {}
    for tk in tickers:
        print(f"  Fetching {tk}...", end="", flush=True)
        try:
            s = _yf_monthly(tk)
            prices[tk] = s
            print(f" {len(s)} months ({s.index[0].strftime('%Y-%m')}→{s.index[-1].strftime('%Y-%m')})")
        except Exception as e:
            print(f" ERROR: {e}")

    if len(prices) < 4:
        raise RuntimeError(f"Only fetched {len(prices)}/4 ETF tickers: {list(prices.keys())}")

    df = pd.DataFrame(prices).dropna()
    df.to_pickle(ETF_CACHE)
    return df


def etf_monthly_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Compute monthly returns and factor proxies from ETF prices."""
    ret = prices.pct_change().dropna()
    ret["SMB_etf"] = ret["IWM"] - ret["SPY"]   # small minus large
    ret["HML_etf"] = ret["IWD"] - ret["IWF"]   # value minus growth
    ret["Mkt_etf"] = ret["SPY"]                 # market proxy
    return ret


# ══════════════════════════════════════════════════════════════════════════════
# 2. FEATURE ENGINEERING (unified — works for both French and ETF columns)
# ══════════════════════════════════════════════════════════════════════════════

def build_features_from_cols(df: pd.DataFrame,
                              smb_col: str, hml_col: str, mkt_col: str,
                              label: str = "") -> pd.DataFrame:
    """
    Build the 28-feature matrix from arbitrary SMB/HML/Mkt return columns.
    All features are lag-1 (no look-ahead).
    """
    feats = pd.DataFrame(index=df.index)

    for factor, col in [("HML", hml_col), ("SMB", smb_col), ("Mkt_RF", mkt_col)]:
        s = df[col]
        feats[f"{factor}_t1"]   = s.shift(1)
        feats[f"{factor}_t3"]   = s.rolling(3).mean().shift(1)
        feats[f"{factor}_t6"]   = s.rolling(6).mean().shift(1)
        feats[f"{factor}_t12"]  = s.rolling(12).mean().shift(1)
        feats[f"{factor}_cum12"]= (1 + s).rolling(12).apply(np.prod, raw=True).shift(1) - 1
        feats[f"{factor}_vol12"]= s.rolling(12).std().shift(1)
        feats[f"{factor}_vol24"]= s.rolling(24).std().shift(1)
        cumret = (1 + s).cumprod()
        peak   = cumret.rolling(60, min_periods=12).max()
        feats[f"{factor}_dd"]   = ((cumret - peak) / peak).shift(1)

    feats["hml_smb_corr12"] = df[hml_col].rolling(12).corr(df[smb_col]).shift(1)
    feats["hml_mkt_corr12"] = df[hml_col].rolling(12).corr(df[mkt_col]).shift(1)
    feats["smb_mkt_corr12"] = df[smb_col].rolling(12).corr(df[mkt_col]).shift(1)
    feats["mkt_bull12"]     = (feats["Mkt_RF_cum12"] > 0).astype(float)
    feats["hml_vol_ratio"]  = feats["HML_vol12"] / df[hml_col].rolling(60).std().shift(1)
    feats["smb_vol_ratio"]  = feats["SMB_vol12"] / df[smb_col].rolling(60).std().shift(1)

    return feats.dropna(how="all")


def build_targets(ff3: pd.DataFrame) -> pd.DataFrame:
    tgts = pd.DataFrame(index=ff3.index)
    for factor, col in [("HML", "hml_bull_12m"), ("SMB", "smb_bull_12m")]:
        fwd_cum = (1 + ff3[factor]).rolling(HORIZON).apply(np.prod, raw=True).shift(-HORIZON)
        tgts[col] = (fwd_cum > 1).astype(float)
    return tgts


# ══════════════════════════════════════════════════════════════════════════════
# 3. MODELS
# ══════════════════════════════════════════════════════════════════════════════

def make_lr() -> Pipeline:
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(C=0.1, max_iter=500, random_state=42)),
    ])


def make_lgbm(seed: int = 0) -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(**{**LGBM_BASE, "random_state": seed})


def walk_forward_folds(n: int, min_train: int, step: int, test_len: int,
                        embargo: int, holdout_start_idx: int):
    folds = []
    train_end = min_train
    while True:
        test_start = train_end + embargo
        test_end   = test_start + test_len
        if test_end > holdout_start_idx:
            break
        folds.append((np.arange(0, train_end), np.arange(test_start, test_end)))
        train_end += step
    return folds


# ══════════════════════════════════════════════════════════════════════════════
# 4. HYBRID EVALUATION
# ══════════════════════════════════════════════════════════════════════════════

def run_hybrid_eval(target_name: str,
                    X_french: pd.DataFrame, y: pd.Series,
                    X_etf: pd.DataFrame,
                    etf_start_idx: int,
                    dev_cutoff: str | None = None) -> dict:
    """
    Phase A — Walk-forward CV on French data dev set (pre-cutoff era).
              Trains and tests only on French-derived features.

    Phase B — OOS: model trained on French dev data applied to ETF features.
              Tests generalization to different feature source.

    Phase C — Feature correlation: French vs ETF in overlap period.
    """
    results = {"target": target_name}

    # Align y with X_french
    common_idx = X_french.index.intersection(y.index)
    X_f = X_french.loc[common_idx].ffill().bfill()
    y_f = y.loc[common_idx]

    # Dev = all French rows before the cutoff date
    cutoff = pd.Timestamp(dev_cutoff if dev_cutoff else ETF_START)
    dev_mask = X_f.index < cutoff
    X_dev = X_f[dev_mask]
    y_dev = y_f[dev_mask]
    n_dev = len(X_dev)

    results["n_dev_french"] = n_dev
    results["dev_period"]   = f"{X_dev.index[0].strftime('%Y-%m')}→{X_dev.index[-1].strftime('%Y-%m')}"
    results["base_rate_dev"] = float(y_dev.mean())

    print(f"\n  ── {target_name} ──────────────────────────────")
    print(f"    Dev (French, pre-{cutoff.strftime('%Y-%m')}): {n_dev} obs | base rate: {y_dev.mean():.1%}")

    # ── Phase A: WF CV on French dev data ────────────────────────────────────
    folds = walk_forward_folds(n_dev, MIN_TRAIN, STEP, TEST_LEN, EMBARGO, n_dev)
    print(f"    Phase A: {len(folds)} WF folds on French dev data")

    lr_aucs, lgbm_aucs = [], []
    for train_idx, test_idx in folds:
        if len(np.unique(y_dev.iloc[test_idx])) < 2:
            continue
        X_tr, y_tr = X_dev.iloc[train_idx], y_dev.iloc[train_idx]
        X_te, y_te = X_dev.iloc[test_idx],  y_dev.iloc[test_idx]
        clean = ~(np.isinf(X_tr).any(axis=1) | np.isnan(X_tr).any(axis=1))
        X_tr, y_tr = X_tr[clean], y_tr[clean]
        clean_te = ~(np.isinf(X_te).any(axis=1) | np.isnan(X_te).any(axis=1))
        X_te, y_te = X_te[clean_te], y_te[clean_te]
        if len(X_tr) < 50 or len(X_te) < 5:
            continue

        lr = make_lr()
        lr.fit(X_tr, y_tr)
        lr_p = lr.predict_proba(X_te)[:, 1]
        lr_aucs.append(roc_auc_score(y_te, lr_p))

        lgb_probs = []
        for seed in range(N_SEEDS):
            m = make_lgbm(seed)
            m.fit(X_tr, y_tr)
            lgb_probs.append(m.predict_proba(X_te)[:, 1])
        lgbm_aucs.append(roc_auc_score(y_te, np.mean(lgb_probs, axis=0)))

    phaseA = {
        "lr_auc_mean":   float(np.mean(lr_aucs))   if lr_aucs   else np.nan,
        "lr_auc_std":    float(np.std(lr_aucs))     if lr_aucs   else np.nan,
        "lgbm_auc_mean": float(np.mean(lgbm_aucs)) if lgbm_aucs else np.nan,
        "lgbm_auc_std":  float(np.std(lgbm_aucs))  if lgbm_aucs else np.nan,
        "n_folds": len(lr_aucs),
    }
    results["phaseA"] = phaseA
    print(f"    Phase A WF: LR={phaseA['lr_auc_mean']:.3f}±{phaseA['lr_auc_std']:.3f}  "
          f"LGBM={phaseA['lgbm_auc_mean']:.3f}±{phaseA['lgbm_auc_std']:.3f}")

    # ── Train final model on FULL French dev data ─────────────────────────────
    clean_dev = ~(np.isinf(X_dev).any(axis=1) | np.isnan(X_dev).any(axis=1))
    X_dev_c, y_dev_c = X_dev[clean_dev], y_dev[clean_dev]

    lr_full = make_lr()
    lr_full.fit(X_dev_c, y_dev_c)

    lgbm_full_models = []
    for seed in range(N_SEEDS):
        m = make_lgbm(seed)
        m.fit(X_dev_c, y_dev_c)
        lgbm_full_models.append(m)

    # ── Phase B: OOS on ETF features ─────────────────────────────────────────
    # Align ETF features with French targets
    common_etf = X_etf.index.intersection(y.index)
    X_etf_aligned = X_etf.loc[common_etf].ffill().bfill()
    y_etf_aligned  = y.loc[common_etf].dropna()
    common2 = X_etf_aligned.index.intersection(y_etf_aligned.index)
    X_oos = X_etf_aligned.loc[common2]
    y_oos = y_etf_aligned.loc[common2]

    # Drop last HORIZON months (no valid target)
    y_oos = y_oos.dropna()
    X_oos = X_oos.reindex(y_oos.index)

    n_oos = len(X_oos)
    results["n_oos_etf"] = n_oos
    results["oos_period"] = (f"{X_oos.index[0].strftime('%Y-%m')}→{X_oos.index[-1].strftime('%Y-%m')}"
                             if n_oos > 0 else "N/A")
    results["base_rate_oos"] = float(y_oos.mean()) if n_oos > 0 else np.nan

    print(f"    Phase B OOS: {n_oos} ETF months | base rate: {y_oos.mean():.1%}")

    if n_oos >= 24:
        clean_oos = ~(np.isinf(X_oos).any(axis=1) | np.isnan(X_oos).any(axis=1))
        X_oos_c, y_oos_c = X_oos[clean_oos], y_oos[clean_oos]

        lr_oos_p  = lr_full.predict_proba(X_oos_c)[:, 1]
        lgbm_oos_probs = [m.predict_proba(X_oos_c)[:, 1] for m in lgbm_full_models]
        lgbm_oos_p = np.mean(lgbm_oos_probs, axis=0)

        phaseB = {
            "lr_auc":   float(roc_auc_score(y_oos_c, lr_oos_p)),
            "lgbm_auc": float(roc_auc_score(y_oos_c, lgbm_oos_p)),
            "n_obs":    int(len(y_oos_c)),
        }
        results["phaseB"] = phaseB
        print(f"    Phase B OOS: LR={phaseB['lr_auc']:.3f}  LGBM={phaseB['lgbm_auc']:.3f}")

        # Store OOS probabilities for equity curve
        results["_oos_lr_probs"]   = lr_oos_p.tolist()
        results["_oos_lgbm_probs"] = lgbm_oos_p.tolist()
        results["_oos_dates"]      = [d.strftime("%Y-%m") for d in X_oos_c.index]
        results["_oos_y"]          = y_oos_c.tolist()
    else:
        print(f"    Phase B: insufficient OOS data ({n_oos} months)")
        results["phaseB"] = {"lr_auc": np.nan, "lgbm_auc": np.nan, "n_obs": n_oos}

    # ── Phase C: Feature correlation in overlap period ────────────────────────
    overlap_idx = X_f.index.intersection(X_etf.index)
    if len(overlap_idx) > 24:
        corrs = {}
        feature_cols = X_f.columns.tolist()
        X_fr_ov = X_f.loc[overlap_idx]
        X_et_ov = X_etf.loc[overlap_idx].reindex(columns=feature_cols)
        for col in feature_cols:
            if col in X_et_ov.columns:
                valid = X_fr_ov[col].dropna().index.intersection(X_et_ov[col].dropna().index)
                if len(valid) > 10:
                    corrs[col] = float(X_fr_ov[col].loc[valid].corr(X_et_ov[col].loc[valid]))
        results["feature_corr"] = corrs
        avg_corr = float(np.nanmean(list(corrs.values())))
        results["avg_feature_corr"] = avg_corr
        print(f"    Phase C: avg feature corr French↔ETF = {avg_corr:.3f} ({len(overlap_idx)} overlap months)")

    # ── Save model for live inference ─────────────────────────────────────────
    results["_model_lr"]         = lr_full
    results["_model_lgbm_seeds"] = lgbm_full_models
    results["_feature_names"]    = X_dev_c.columns.tolist()

    return results


# ══════════════════════════════════════════════════════════════════════════════
# 5. EQUITY CURVE (OOS, ETF features only)
# ══════════════════════════════════════════════════════════════════════════════

def build_oos_equity(target_name: str, factor_col: str,
                     ff3: pd.DataFrame, res: dict) -> pd.DataFrame:
    """Build always-hold vs LR-timed equity using ETF-era factor returns."""
    if "_oos_dates" not in res:
        return pd.DataFrame()

    dates  = pd.to_datetime(res["_oos_dates"], format="%Y-%m")
    probs  = pd.Series(res["_oos_lr_probs"], index=dates)
    factor_ret = ff3[factor_col].reindex(dates)

    # Always hold
    always_eq = (1 + factor_ret).cumprod() * 100

    # Timed: invest if prob > 0.52, else flat (cash)
    THRESH = 0.52
    signal = (probs > THRESH).astype(float)
    timed_ret = factor_ret * signal
    timed_eq  = (1 + timed_ret).cumprod() * 100

    df = pd.DataFrame({
        "always": always_eq,
        "timed":  timed_eq,
        "signal": signal,
        "prob":   probs,
    }).dropna(subset=["always", "timed"])

    always_cagr = _cagr(df["always"])
    timed_cagr  = _cagr(df["timed"])
    print(f"    {target_name} OOS equity: always={always_cagr:.1%} timed={timed_cagr:.1%}")
    return df


def _cagr(s: pd.Series) -> float:
    if len(s) < 2:
        return 0.0
    years = (s.index[-1] - s.index[0]).days / 365.25
    if years <= 0:
        return 0.0
    return float((s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1)


# ══════════════════════════════════════════════════════════════════════════════
# 6. FEATURE CORRELATION HEATMAP + REPORT
# ══════════════════════════════════════════════════════════════════════════════

def build_html_report(results_hml: dict, results_smb: dict,
                      eq_hml: pd.DataFrame, eq_smb: pd.DataFrame,
                      ff3: pd.DataFrame, etf_ret: pd.DataFrame,
                      res_hml_edgar: dict | None = None,
                      eq_hml_edgar: pd.DataFrame | None = None) -> str:

    figs = []

    # ── 0. Raw factor correlation over time ───────────────────────────────────
    ovlp = ff3.index.intersection(etf_ret.index)
    if len(ovlp) > 36:
        roll_smb = ff3["SMB"].loc[ovlp].rolling(36).corr(etf_ret["SMB_etf"].loc[ovlp])
        roll_hml = ff3["HML"].loc[ovlp].rolling(36).corr(etf_ret["HML_etf"].loc[ovlp])

        fig0 = go.Figure()
        fig0.add_trace(go.Scatter(x=ovlp, y=roll_smb, name="SMB (IWM-SPY)",
                                  line=dict(color="#00d4ff", width=2)))
        fig0.add_trace(go.Scatter(x=ovlp, y=roll_hml, name="HML (IWD-IWF)",
                                  line=dict(color="#ff9f40", width=2)))
        fig0.add_hline(y=0.5, line_dash="dot", line_color="red",
                       annotation_text="0.50 threshold")
        fig0.update_layout(
            title="36-Month Rolling Correlation: French Factor vs ETF Proxy",
            xaxis_title="Date", yaxis_title="Pearson r",
            paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
            font=dict(color="#e0e0e0"), height=350,
            legend=dict(bgcolor="rgba(0,0,0,0)"),
        )
        figs.append(("fig0", fig0, "Rolling Correlation: French ↔ ETF Proxy"))

    # ── 1. OOS equity curves ──────────────────────────────────────────────────
    equity_list = [("HML (Value)", eq_hml, "HML"), ("SMB (Size)", eq_smb, "SMB")]
    if res_hml_edgar and eq_hml_edgar is not None and not eq_hml_edgar.empty:
        equity_list.append(("HML (EDGAR proxy)", eq_hml_edgar, "HML"))
    for name, eq, factor_col in equity_list:
        if eq.empty:
            continue
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=eq.index, y=eq["always"], name="Always Hold",
                                  line=dict(color="#6c7a89", width=2, dash="dot")))
        fig.add_trace(go.Scatter(x=eq.index, y=eq["timed"], name="Regime Timed (LR)",
                                  line=dict(color="#00d4ff", width=2.5)))

        always_c = _cagr(eq["always"])
        timed_c  = _cagr(eq["timed"])
        fig.update_layout(
            title=f"{name} — OOS ETF Proxy | Always={always_c:.1%}  Timed={timed_c:.1%}",
            xaxis_title="Date", yaxis_title="Equity ($100 start)",
            paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
            font=dict(color="#e0e0e0"), height=380,
            legend=dict(bgcolor="rgba(0,0,0,0)"),
            annotations=[dict(
                x=0.01, y=0.97, xref="paper", yref="paper",
                text="Model trained on pre-ETF French data (pre-2000) | Signal: LR p>0.52",
                showarrow=False, font=dict(size=10, color="#888"), align="left"
            )]
        )
        key = name.replace(" ", "_").replace("(", "").replace(")", "")
        figs.append((key, fig, f"{name} OOS Equity Curve (ETF Proxy)"))

    # ── 2. Feature correlation bar chart ─────────────────────────────────────
    for name, res in [("HML", results_hml), ("SMB", results_smb)]:
        fc = res.get("feature_corr", {})
        if fc:
            cols = sorted(fc.keys(), key=lambda k: abs(fc[k]), reverse=True)
            vals = [fc[c] for c in cols]
            colors = ["#00d4ff" if v >= 0 else "#ff4444" for v in vals]
            fig_fc = go.Figure(go.Bar(x=cols, y=vals, marker_color=colors))
            fig_fc.update_layout(
                title=f"{name} — Feature Correlation: French vs ETF (overlap {res.get('n_oos_etf',0)} months)",
                xaxis_tickangle=-45, yaxis_title="Pearson r",
                paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
                font=dict(color="#e0e0e0"), height=400,
            )
            figs.append((f"fc_{name}", fig_fc, f"{name} Feature Correlation"))

    # ── 3. Summary table ─────────────────────────────────────────────────────
    def _fmt(v, digits=3):
        if isinstance(v, float) and math.isnan(v):
            return "—"
        if isinstance(v, float):
            return f"{v:.{digits}f}"
        return str(v)

    rows_html = ""
    all_res = [("HML (Value)", results_hml), ("SMB (Size)", results_smb)]
    if res_hml_edgar:
        all_res.append(("HML (EDGAR proxy)", res_hml_edgar))
    for name, res in all_res:
        pA = res.get("phaseA", {})
        pB = res.get("phaseB", {})
        rows_html += f"""
        <tr>
          <td>{name}</td>
          <td>{res.get('dev_period','—')}</td>
          <td>{pA.get('n_folds','—')}</td>
          <td>{_fmt(pA.get('lr_auc_mean',float('nan')))} ± {_fmt(pA.get('lr_auc_std',float('nan')))}</td>
          <td>{_fmt(pA.get('lgbm_auc_mean',float('nan')))} ± {_fmt(pA.get('lgbm_auc_std',float('nan')))}</td>
          <td>{res.get('oos_period','—')}</td>
          <td>{_fmt(pB.get('lr_auc',float('nan')))}</td>
          <td>{_fmt(pB.get('lgbm_auc',float('nan')))}</td>
          <td>{_fmt(res.get('avg_feature_corr',float('nan')))}</td>
        </tr>"""

    # Assemble HTML
    plots_html = ""
    for key, fig, title in figs:
        plots_html += f"""
        <div class="chart-block">
          <div class="chart-title">{title}</div>
          {fig.to_html(full_html=False, include_plotlyjs=False)}
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Factor Regime — Live Signal via ETF Proxies</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  html,body{{background:#0f1117!important;color:#e0e0e0;font-family:'Inter',sans-serif;margin:0;padding:0}}
  .container{{max-width:1200px;margin:0 auto;padding:24px}}
  h1{{font-size:1.6rem;color:#00d4ff;margin-bottom:4px}}
  .subtitle{{color:#888;font-size:.9rem;margin-bottom:32px}}
  .section-title{{font-size:1.1rem;color:#aaa;margin:28px 0 12px;border-bottom:1px solid #2a2d3a;padding-bottom:6px}}
  .card-row{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px}}
  .card{{background:#1a1d2e;border:1px solid #2a2d3a;border-radius:8px;padding:16px;flex:1;min-width:200px}}
  .card-label{{font-size:.75rem;color:#888;text-transform:uppercase;letter-spacing:.06em}}
  .card-value{{font-size:1.5rem;font-weight:700;color:#00d4ff;margin:4px 0}}
  .card-sub{{font-size:.8rem;color:#666}}
  .chart-block{{background:#1a1d2e;border:1px solid #2a2d3a;border-radius:8px;padding:16px;margin-bottom:16px}}
  .chart-title{{font-size:.95rem;color:#aaa;margin-bottom:10px}}
  table{{width:100%;border-collapse:collapse;font-size:.85rem}}
  th{{background:#1a1d2e;color:#888;padding:8px 10px;text-align:left;border-bottom:1px solid #2a2d3a}}
  td{{padding:8px 10px;border-bottom:1px solid #1e2130;color:#ccc}}
  tr:hover td{{background:#1a1d2e}}
  .verdict{{background:#1a1d2e;border-left:4px solid #00d4ff;padding:14px 18px;border-radius:0 8px 8px 0;margin:20px 0}}
  .tag-good{{background:#1a3a2a;color:#4ade80;padding:2px 8px;border-radius:12px;font-size:.8rem}}
  .tag-warn{{background:#3a2a1a;color:#fb923c;padding:2px 8px;border-radius:12px;font-size:.8rem}}
  .tag-bad{{background:#3a1a1a;color:#f87171;padding:2px 8px;border-radius:12px;font-size:.8rem}}
</style>
</head>
<body>
<div class="container">
  <h1>Factor Regime — Live Signal via ETF Proxies</h1>
  <div class="subtitle">
    Train: Ken French monthly data pre-2000 (French features) &nbsp;|&nbsp;
    OOS: 2000→2026 using ETF proxies (IWM−SPY for SMB, IWD−IWF for HML)
  </div>

  <div class="verdict">
    <strong>What this tests:</strong> If we train the regime model on historical French data
    and then deploy it using ETF-computed features (no French lag needed), does the model
    still work? AUC &gt; 0.55 in both Phase A and B confirms the proxy is viable for live trading.
  </div>

  <div class="section-title">Summary</div>
  <div style="overflow-x:auto">
  <table>
    <tr>
      <th>Target</th><th>Dev Period</th><th>Folds</th>
      <th>Phase A LR AUC (French WF)</th><th>Phase A LGBM AUC</th>
      <th>OOS Period</th><th>Phase B LR AUC (ETF)</th><th>Phase B LGBM</th>
      <th>Avg Feature Corr</th>
    </tr>
    {rows_html}
  </table>
  </div>

  <div class="section-title">Charts</div>
  {plots_html}

  <div class="section-title">Interpretation</div>
  <div class="verdict">
    <strong>Phase A</strong> = walk-forward CV using French data only (pre-2000, same method as main model).<br>
    <strong>Phase B</strong> = OOS using ETF proxy features into French-trained model (2000→2026).
    This is the live-trading scenario — no French data required at inference time.<br>
    <strong>Feature corr</strong> = Pearson r between French-computed and ETF-computed feature values in overlap period.
    High (&gt;0.7) = ETF proxies faithfully replicate the French-based features.
  </div>

  <p style="color:#444;font-size:.8rem;margin-top:32px">
    Generated {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} ART
  </p>
</div>
</body>
</html>"""
    return html


# ══════════════════════════════════════════════════════════════════════════════
# 7. MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("Factor Regime — Live Signal via ETF Proxies")
    print("=" * 60)

    # 1. Load data
    print("\n[1/5] Loading French 3-factor data...")
    ff3 = load_french_3factor()
    print(f"  French: {ff3.index[0].strftime('%Y-%m')} → {ff3.index[-1].strftime('%Y-%m')} ({len(ff3)} months)")

    print("\n[2/5] Loading ETF monthly data (IWM, SPY, IWD, IWF)...")
    os.makedirs(CACHE_DIR, exist_ok=True)
    etf_prices = load_etf_monthly()
    etf_ret    = etf_monthly_returns(etf_prices)
    print(f"  ETF: {etf_ret.index[0].strftime('%Y-%m')} → {etf_ret.index[-1].strftime('%Y-%m')} ({len(etf_ret)} months)")

    # 2. Build features
    print("\n[3/5] Building feature matrices...")

    # French features (all history)
    ff3_ext = ff3.copy()
    ff3_ext["RF_flat"] = ff3["RF"]   # Mkt_RF already excess return
    X_french = build_features_from_cols(ff3,
                                         smb_col="SMB", hml_col="HML", mkt_col="Mkt_RF",
                                         label="French")
    print(f"  French features: {X_french.shape} (from {X_french.index[0].strftime('%Y-%m')})")

    # ETF features
    X_etf = build_features_from_cols(etf_ret,
                                      smb_col="SMB_etf", hml_col="HML_etf", mkt_col="Mkt_etf",
                                      label="ETF")
    print(f"  ETF features: {X_etf.shape} (from {X_etf.index[0].strftime('%Y-%m')})")

    # Targets (always from French — these are the ground truth)
    y_all = build_targets(ff3)

    # French feature corr check in overlap
    overlap = X_french.index.intersection(X_etf.index)
    print(f"  Overlap period: {overlap[0].strftime('%Y-%m')} → {overlap[-1].strftime('%Y-%m')} ({len(overlap)} months)")

    # 4. Run hybrid evaluation
    print("\n[4/5] Running hybrid evaluation...")
    etf_start_idx = (X_french.index < pd.Timestamp(ETF_START)).sum()

    res_hml = run_hybrid_eval("HML", X_french, y_all["hml_bull_12m"], X_etf, etf_start_idx)
    res_smb = run_hybrid_eval("SMB", X_french, y_all["smb_bull_12m"], X_etf, etf_start_idx)

    # 4b. EDGAR HML variant — correct split: train on full French 1926→EDGAR_START,
    #     test on EDGAR features in EDGAR_START→2026.
    #     This is the real live-deploy scenario: model sees the structural break
    #     (dot-com, 2008) before going live with EDGAR features.
    edgar_pkl = os.path.join(CACHE_DIR, "hml_edgar.pkl")
    res_hml_edgar = None
    if os.path.exists(edgar_pkl):
        print("\n  ── HML (EDGAR proxy, correct split) ──────────────")
        hml_edgar = pd.read_pickle(edgar_pkl)
        # Build hybrid: SMB=IWM-SPY, HML=EDGAR, Mkt=SPY
        hybrid = etf_ret[["SMB_etf", "Mkt_etf"]].copy()
        hml_edgar_aligned = hml_edgar.reindex(hybrid.index)
        hybrid["HML_edgar"] = hml_edgar_aligned
        hybrid = hybrid.dropna()
        X_edgar = build_features_from_cols(hybrid,
                                            smb_col="SMB_etf",
                                            hml_col="HML_edgar",
                                            mkt_col="Mkt_etf",
                                            label="EDGAR")
        print(f"    EDGAR hybrid features: {X_edgar.shape}")
        # Training cutoff = EDGAR availability (2009-04), not just ETF start (2000-07)
        # Model sees 1926→2009 in training — includes dot-com crash + 2008 crisis
        edgar_start_idx = (X_french.index < pd.Timestamp(EDGAR_START)).sum()
        print(f"    French dev (pre-EDGAR): {edgar_start_idx} obs "
              f"({X_french.index[0].strftime('%Y-%m')}→{X_french.index[edgar_start_idx-1].strftime('%Y-%m')})")
        res_hml_edgar = run_hybrid_eval("HML_EDGAR", X_french, y_all["hml_bull_12m"],
                                        X_edgar, edgar_start_idx,
                                        dev_cutoff=EDGAR_START)
    else:
        print(f"\n  (EDGAR HML not yet built — run factor_hml_edgar.py to unlock)")

    # 5. OOS equity curves
    print("\n[5/5] Building OOS equity curves and report...")
    eq_hml = build_oos_equity("HML", "HML", ff3, res_hml)
    eq_smb = build_oos_equity("SMB", "SMB", ff3, res_smb)
    eq_hml_edgar = (build_oos_equity("HML_EDGAR", "HML", ff3, res_hml_edgar)
                    if res_hml_edgar else pd.DataFrame())

    # Build report
    html = build_html_report(res_hml, res_smb, eq_hml, eq_smb, ff3, etf_ret,
                             res_hml_edgar=res_hml_edgar, eq_hml_edgar=eq_hml_edgar)
    with open(OUT_HTML, "w") as f:
        f.write(html)
    print(f"  Wrote {OUT_HTML}")

    # Save JSON results (strip private keys)
    def _clean(d):
        return {k: v for k, v in d.items() if not k.startswith("_")}

    out = {
        "generated": pd.Timestamp.now().isoformat(),
        "etf_start": ETF_START,
        "HML": _clean(res_hml),
        "SMB": _clean(res_smb),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"  Wrote {OUT_JSON}")

    # Serialize production models
    model_bundle = {
        "HML": {
            "lr":          res_hml["_model_lr"],
            "lgbm_seeds":  res_hml["_model_lgbm_seeds"],
            "feature_names": res_hml["_feature_names"],
        },
        "SMB": {
            "lr":          res_smb["_model_lr"],
            "lgbm_seeds":  res_smb["_model_lgbm_seeds"],
            "feature_names": res_smb["_feature_names"],
        },
        "feature_builder": {
            "smb_col":  "SMB_etf",
            "hml_col":  "HML_etf",
            "mkt_col":  "Mkt_etf",
            "threshold": 0.52,
            "horizon":  HORIZON,
        },
        "etf_proxies": {
            "SMB": "IWM - SPY",
            "HML": "IWD - IWF",
        },
    }
    with open(OUT_MODEL, "wb") as f:
        pickle.dump(model_bundle, f)
    print(f"  Serialized model → {OUT_MODEL}")

    # Print verdict
    print("\n" + "=" * 60)
    print("VERDICT")
    print("=" * 60)
    verdict_list = [("HML (ETF proxy)", res_hml), ("SMB", res_smb)]
    if res_hml_edgar:
        verdict_list.append(("HML (EDGAR proxy)", res_hml_edgar))
    for name, res in verdict_list:
        pA = res.get("phaseA", {})
        pB = res.get("phaseB", {})
        avg_c = res.get("avg_feature_corr", float("nan"))
        print(f"\n  {name}:")
        print(f"    Phase A WF AUC (French):  LR={pA.get('lr_auc_mean',0):.3f}  LGBM={pA.get('lgbm_auc_mean',0):.3f}")
        print(f"    Phase B OOS AUC (ETF):    LR={pB.get('lr_auc',0):.3f}  LGBM={pB.get('lgbm_auc',0):.3f}")
        print(f"    Avg feature corr:         {avg_c:.3f}")
        viable = (not math.isnan(pB.get("lr_auc", float("nan")))
                  and pB.get("lr_auc", 0) > 0.52
                  and avg_c > 0.60)
        print(f"    Live proxy viable?        {'✓ YES' if viable else '⚠ BORDERLINE / NO'}")

    return res_hml, res_smb


if __name__ == "__main__":
    main()
