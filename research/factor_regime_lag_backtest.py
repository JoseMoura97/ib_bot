"""
Factor Regime — Lag Backtest
=============================

Tests what happens if we use French data with a 2-month publication lag.

At each month t: signal is computed from data available at t-lag.
Compares: no-lag vs 1-month vs 2-month vs 3-month lag.

Also tests SMB (IWM-SPY, 0-lag) side by side.

Run:
  python3 research/factor_regime_lag_backtest.py
"""
from __future__ import annotations

import io, json, os, pickle, warnings, zipfile
import numpy as np
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb

warnings.filterwarnings("ignore")

OUT_DIR   = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(OUT_DIR, ".french_cache")
ETF_CACHE = os.path.join(CACHE_DIR, "etf_monthly.pkl")
OUT_HTML  = os.path.join(OUT_DIR, "factor_regime_lag_backtest.html")
OUT_JSON  = os.path.join(OUT_DIR, "factor_regime_lag_backtest.json")

HORIZON   = 12
EMBARGO   = 6
MIN_TRAIN = 240
STEP      = 24
TEST_LEN  = 24
N_SEEDS   = 5
HOLDOUT   = "2010-01"
THRESH    = 0.52

LGBM_BASE = dict(n_estimators=200, max_depth=3, learning_rate=0.03,
                 subsample=0.8, colsample_bytree=0.7,
                 min_child_samples=15, reg_lambda=2.0, verbose=-1)


# ══════════════════════════════════════════════════════════════════════════════
# DATA
# ══════════════════════════════════════════════════════════════════════════════

def load_french_3factor() -> pd.DataFrame:
    cache = os.path.join(CACHE_DIR, "3factor.csv")
    url = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip"
    if not os.path.exists(cache):
        r = requests.get(url, timeout=60)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        csv = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        with open(cache, "w") as f:
            f.write(z.read(csv).decode("utf-8", errors="replace"))
    rows = []
    with open(cache) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4 and len(parts[0]) == 6 and parts[0].isdigit():
                    yr, mo = int(parts[0][:4]), int(parts[0][4:])
                    if 1 <= mo <= 12 and yr >= 1920:
                        rows.append((f"{yr}-{mo:02d}",
                                     float(parts[1]), float(parts[2]),
                                     float(parts[3]), float(parts[4])))
            except: continue
    df = pd.DataFrame(rows, columns=["date","Mkt_RF","SMB","HML","RF"])
    df = df.set_index("date")
    df.index = pd.to_datetime(df.index, format="%Y-%m")
    return (df / 100.0).dropna()


def load_etf_monthly() -> pd.DataFrame:
    if os.path.exists(ETF_CACHE):
        df = pd.read_pickle(ETF_CACHE)
        if not df.empty and len(df.columns) >= 4:
            return df
    raise FileNotFoundError("ETF cache missing — run factor_regime_live.py first")


# ══════════════════════════════════════════════════════════════════════════════
# FEATURES
# ══════════════════════════════════════════════════════════════════════════════

def build_features(df: pd.DataFrame, smb_col: str, hml_col: str, mkt_col: str) -> pd.DataFrame:
    feats = pd.DataFrame(index=df.index)
    for factor, col in [("HML", hml_col), ("SMB", smb_col), ("Mkt_RF", mkt_col)]:
        s = df[col]
        feats[f"{factor}_t1"]    = s.shift(1)
        feats[f"{factor}_t3"]    = s.rolling(3).mean().shift(1)
        feats[f"{factor}_t6"]    = s.rolling(6).mean().shift(1)
        feats[f"{factor}_t12"]   = s.rolling(12).mean().shift(1)
        feats[f"{factor}_cum12"] = (1+s).rolling(12).apply(np.prod, raw=True).shift(1) - 1
        feats[f"{factor}_vol12"] = s.rolling(12).std().shift(1)
        feats[f"{factor}_vol24"] = s.rolling(24).std().shift(1)
        cumret = (1+s).cumprod()
        peak   = cumret.rolling(60, min_periods=12).max()
        feats[f"{factor}_dd"]    = ((cumret - peak) / peak).shift(1)
    feats["hml_smb_corr12"] = df[hml_col].rolling(12).corr(df[smb_col]).shift(1)
    feats["hml_mkt_corr12"] = df[hml_col].rolling(12).corr(df[mkt_col]).shift(1)
    feats["smb_mkt_corr12"] = df[smb_col].rolling(12).corr(df[mkt_col]).shift(1)
    feats["mkt_bull12"]     = (feats["Mkt_RF_cum12"] > 0).astype(float)
    feats["hml_vol_ratio"]  = feats["HML_vol12"] / df[hml_col].rolling(60).std().shift(1)
    feats["smb_vol_ratio"]  = feats["SMB_vol12"] / df[smb_col].rolling(60).std().shift(1)
    return feats.dropna(how="all")


def build_targets(ff3: pd.DataFrame) -> pd.DataFrame:
    tgts = pd.DataFrame(index=ff3.index)
    for factor, col in [("HML","hml_bull_12m"), ("SMB","smb_bull_12m")]:
        fwd = (1+ff3[factor]).rolling(HORIZON).apply(np.prod, raw=True).shift(-HORIZON)
        tgts[col] = (fwd > 1).astype(float)
    return tgts


# ══════════════════════════════════════════════════════════════════════════════
# MODELS + WALK-FORWARD
# ══════════════════════════════════════════════════════════════════════════════

def make_lr():
    return Pipeline([("sc", StandardScaler()),
                     ("clf", LogisticRegression(C=0.1, max_iter=500, random_state=42))])

def make_lgbm(seed=0):
    return lgb.LGBMClassifier(**{**LGBM_BASE, "random_state": seed})


def build_oof_probs(X: pd.DataFrame, y: pd.Series,
                    holdout_start_idx: int) -> tuple[pd.Series, pd.Series]:
    """
    Walk-forward OOF probabilities on dev set.
    Returns (oof_prob_filled, holdout_prob).
    oof_prob_filled: NaN months filled with 1.0 (always hold when no prediction).
    """
    X_dev = X.iloc[:holdout_start_idx]
    y_dev = y.iloc[:holdout_start_idx]
    X_hold = X.iloc[holdout_start_idx:]
    y_hold = y.iloc[holdout_start_idx:]

    n = len(X_dev)
    oof_prob = pd.Series(np.nan, index=X_dev.index)

    train_end = MIN_TRAIN
    while True:
        test_start = train_end + EMBARGO
        test_end   = test_start + TEST_LEN
        if test_end > n:
            break
        tr_idx = np.arange(0, train_end)
        te_idx = np.arange(test_start, test_end)

        X_tr, y_tr = X_dev.iloc[tr_idx], y_dev.iloc[tr_idx]
        X_te, y_te = X_dev.iloc[te_idx], y_dev.iloc[te_idx]

        clean_tr = ~(np.isinf(X_tr).any(axis=1) | np.isnan(X_tr).any(axis=1))
        clean_te = ~(np.isinf(X_te).any(axis=1) | np.isnan(X_te).any(axis=1))
        X_tr, y_tr = X_tr[clean_tr], y_tr[clean_tr]
        X_te, y_te = X_te[clean_te], y_te[clean_te]
        if len(X_tr) < 50: break

        lr = make_lr()
        lr.fit(X_tr, y_tr)
        oof_prob.iloc[te_idx[clean_te.values]] = lr.predict_proba(X_te)[:,1]
        train_end += STEP

    oof_prob_filled = oof_prob.fillna(1.0)   # gap months = always hold

    # Retrain on full dev for holdout
    clean_dev = ~(np.isinf(X_dev).any(axis=1) | np.isnan(X_dev).any(axis=1))
    lr_full = make_lr()
    lr_full.fit(X_dev[clean_dev], y_dev[clean_dev])
    hold_prob = pd.Series(lr_full.predict_proba(X_hold)[:,1], index=X_hold.index)

    return oof_prob_filled, hold_prob, lr_full


# ══════════════════════════════════════════════════════════════════════════════
# LAG BACKTEST
# ══════════════════════════════════════════════════════════════════════════════

def build_lagged_equity(factor_ret: pd.Series, prob: pd.Series,
                         lag: int, label: str) -> dict:
    """
    Simulate trading with `lag` months of signal delay.
    At month t: trade based on prob[t - lag].
    lag=0: no delay (ideal, unrealistic for French data)
    lag=2: French data publication delay
    """
    if lag > 0:
        # Shift signal forward by lag: prob available at t-lag applied at t
        signal_prob = prob.shift(lag)
    else:
        signal_prob = prob

    signal = (signal_prob > THRESH).astype(float).fillna(1.0)
    timed_ret = factor_ret * signal
    always_ret = factor_ret

    timed_eq = (1 + timed_ret).cumprod() * 100
    always_eq = (1 + always_ret).cumprod() * 100

    def cagr(s):
        s = s.dropna()
        if len(s) < 2: return 0.0
        yrs = (s.index[-1] - s.index[0]).days / 365.25
        return float((s.iloc[-1]/s.iloc[0])**(1/yrs) - 1) if yrs > 0 else 0.0

    def sharpe(ret_series):
        r = ret_series.dropna()
        if r.std() == 0: return 0.0
        return float(r.mean() / r.std() * np.sqrt(12))

    pct_invested = float(signal.mean())
    months_avoided = int((signal == 0).sum())

    return {
        "label":           label,
        "lag":             lag,
        "always_eq":       always_eq,
        "timed_eq":        timed_eq,
        "always_cagr":     cagr(always_eq),
        "timed_cagr":      cagr(timed_eq),
        "always_sharpe":   sharpe(always_ret),
        "timed_sharpe":    sharpe(timed_ret),
        "pct_invested":    pct_invested,
        "months_avoided":  months_avoided,
        "signal":          signal,
    }


def run_lag_study(name: str, factor_ret: pd.Series, X: pd.DataFrame,
                  y: pd.Series, lags: list[int] = [0, 1, 2, 3]) -> dict:
    """Full lag study for one factor."""
    print(f"\n  ── {name} ──────────────────────────────")

    # Align
    common = X.index.intersection(y.index).intersection(factor_ret.index)
    X = X.loc[common].ffill().bfill()
    y = y.loc[common].dropna()
    factor_ret = factor_ret.reindex(common)
    holdout_idx = (X.index < pd.Timestamp(HOLDOUT)).sum()

    # Build OOF probs
    oof_prob, hold_prob, lr_model = build_oof_probs(X, y, holdout_idx)

    # Full signal: dev OOF + holdout
    full_prob = pd.concat([oof_prob, hold_prob])
    full_ret  = factor_ret.reindex(full_prob.index)

    # AUC check
    y_full = y.reindex(full_prob.index).dropna()
    prob_aligned = full_prob.reindex(y_full.index)
    valid = ~prob_aligned.isna()
    if valid.sum() > 20 and len(np.unique(y_full[valid])) == 2:
        auc_no_lag = roc_auc_score(y_full[valid], prob_aligned[valid])
        auc_lag2   = roc_auc_score(y_full[valid],
                                    prob_aligned.shift(2).reindex(y_full.index)[valid].fillna(0.5))
    else:
        auc_no_lag = auc_lag2 = np.nan

    print(f"    AUC (no lag): {auc_no_lag:.3f}  AUC (2m lag): {auc_lag2:.3f}")

    results = {}
    for lag in lags:
        label = f"{name} lag={lag}m"
        r = build_lagged_equity(full_ret, full_prob, lag, label)
        results[lag] = r
        print(f"    lag={lag}m → always={r['always_cagr']:.1%}  "
              f"timed={r['timed_cagr']:.1%}  "
              f"invested={r['pct_invested']:.0%}  "
              f"avoided={r['months_avoided']} months")

    return {
        "name":         name,
        "lags":         results,
        "auc_no_lag":   auc_no_lag,
        "auc_lag2":     auc_lag2,
        "holdout_start": HOLDOUT,
    }


# ══════════════════════════════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════════════════════════════

DARK = dict(paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
            font=dict(color="#e0e0e0"))
COLORS = {0: "#00d4ff", 1: "#4ade80", 2: "#fb923c", 3: "#f87171",
          "always": "#6c7a89"}


def make_equity_figure(study: dict, title: str) -> go.Figure:
    lags = study["lags"]
    fig = go.Figure()

    # Always hold (same regardless of lag)
    always_eq = lags[0]["always_eq"].dropna()
    fig.add_trace(go.Scatter(
        x=always_eq.index, y=always_eq,
        name=f"Always Hold ({lags[0]['always_cagr']:.1%} CAGR)",
        line=dict(color=COLORS["always"], width=1.5, dash="dot"),
    ))

    for lag, r in lags.items():
        eq = r["timed_eq"].dropna()
        fig.add_trace(go.Scatter(
            x=eq.index, y=eq,
            name=f"Timed lag={lag}m ({r['timed_cagr']:.1%} CAGR, {r['pct_invested']:.0%} invested)",
            line=dict(color=COLORS[lag], width=2 if lag == 2 else 1.5,
                      dash="solid"),
        ))

    # Holdout boundary
    fig.add_vline(x=pd.Timestamp(HOLDOUT).timestamp() * 1000,
                  line_dash="dash", line_color="#555",
                  annotation_text="Holdout start (2010)", annotation_font_size=10)

    fig.update_layout(
        title=title,
        xaxis_title="Date", yaxis_title="Equity ($100 start)",
        height=420, **DARK,
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
    )
    return fig


def make_cagr_bar(hml_study: dict, smb_study: dict) -> go.Figure:
    lags = [0, 1, 2, 3]
    fig = go.Figure()

    for study, color_set in [(hml_study, ["#00d4ff","#4ade80","#fb923c","#f87171"]),
                              (smb_study, ["#818cf8","#a78bfa","#c084fc","#e879f9"])]:
        name = study["name"]
        always_c = study["lags"][0]["always_cagr"]
        xs, ys, cs = [], [], []
        for lag in lags:
            xs.append(f"{name} lag={lag}m")
            ys.append(study["lags"][lag]["timed_cagr"])
            cs.append(color_set[lag])

        fig.add_trace(go.Bar(x=xs, y=ys, marker_color=cs,
                             name=name, text=[f"{v:.1%}" for v in ys],
                             textposition="outside"))
        # Always-hold reference line per group
        fig.add_hline(y=always_c, line_dash="dot",
                      line_color="#888" if name == "HML" else "#aaa",
                      annotation_text=f"{name} always={always_c:.1%}",
                      annotation_font_size=9)

    fig.update_layout(
        title="CAGR by Lag — How much signal degrades as lag increases",
        yaxis_title="CAGR", yaxis_tickformat=".1%",
        height=380, **DARK,
        barmode="group",
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig


def build_html(hml_study: dict, smb_study: dict) -> str:
    fig_hml  = make_equity_figure(hml_study,  "HML (Value Premium) — Timed Strategy by Lag")
    fig_smb  = make_equity_figure(smb_study,  "SMB (Size Premium) — Timed Strategy by Lag")
    fig_bar  = make_cagr_bar(hml_study, smb_study)

    # Summary table rows
    rows = ""
    for study in [hml_study, smb_study]:
        for lag, r in study["lags"].items():
            lag_str = f"{lag}m{'  ← French data' if lag == 2 and study['name'] == 'HML' else ''}"
            lag_str += "  ← live (IWM-SPY)" if lag == 0 and study["name"] == "SMB" else ""
            delta = r["timed_cagr"] - r["always_cagr"]
            tag = ("tag-good" if delta > 0.005
                   else "tag-warn" if delta > -0.005
                   else "tag-bad")
            rows += f"""<tr>
              <td>{study['name']}</td>
              <td>{lag_str}</td>
              <td>{r['always_cagr']:.1%}</td>
              <td>{r['timed_cagr']:.1%}</td>
              <td><span class="{tag}">{delta:+.1%}</span></td>
              <td>{r['always_sharpe']:.2f}</td>
              <td>{r['timed_sharpe']:.2f}</td>
              <td>{r['pct_invested']:.0%}</td>
              <td>{r['months_avoided']}</td>
            </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Factor Regime — Lag Backtest</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  html,body{{background:#0f1117!important;color:#e0e0e0;font-family:'Inter',sans-serif;margin:0;padding:0}}
  .container{{max-width:1200px;margin:0 auto;padding:24px}}
  h1{{font-size:1.6rem;color:#00d4ff;margin-bottom:4px}}
  .subtitle{{color:#888;font-size:.9rem;margin-bottom:28px}}
  .section{{font-size:1.05rem;color:#aaa;margin:28px 0 12px;border-bottom:1px solid #2a2d3a;padding-bottom:6px}}
  .verdict{{background:#1a1d2e;border-left:4px solid #00d4ff;padding:14px 18px;border-radius:0 8px 8px 0;margin:20px 0;font-size:.95rem}}
  .chart-block{{background:#1a1d2e;border:1px solid #2a2d3a;border-radius:8px;padding:16px;margin-bottom:16px}}
  table{{width:100%;border-collapse:collapse;font-size:.85rem}}
  th{{background:#1a1d2e;color:#888;padding:8px 10px;text-align:left;border-bottom:1px solid #2a2d3a}}
  td{{padding:8px 10px;border-bottom:1px solid #1e2130;color:#ccc}}
  tr:hover td{{background:#1a1d2e}}
  .tag-good{{background:#1a3a2a;color:#4ade80;padding:2px 8px;border-radius:12px;font-size:.8rem}}
  .tag-warn{{background:#3a3a1a;color:#facc15;padding:2px 8px;border-radius:12px;font-size:.8rem}}
  .tag-bad{{background:#3a1a1a;color:#f87171;padding:2px 8px;border-radius:12px;font-size:.8rem}}
  .highlight{{color:#fb923c;font-weight:600}}
</style>
</head>
<body>
<div class="container">
  <h1>Factor Regime — Lag Backtest</h1>
  <div class="subtitle">
    French data has ~2 month publication lag. Does waiting hurt the signal?<br>
    Dev: 1926→2010 (OOF walk-forward) &nbsp;|&nbsp; Holdout: 2010→2026
  </div>

  <div class="verdict">
    <strong>What "lag=2" means:</strong> At month t, we only see French data through month t-2.
    We compute features, get model probability, apply trade at month t.
    The signal predicts the <em>next 12 months</em> — so a 2-month stale reading
    still captures the dominant 10-month forward window intact.
  </div>

  <div class="section">Charts</div>
  <div class="chart-block">{fig_hml.to_html(full_html=False, include_plotlyjs=False)}</div>
  <div class="chart-block">{fig_smb.to_html(full_html=False, include_plotlyjs=False)}</div>
  <div class="chart-block">{fig_bar.to_html(full_html=False, include_plotlyjs=False)}</div>

  <div class="section">Summary Table</div>
  <div style="overflow-x:auto">
  <table>
    <tr>
      <th>Factor</th><th>Lag</th>
      <th>Always CAGR</th><th>Timed CAGR</th><th>Delta</th>
      <th>Always Sharpe</th><th>Timed Sharpe</th>
      <th>% Invested</th><th>Months Avoided</th>
    </tr>
    {rows}
  </table>
  </div>

  <div class="section">Key Questions</div>
  <div class="verdict">
    <strong>Q: Does lag=2 materially hurt HML?</strong><br>
    The signal predicts 12-month forward returns. Shifting by 2 months
    means your forecast window is [t+2 → t+14] instead of [t → t+12].
    These windows overlap by 10 months — so ~83% of the information is preserved.<br><br>
    <strong>Q: SMB needs zero lag?</strong><br>
    SMB uses IWM-SPY (live ETF data) so lag=0 is the real-world scenario.
    Lag tests on SMB show how robust the signal is to stale inputs.<br><br>
    <strong>Q: When should I stop if lag hurts too much?</strong><br>
    If lag=2 timed CAGR &lt; always-hold CAGR, the French lag cost exceeds the
    signal benefit → switch to EDGAR proxy (weak but real-time) or drop HML.
  </div>

  <p style="color:#444;font-size:.8rem;margin-top:32px">
    Generated {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} ART
  </p>
</div>
</body>
</html>"""
    return html


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("Factor Regime — Lag Backtest")
    print("=" * 60)

    print("\n[1/4] Loading data...")
    ff3 = load_french_3factor()
    print(f"  French: {ff3.index[0].strftime('%Y-%m')} → {ff3.index[-1].strftime('%Y-%m')}")

    try:
        etf_prices = load_etf_monthly()
        etf_ret = etf_prices.pct_change().dropna()
        etf_ret["SMB_etf"] = etf_ret["IWM"] - etf_ret["SPY"]
        etf_ret["Mkt_etf"] = etf_ret["SPY"]
        has_etf = True
        print(f"  ETF: {etf_ret.index[0].strftime('%Y-%m')} → {etf_ret.index[-1].strftime('%Y-%m')}")
    except FileNotFoundError:
        has_etf = False
        print("  ETF cache not found — SMB will use French SMB")

    print("\n[2/4] Building features and targets...")
    X_french = build_features(ff3, smb_col="SMB", hml_col="HML", mkt_col="Mkt_RF")
    y_all    = build_targets(ff3)
    print(f"  French features: {X_french.shape}")

    if has_etf:
        X_smb = build_features(etf_ret, smb_col="SMB_etf",
                                hml_col="SMB_etf",  # dummy HML col (not used for SMB signal)
                                mkt_col="Mkt_etf")
        smb_ret = etf_ret["SMB_etf"]
        # For SMB targets we still use French ground truth
        y_smb = y_all["smb_bull_12m"].reindex(X_smb.index)
    else:
        X_smb  = X_french
        smb_ret = ff3["SMB"]
        y_smb   = y_all["smb_bull_12m"]

    print("\n[3/4] Running lag studies...")
    hml_study = run_lag_study("HML", ff3["HML"], X_french, y_all["hml_bull_12m"])
    smb_study = run_lag_study("SMB", smb_ret,     X_smb,   y_smb)

    print("\n[4/4] Building report...")
    html = build_html(hml_study, smb_study)
    with open(OUT_HTML, "w") as f:
        f.write(html)
    print(f"  Wrote {OUT_HTML}")

    # Save JSON summary (no equity series)
    def _clean(study):
        out = {"name": study["name"],
               "auc_no_lag": study["auc_no_lag"],
               "auc_lag2":   study["auc_lag2"]}
        for lag, r in study["lags"].items():
            out[f"lag{lag}"] = {
                "always_cagr":   r["always_cagr"],
                "timed_cagr":    r["timed_cagr"],
                "always_sharpe": r["always_sharpe"],
                "timed_sharpe":  r["timed_sharpe"],
                "pct_invested":  r["pct_invested"],
                "months_avoided":r["months_avoided"],
            }
        return out

    with open(OUT_JSON, "w") as f:
        json.dump({"HML": _clean(hml_study), "SMB": _clean(smb_study)}, f, indent=2, default=str)
    print(f"  Wrote {OUT_JSON}")

    print("\n" + "=" * 60)
    print("VERDICT")
    print("=" * 60)
    for study in [hml_study, smb_study]:
        print(f"\n  {study['name']}:")
        r0 = study["lags"][0]
        r2 = study["lags"][2]
        cost = r0["timed_cagr"] - r2["timed_cagr"]
        print(f"    No-lag timed CAGR:   {r0['timed_cagr']:.1%}")
        print(f"    2m-lag timed CAGR:   {r2['timed_cagr']:.1%}")
        print(f"    Lag cost:            {cost:.2%}/yr")
        print(f"    Always-hold CAGR:    {r2['always_cagr']:.1%}")
        viable = r2["timed_cagr"] > r2["always_cagr"]
        print(f"    Lag=2 beats always?  {'✓ YES' if viable else '✗ NO'}")


if __name__ == "__main__":
    main()
