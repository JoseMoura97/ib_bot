"""
Factor Combination Backtest
============================

Computes per-window CAGRs and builds the combined strategy:
  - HML: always hold (no regime timing needed)
  - SMB: regime-timed via IWM-SPY signal (LR model)
  - COMBO: HML always + SMB timed (50/50 blend)

Windows: 15yr / 10yr / 5yr / 3yr  (ending at latest available data)

Run:
  python3 research/factor_combo_backtest.py
"""
from __future__ import annotations
import io, json, os, warnings, zipfile
import numpy as np
import pandas as pd
import requests
import plotly.graph_objects as go
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
warnings.filterwarnings("ignore")

OUT_DIR   = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(OUT_DIR, ".french_cache")
ETF_CACHE = os.path.join(CACHE_DIR, "etf_monthly.pkl")
OUT_HTML  = os.path.join(OUT_DIR, "factor_combo_backtest.html")

HORIZON   = 12
EMBARGO   = 6
MIN_TRAIN = 240
STEP      = 24
TEST_LEN  = 24
HOLDOUT   = "2010-01"
THRESH    = 0.52

WINDOWS = {"15yr": 15, "10yr": 10, "5yr": 5, "3yr": 3}
DARK    = dict(paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
               font=dict(color="#e0e0e0"))


# ══════════════════════════════════════════════════════════════════════════════
# DATA
# ══════════════════════════════════════════════════════════════════════════════

def load_french() -> pd.DataFrame:
    cache = os.path.join(CACHE_DIR, "3factor.csv")
    rows = []
    with open(cache) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                p = [x.strip() for x in line.split(",")]
                if len(p) >= 4 and len(p[0]) == 6 and p[0].isdigit():
                    yr, mo = int(p[0][:4]), int(p[0][4:])
                    if 1 <= mo <= 12 and yr >= 1920:
                        rows.append((f"{yr}-{mo:02d}",
                                     float(p[1]), float(p[2]), float(p[3]), float(p[4])))
            except: continue
    df = pd.DataFrame(rows, columns=["date","Mkt_RF","SMB","HML","RF"])
    df = df.set_index("date")
    df.index = pd.to_datetime(df.index, format="%Y-%m")
    return (df / 100.0).dropna()


def load_etf() -> pd.DataFrame:
    return pd.read_pickle(ETF_CACHE)


# ══════════════════════════════════════════════════════════════════════════════
# FEATURES + MODEL
# ══════════════════════════════════════════════════════════════════════════════

def build_features(df, smb_col, hml_col, mkt_col):
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


def build_targets(ff3):
    tgts = pd.DataFrame(index=ff3.index)
    for factor, col in [("HML","hml_bull_12m"), ("SMB","smb_bull_12m")]:
        fwd = (1+ff3[factor]).rolling(HORIZON).apply(np.prod, raw=True).shift(-HORIZON)
        tgts[col] = (fwd > 1).astype(float)
    return tgts


def make_lr():
    return Pipeline([("sc", StandardScaler()),
                     ("clf", LogisticRegression(C=0.1, max_iter=500, random_state=42))])


def build_smb_signal(X_etf, y_smb_french, ff3) -> pd.Series:
    """
    Walk-forward on French SMB targets with ETF features.
    Dev = pre-2010 ETF months only (short, but ETF only starts 2000).
    Fill pre-ETF months using French-trained model.
    Returns full signal probability series covering 1926→2026.
    """
    # Phase 1: train on French data pre-ETF, apply to ETF for 2000→2026
    common_etf = X_etf.index.intersection(y_smb_french.index)
    X_oos = X_etf.loc[common_etf].ffill().bfill()
    y_oos = y_smb_french.loc[common_etf].dropna()
    X_oos = X_oos.reindex(y_oos.index)

    # Train on French features pre-ETF start
    X_french = build_features(ff3, smb_col="SMB", hml_col="HML", mkt_col="Mkt_RF")
    y_fr     = build_targets(ff3)["smb_bull_12m"]
    common_fr = X_french.index.intersection(y_fr.index)
    X_fr = X_french.loc[common_fr].ffill().bfill()
    y_fr = y_fr.loc[common_fr]

    # French dev: pre-ETF (1926→2000) for initial model
    pre_etf = X_fr.index < X_oos.index[0]
    X_dev_fr = X_fr[pre_etf]
    y_dev_fr = y_fr[pre_etf]

    clean = ~(np.isinf(X_dev_fr).any(axis=1) | np.isnan(X_dev_fr).any(axis=1))
    lr_pre = make_lr()
    lr_pre.fit(X_dev_fr[clean], y_dev_fr[clean])

    # Apply to ETF features
    clean_oos = ~(np.isinf(X_oos).any(axis=1) | np.isnan(X_oos).any(axis=1))
    oos_prob = pd.Series(lr_pre.predict_proba(X_oos[clean_oos])[:,1],
                          index=X_oos[clean_oos].index)

    # Also run walk-forward on French for pre-ETF period
    holdout_idx = (X_fr.index < pd.Timestamp(HOLDOUT)).sum()
    n = holdout_idx
    oof_prob = pd.Series(np.nan, index=X_fr.index[:n])
    train_end = MIN_TRAIN
    while True:
        test_start = train_end + EMBARGO
        test_end   = test_start + TEST_LEN
        if test_end > n: break
        X_tr, y_tr = X_fr.iloc[:train_end], y_fr.iloc[:train_end]
        X_te, y_te = X_fr.iloc[test_start:test_end], y_fr.iloc[test_start:test_end]
        cl_tr = ~(np.isinf(X_tr).any(axis=1) | np.isnan(X_tr).any(axis=1))
        cl_te = ~(np.isinf(X_te).any(axis=1) | np.isnan(X_te).any(axis=1))
        if cl_tr.sum() < 50: break
        lr = make_lr()
        lr.fit(X_tr[cl_tr], y_tr[cl_tr])
        te_idx = np.where(cl_te.values)[0]
        oof_prob.iloc[test_start + te_idx] = lr.predict_proba(X_te[cl_te])[:,1]
        train_end += STEP
    oof_prob = oof_prob.fillna(1.0)

    # Holdout: retrain on full French dev, predict on holdout
    lr_hold = make_lr()
    cl_dev  = ~(np.isinf(X_fr.iloc[:holdout_idx]).any(axis=1) | np.isnan(X_fr.iloc[:holdout_idx]).any(axis=1))
    lr_hold.fit(X_fr.iloc[:holdout_idx][cl_dev], y_fr.iloc[:holdout_idx][cl_dev])

    # Post-ETF: use ETF features (OOS from pre-ETF trained model)
    # For 2010+ holdout period: use the ETF oos_prob
    # Combine: pre-ETF=oof_prob, ETF era=oos_prob
    full_prob = oof_prob.copy()

    # For ETF overlap months (2000-2026) overwrite with ETF-feature predictions
    for idx in oos_prob.index:
        if idx in full_prob.index:
            full_prob.loc[idx] = oos_prob.loc[idx]
        # If beyond French OOF range, append
    # Append holdout months that aren't in oof (2010+)
    holdout_months = X_fr.index[holdout_idx:]
    # For holdout: use ETF probs where available, French model otherwise
    for idx in holdout_months:
        if idx in oos_prob.index:
            full_prob[idx] = oos_prob[idx]
        else:
            cl = not (any(np.isinf(X_fr.loc[idx])) or any(np.isnan(X_fr.loc[idx])))
            if cl:
                full_prob[idx] = lr_hold.predict_proba(X_fr.loc[[idx]])[:,1][0]
            else:
                full_prob[idx] = 1.0

    return full_prob.sort_index()


# ══════════════════════════════════════════════════════════════════════════════
# METRICS
# ══════════════════════════════════════════════════════════════════════════════

def cagr(eq: pd.Series) -> float:
    eq = eq.dropna()
    if len(eq) < 2: return float("nan")
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    return float((eq.iloc[-1]/eq.iloc[0])**(1/yrs) - 1) if yrs > 0 else float("nan")


def sharpe(ret: pd.Series) -> float:
    r = ret.dropna()
    return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0


def max_dd(eq: pd.Series) -> float:
    eq = eq.dropna()
    peak = eq.cummax()
    return float(((eq - peak) / peak).min())


def window_stats(ret: pd.Series, label: str) -> dict:
    eq = (1 + ret).cumprod() * 100
    end = ret.index[-1]
    out = {"label": label, "full_cagr": cagr(eq), "full_sharpe": sharpe(ret),
           "full_maxdd": max_dd(eq), "eq": eq, "ret": ret}
    for wlabel, yrs in WINDOWS.items():
        start = end - pd.DateOffset(years=yrs)
        sl = ret.loc[start:]
        if len(sl) < 12:
            out[wlabel] = float("nan")
            continue
        eq_w = (1 + sl).cumprod() * 100
        out[wlabel] = cagr(eq_w)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════════════════════════════

def build_html(strategies: list[dict], spy_ret: pd.Series) -> str:
    # ── 1. Full equity curves chart
    fig_eq = go.Figure()
    colors = {"HML Always":   "#fb923c",
              "SMB Timed":    "#00d4ff",
              "COMBO":        "#4ade80",
              "SPY":          "#6c7a89"}

    spy_stats = window_stats(spy_ret.reindex(strategies[0]["ret"].index).dropna(), "SPY")
    for s in strategies + [spy_stats]:
        eq = s["eq"].dropna()
        fig_eq.add_trace(go.Scatter(
            x=eq.index, y=eq,
            name=f"{s['label']} ({s['full_cagr']:.1%} CAGR)",
            line=dict(color=colors.get(s["label"], "#aaa"),
                      width=2.5 if s["label"] == "COMBO" else 1.8)))

    fig_eq.add_vline(x=pd.Timestamp(HOLDOUT).timestamp()*1000,
                     line_dash="dash", line_color="#444",
                     annotation_text="Holdout 2010", annotation_font_size=10)
    fig_eq.update_layout(title="Equity Curves — Full History",
                         xaxis_title="Date", yaxis_title="$100 start",
                         height=430, **DARK,
                         legend=dict(bgcolor="rgba(0,0,0,0)"))

    # ── 2. Window CAGR heatmap-style bar chart
    window_labels = list(WINDOWS.keys())
    fig_bar = go.Figure()
    for s in strategies + [spy_stats]:
        vals  = [s.get(w, float("nan")) for w in window_labels]
        fig_bar.add_trace(go.Bar(
            name=s["label"],
            x=window_labels, y=vals,
            text=[f"{v:.1%}" if not np.isnan(v) else "—" for v in vals],
            textposition="outside",
            marker_color=colors.get(s["label"], "#aaa"),
        ))
    fig_bar.add_hline(y=0, line_color="#555", line_width=1)
    fig_bar.update_layout(title="CAGR by Window",
                          yaxis_title="CAGR", yaxis_tickformat=".1%",
                          barmode="group", height=400, **DARK,
                          legend=dict(bgcolor="rgba(0,0,0,0)"))

    # ── 3. Summary table
    all_strats = strategies + [spy_stats]
    hdr = ["Strategy"] + [f"{w} CAGR" for w in window_labels] + ["Full CAGR","Sharpe","MaxDD"]
    rows_html = ""
    for s in all_strats:
        tds = f"<td><strong>{s['label']}</strong></td>"
        for w in window_labels:
            v = s.get(w, float("nan"))
            if np.isnan(v):
                tds += "<td>—</td>"
            else:
                cls = "pos" if v > 0.02 else ("neg" if v < 0 else "")
                tds += f'<td class="{cls}">{v:.1%}</td>'
        tds += f"<td>{s['full_cagr']:.1%}</td>"
        tds += f"<td>{s['full_sharpe']:.2f}</td>"
        tds += f"<td>{s['full_maxdd']:.1%}</td>"
        rows_html += f"<tr>{tds}</tr>"

    plots = (fig_eq.to_html(full_html=False, include_plotlyjs=False) +
             fig_bar.to_html(full_html=False, include_plotlyjs=False))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Factor Combo Backtest</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  html,body{{background:#0f1117!important;color:#e0e0e0;font-family:'Inter',sans-serif;margin:0;padding:0}}
  .container{{max-width:1200px;margin:0 auto;padding:24px}}
  h1{{font-size:1.6rem;color:#4ade80;margin-bottom:4px}}
  .subtitle{{color:#888;font-size:.9rem;margin-bottom:28px}}
  .section{{font-size:1.05rem;color:#aaa;margin:28px 0 12px;border-bottom:1px solid #2a2d3a;padding-bottom:6px}}
  .verdict{{background:#1a1d2e;border-left:4px solid #4ade80;padding:14px 18px;border-radius:0 8px 8px 0;margin:20px 0;font-size:.95rem;line-height:1.6}}
  .chart-block{{background:#1a1d2e;border:1px solid #2a2d3a;border-radius:8px;padding:16px;margin-bottom:16px}}
  table{{width:100%;border-collapse:collapse;font-size:.85rem}}
  th{{background:#1a1d2e;color:#888;padding:8px 10px;text-align:left;border-bottom:1px solid #2a2d3a}}
  td{{padding:8px 10px;border-bottom:1px solid #1e2130;color:#ccc;text-align:right}}
  td:first-child{{text-align:left}}
  tr:hover td{{background:#1a1d2e}}
  .pos{{color:#4ade80}} .neg{{color:#f87171}}
</style>
</head>
<body>
<div class="container">
  <h1>Factor Combination Backtest</h1>
  <div class="subtitle">
    HML: always hold value premium (no timing, no lag) &nbsp;|&nbsp;
    SMB: regime-timed via IWM−SPY signal &nbsp;|&nbsp;
    COMBO: 50/50 blend
  </div>

  <div class="verdict">
    <strong>Strategy logic:</strong><br>
    • <strong>HML Always</strong> = long the value factor every month. No model. No French lag.<br>
    • <strong>SMB Timed</strong> = long the size factor only when LR regime signal &gt; 0.52. Uses IWM−SPY (live, 0 lag).<br>
    • <strong>COMBO</strong> = 50% HML Always + 50% SMB Timed. Rebalanced monthly.
    This is the ib_bot strategy spec: value core + conditional size tilt.
  </div>

  <div class="section">Charts</div>
  <div class="chart-block">{plots}</div>

  <div class="section">Window CAGR Table</div>
  <div style="overflow-x:auto">
  <table>
    <tr>{''.join(f'<th>{h}</th>' for h in hdr)}</tr>
    {rows_html}
  </table>
  </div>

  <p style="color:#444;font-size:.8rem;margin-top:32px">
    Dev: 1926→2010 walk-forward OOF &nbsp;|&nbsp; Holdout: 2010→2026 &nbsp;|&nbsp;
    SMB timed threshold: p&gt;{THRESH} &nbsp;|&nbsp;
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
    print("Factor Combination Backtest")
    print("=" * 60)

    print("\n[1/5] Loading data...")
    ff3 = load_french()
    etf_prices = load_etf()
    etf_ret = etf_prices.pct_change().dropna()
    etf_ret["SMB_etf"] = etf_ret["IWM"] - etf_ret["SPY"]
    etf_ret["HML_dummy"] = etf_ret["SMB_etf"]  # placeholder
    etf_ret["Mkt_etf"]  = etf_ret["SPY"]
    spy_ret = etf_ret["SPY"]
    print(f"  French: {ff3.index[0].strftime('%Y-%m')} → {ff3.index[-1].strftime('%Y-%m')}")
    print(f"  ETF:    {etf_ret.index[0].strftime('%Y-%m')} → {etf_ret.index[-1].strftime('%Y-%m')}")

    print("\n[2/5] Building features...")
    X_etf = build_features(etf_ret, smb_col="SMB_etf",
                            hml_col="HML_dummy", mkt_col="Mkt_etf")
    y_all = build_targets(ff3)
    print(f"  ETF features: {X_etf.shape}")

    print("\n[3/5] Building SMB regime signal (IWM-SPY)...")
    smb_prob = build_smb_signal(X_etf, y_all["smb_bull_12m"], ff3)
    print(f"  SMB signal: {smb_prob.index[0].strftime('%Y-%m')} → {smb_prob.index[-1].strftime('%Y-%m')}")
    print(f"  % months invested: {(smb_prob > THRESH).mean():.0%}")

    print("\n[4/5] Building strategy returns...")

    # Common index: wherever we have both French HML and SMB signal
    common = ff3["HML"].index.intersection(smb_prob.index)
    hml_ret  = ff3["HML"].reindex(common)
    smb_ret_f = ff3["SMB"].reindex(common)
    smb_signal = (smb_prob.reindex(common) > THRESH).astype(float).fillna(1.0)

    # For SMB use ETF returns where available, French otherwise
    smb_etf_aligned = etf_ret["SMB_etf"].reindex(common)
    smb_use = smb_etf_aligned.where(smb_etf_aligned.notna(), smb_ret_f)

    hml_always_ret = hml_ret
    smb_timed_ret  = smb_use * smb_signal
    combo_ret      = 0.5 * hml_always_ret + 0.5 * smb_timed_ret

    strategies = [
        window_stats(hml_always_ret, "HML Always"),
        window_stats(smb_timed_ret,  "SMB Timed"),
        window_stats(combo_ret,      "COMBO"),
    ]

    print("\n  Window CAGR summary:")
    print(f"  {'Strategy':<16}", end="")
    for w in WINDOWS: print(f"  {w:>8}", end="")
    print(f"  {'Full':>8}  {'Sharpe':>8}  {'MaxDD':>8}")
    print("  " + "-"*76)
    spy_stats = window_stats(spy_ret.reindex(common).dropna(), "SPY")
    for s in strategies + [spy_stats]:
        print(f"  {s['label']:<16}", end="")
        for w in WINDOWS:
            v = s.get(w, float("nan"))
            print(f"  {v:>7.1%}" if not np.isnan(v) else f"  {'—':>7}", end="")
        print(f"  {s['full_cagr']:>7.1%}  {s['full_sharpe']:>8.2f}  {s['full_maxdd']:>7.1%}")

    print("\n[5/5] Building report...")
    html = build_html(strategies, spy_ret.reindex(common).dropna())
    with open(OUT_HTML, "w") as f:
        f.write(html)
    print(f"  Wrote {OUT_HTML}")


if __name__ == "__main__":
    main()
