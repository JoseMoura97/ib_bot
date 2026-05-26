"""
Factor ETF Strategy Backtest
==============================

Long-only. One signal. Two ETFs.

  SMB regime ON  → IWN (iShares Russell 2000 Value)  = market + value + size
  SMB regime OFF → IWD (iShares Russell 1000 Value)  = market + value

Benchmark: SPY (pure market beta)
Also shows: IWD always, IWN always, 50/50 blend

SMB signal: LR model trained on French monthly data (IWM-SPY features).
Data: yfinance monthly prices, French 3-factor for signal training.

Run:
  python3 research/factor_etf_strategy.py
"""
from __future__ import annotations
import io, json, os, warnings, zipfile
import numpy as np
import pandas as pd
import requests
import yfinance as yf
import plotly.graph_objects as go
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
warnings.filterwarnings("ignore")

OUT_DIR   = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(OUT_DIR, ".french_cache")
OUT_HTML  = os.path.join(OUT_DIR, "factor_etf_strategy.html")

HORIZON  = 12
EMBARGO  = 6
MIN_TRAIN= 240
STEP     = 24
TEST_LEN = 24
HOLDOUT  = "2010-01"
THRESH   = 0.52

WINDOWS = {"15yr": 15, "10yr": 10, "5yr": 5, "3yr": 3}
DARK    = dict(paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
               font=dict(color="#e0e0e0"))
COLORS  = {"Strategy": "#4ade80", "IWD Always": "#fb923c",
           "IWN Always": "#00d4ff", "IWD+IWN 50/50": "#a78bfa", "SPY": "#6c7a89"}


# ══════════════════════════════════════════════════════════════════════════════
# DATA
# ══════════════════════════════════════════════════════════════════════════════

def _yf_monthly(ticker: str, start: str = "1999-01-01") -> pd.Series:
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


def load_etf_prices(tickers: list[str]) -> pd.DataFrame:
    """Load from cache or download. Cache: etf_all.pkl"""
    cache = os.path.join(CACHE_DIR, "etf_all.pkl")
    if os.path.exists(cache):
        df = pd.read_pickle(cache)
        if all(t in df.columns for t in tickers):
            return df[tickers]

    prices = {}
    for tk in tickers:
        print(f"  Fetching {tk}...", end="", flush=True)
        try:
            s = _yf_monthly(tk)
            prices[tk] = s
            print(f" {len(s)} months")
        except Exception as e:
            print(f" ERROR: {e}")

    df = pd.DataFrame(prices).dropna()
    df.to_pickle(cache)
    return df[tickers]


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
                                     float(p[1]), float(p[2]),
                                     float(p[3]), float(p[4])))
            except: continue
    df = pd.DataFrame(rows, columns=["date","Mkt_RF","SMB","HML","RF"])
    df.index = pd.to_datetime([r[0] for r in rows], format="%Y-%m")
    df = df.drop("date", axis=1) / 100.0
    return df.dropna()


# ══════════════════════════════════════════════════════════════════════════════
# FEATURES + SIGNAL
# ══════════════════════════════════════════════════════════════════════════════

def build_features(smb: pd.Series, mkt: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame({"SMB": smb, "HML": smb, "Mkt_RF": mkt})
    feats = pd.DataFrame(index=df.index)
    for factor, col in [("HML","HML"), ("SMB","SMB"), ("Mkt_RF","Mkt_RF")]:
        s = df[col]
        feats[f"{factor}_t1"]    = s.shift(1)
        feats[f"{factor}_t3"]    = s.rolling(3).mean().shift(1)
        feats[f"{factor}_t6"]    = s.rolling(6).mean().shift(1)
        feats[f"{factor}_t12"]   = s.rolling(12).mean().shift(1)
        feats[f"{factor}_cum12"] = (1+s).rolling(12).apply(np.prod,raw=True).shift(1)-1
        feats[f"{factor}_vol12"] = s.rolling(12).std().shift(1)
        feats[f"{factor}_vol24"] = s.rolling(24).std().shift(1)
        cumret = (1+s).cumprod()
        peak   = cumret.rolling(60, min_periods=12).max()
        feats[f"{factor}_dd"]    = ((cumret-peak)/peak).shift(1)
    feats["hml_smb_corr12"] = df["HML"].rolling(12).corr(df["SMB"]).shift(1)
    feats["hml_mkt_corr12"] = df["HML"].rolling(12).corr(df["Mkt_RF"]).shift(1)
    feats["smb_mkt_corr12"] = df["SMB"].rolling(12).corr(df["Mkt_RF"]).shift(1)
    feats["mkt_bull12"]     = (feats["Mkt_RF_cum12"] > 0).astype(float)
    feats["hml_vol_ratio"]  = feats["HML_vol12"] / df["HML"].rolling(60).std().shift(1)
    feats["smb_vol_ratio"]  = feats["SMB_vol12"] / df["SMB"].rolling(60).std().shift(1)
    return feats.dropna(how="all")


def make_lr():
    return Pipeline([("sc", StandardScaler()),
                     ("clf", LogisticRegression(C=0.1, max_iter=500, random_state=42))])


def build_smb_signal_full(ff3: pd.DataFrame,
                           smb_etf: pd.Series,
                           spy_ret: pd.Series) -> pd.Series:
    """
    SMB regime signal covering full ETF history (2000→now).
    Train: French data pre-ETF (1926→2000), features = IWM-SPY.
    Gives a probability for each month. Signal = prob > THRESH.
    """
    # French targets
    fwd = (1 + ff3["SMB"]).rolling(HORIZON).apply(np.prod, raw=True).shift(-HORIZON)
    y_fr = (fwd > 1).astype(float).dropna()

    # French features (using French SMB + Mkt as proxy for training)
    X_fr = build_features(ff3["SMB"], ff3["Mkt_RF"])

    # Walk-forward on French dev (pre-HOLDOUT)
    common = X_fr.index.intersection(y_fr.index)
    X_fr = X_fr.loc[common].ffill().bfill()
    y_fr = y_fr.loc[common]
    holdout_idx = (X_fr.index < pd.Timestamp(HOLDOUT)).sum()
    n = holdout_idx

    oof = pd.Series(np.nan, index=X_fr.index[:n])
    train_end = MIN_TRAIN
    while True:
        ts = train_end + EMBARGO
        te = ts + TEST_LEN
        if te > n: break
        X_tr, y_tr = X_fr.iloc[:train_end], y_fr.iloc[:train_end]
        X_te       = X_fr.iloc[ts:te]
        cl_tr = ~(np.isinf(X_tr).any(axis=1)|np.isnan(X_tr).any(axis=1))
        cl_te = ~(np.isinf(X_te).any(axis=1)|np.isnan(X_te).any(axis=1))
        if cl_tr.sum() < 50: break
        lr = make_lr()
        lr.fit(X_tr[cl_tr], y_tr[cl_tr])
        idx = np.where(cl_te.values)[0]
        oof.iloc[ts + idx] = lr.predict_proba(X_te[cl_te])[:,1]
        train_end += STEP
    oof = oof.fillna(1.0)

    # Retrain on full French dev for holdout + ETF period
    cl_dev = ~(np.isinf(X_fr.iloc[:holdout_idx]).any(axis=1) |
                np.isnan(X_fr.iloc[:holdout_idx]).any(axis=1))
    lr_full = make_lr()
    lr_full.fit(X_fr.iloc[:holdout_idx][cl_dev], y_fr.iloc[:holdout_idx][cl_dev])

    # Build ETF features (IWM-SPY, live signal)
    X_etf = build_features(smb_etf, spy_ret)

    # Holdout months: use ETF features where available, French otherwise
    hold_months = X_fr.index[holdout_idx:]
    hold_prob = pd.Series(index=hold_months, dtype=float)
    for idx in hold_months:
        if idx in X_etf.index:
            row = X_etf.loc[[idx]]
            if not (np.isinf(row).any(axis=1) | np.isnan(row).any(axis=1)).any():
                hold_prob[idx] = lr_full.predict_proba(row)[:,1][0]
                continue
        # Fallback to French features
        if idx in X_fr.index:
            row = X_fr.loc[[idx]]
            if not (np.isinf(row).any(axis=1) | np.isnan(row).any(axis=1)).any():
                hold_prob[idx] = lr_full.predict_proba(row)[:,1][0]
                continue
        hold_prob[idx] = 1.0
    hold_prob = hold_prob.fillna(1.0)

    # For ETF period before holdout (2000→2010): recompute with ETF features
    etf_pre_hold = X_etf.index[X_etf.index < pd.Timestamp(HOLDOUT)]
    etf_pre_prob = pd.Series(index=etf_pre_hold, dtype=float)
    for idx in etf_pre_hold:
        row = X_etf.loc[[idx]]
        if not (np.isinf(row).any(axis=1) | np.isnan(row).any(axis=1)).any():
            etf_pre_prob[idx] = lr_full.predict_proba(row)[:,1][0]
        else:
            etf_pre_prob[idx] = 1.0

    # Combine: OOF (French, pre-holdout) overwritten by ETF where available,
    # then holdout
    full = oof.copy()
    for idx in etf_pre_prob.index:
        if idx in full.index:
            full[idx] = etf_pre_prob[idx]
    full = pd.concat([full, hold_prob]).sort_index()
    full = full[~full.index.duplicated(keep="last")]

    return full


# ══════════════════════════════════════════════════════════════════════════════
# METRICS
# ══════════════════════════════════════════════════════════════════════════════

def metrics(ret: pd.Series) -> dict:
    eq = (1+ret).cumprod()*100
    yrs = (ret.index[-1]-ret.index[0]).days/365.25
    c = float((eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1) if yrs > 0 else 0.0
    sh = float(ret.mean()/ret.std()*np.sqrt(12)) if ret.std() > 0 else 0.0
    pk = eq.cummax()
    dd = float(((eq-pk)/pk).min())
    return {"cagr": c, "sharpe": sh, "maxdd": dd, "eq": eq, "ret": ret}


def window_cagr(ret: pd.Series, yrs: int) -> float:
    end   = ret.index[-1]
    start = end - pd.DateOffset(years=yrs)
    sl    = ret.loc[start:]
    if len(sl) < 6: return float("nan")
    eq = (1+sl).cumprod()
    y  = (sl.index[-1]-sl.index[0]).days/365.25
    return float((eq.iloc[-1]/eq.iloc[0])**(1/y)-1) if y > 0 else float("nan")


# ══════════════════════════════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════════════════════════════

def build_report(strats: dict[str, dict], signal: pd.Series,
                 iwd_ret: pd.Series, iwn_ret: pd.Series) -> str:
    # ── equity chart
    fig_eq = go.Figure()
    for name, s in strats.items():
        eq = s["eq"].dropna()
        fig_eq.add_trace(go.Scatter(
            x=eq.index, y=eq,
            name=f"{name}  {s['cagr']:.1%} CAGR",
            line=dict(color=COLORS.get(name,"#aaa"),
                      width=3 if name=="Strategy" else 1.8,
                      dash="solid" if name!="SPY" else "dot")))

    fig_eq.add_vline(x=pd.Timestamp(HOLDOUT).timestamp()*1000,
                     line_dash="dash", line_color="#333",
                     annotation_text="Holdout 2010", annotation_font_size=10)
    fig_eq.update_layout(title="Equity Curves (log scale)",
                         yaxis_type="log",
                         xaxis_title="Date", yaxis_title="$100 start (log)",
                         height=450, **DARK,
                         legend=dict(bgcolor="rgba(0,0,0,0)"))

    # ── signal chart (fraction of time in IWN vs IWD)
    sig_binary = (signal > THRESH).astype(int).reindex(iwd_ret.index).fillna(0)
    fig_sig = go.Figure()
    fig_sig.add_trace(go.Scatter(x=sig_binary.index, y=sig_binary.rolling(12).mean(),
                                  name="12m % months in IWN (small)",
                                  line=dict(color="#00d4ff", width=1.5),
                                  fill="tozeroy", fillcolor="rgba(0,212,255,0.1)"))
    fig_sig.add_hline(y=0.5, line_dash="dot", line_color="#555")
    fig_sig.update_layout(title="SMB Signal — Rolling 12m % Time in Small-Cap (IWN)",
                          yaxis_tickformat=".0%", height=280, **DARK,
                          legend=dict(bgcolor="rgba(0,0,0,0)"))

    # ── window bar chart
    fig_bar = go.Figure()
    wlabels = list(WINDOWS.keys())
    for name, s in strats.items():
        vals = [window_cagr(s["ret"], y) for y in WINDOWS.values()]
        fig_bar.add_trace(go.Bar(
            name=name, x=wlabels, y=vals,
            text=[f"{v:.1%}" if not np.isnan(v) else "—" for v in vals],
            textposition="outside",
            marker_color=COLORS.get(name,"#aaa")))
    fig_bar.add_hline(y=0, line_color="#555", line_width=1)
    fig_bar.update_layout(title="CAGR by Window",
                          yaxis_tickformat=".1%", barmode="group",
                          height=400, **DARK,
                          legend=dict(bgcolor="rgba(0,0,0,0)"))

    # ── table
    hdr = ["Strategy"] + [f"{w}" for w in WINDOWS] + ["Full CAGR","Sharpe","MaxDD"]
    rows = ""
    for name, s in strats.items():
        wvals = [window_cagr(s["ret"], y) for y in WINDOWS.values()]
        tds = f"<td><strong>{name}</strong></td>"
        for v in wvals:
            if np.isnan(v): tds += "<td>—</td>"
            else:
                cls = "pos" if v > 0.05 else ("neg" if v < 0 else "")
                tds += f'<td class="{cls}">{v:.1%}</td>'
        c = s["cagr"]
        tds += f'<td class="{"pos" if c>0.05 else "neg" if c<0 else ""}">{c:.1%}</td>'
        tds += f"<td>{s['sharpe']:.2f}</td>"
        tds += f"<td>{s['maxdd']:.1%}</td>"
        rows += f"<tr>{tds}</tr>"

    pct_iwn = float(sig_binary.mean())
    plots = (fig_eq.to_html(full_html=False, include_plotlyjs=False) +
             fig_sig.to_html(full_html=False, include_plotlyjs=False) +
             fig_bar.to_html(full_html=False, include_plotlyjs=False))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Factor ETF Strategy</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  html,body{{background:#0f1117!important;color:#e0e0e0;font-family:'Inter',sans-serif;margin:0;padding:0}}
  .container{{max-width:1200px;margin:0 auto;padding:24px}}
  h1{{font-size:1.7rem;color:#4ade80;margin-bottom:4px}}
  .subtitle{{color:#888;font-size:.9rem;margin-bottom:28px}}
  .section{{font-size:1.05rem;color:#aaa;margin:28px 0 12px;border-bottom:1px solid #2a2d3a;padding-bottom:6px}}
  .verdict{{background:#1a1d2e;border-left:4px solid #4ade80;padding:16px 20px;border-radius:0 8px 8px 0;margin:20px 0;line-height:1.8}}
  .chart-block{{background:#1a1d2e;border:1px solid #2a2d3a;border-radius:8px;padding:16px;margin-bottom:16px}}
  table{{width:100%;border-collapse:collapse;font-size:.85rem}}
  th{{background:#1a1d2e;color:#888;padding:8px 10px;text-align:right;border-bottom:1px solid #2a2d3a}}
  th:first-child{{text-align:left}}
  td{{padding:8px 10px;border-bottom:1px solid #1e2130;color:#ccc;text-align:right}}
  td:first-child{{text-align:left}}
  tr:hover td{{background:#1a1d2e}}
  .pos{{color:#4ade80;font-weight:600}} .neg{{color:#f87171}}
  .pill{{display:inline-block;padding:2px 10px;border-radius:12px;font-size:.8rem;font-weight:600}}
  .pill-green{{background:#1a3a2a;color:#4ade80}}
  .pill-blue{{background:#0a2a3a;color:#00d4ff}}
</style>
</head>
<body>
<div class="container">
  <h1>Factor ETF Strategy</h1>
  <div class="subtitle">Long-only · One signal · Two ETFs · Full market beta</div>

  <div class="verdict">
    <strong>Strategy</strong><br>
    <span class="pill pill-green">SMB ON</span>&nbsp; Hold <strong>IWN</strong>
      (iShares Russell 2000 Value) — <em>small-cap + value + market</em><br>
    <span class="pill pill-blue">SMB OFF</span>&nbsp; Hold <strong>IWD</strong>
      (iShares Russell 1000 Value) — <em>large-cap + value + market</em><br><br>
    Signal: LR regime model trained on French SMB (1926→2010), deployed on IWM−SPY features (live, 0 lag).<br>
    In <strong>IWN {pct_iwn:.0%}</strong> of months, <strong>IWD {1-pct_iwn:.0%}</strong> of months.
  </div>

  <div class="section">Charts</div>
  <div class="chart-block">{plots}</div>

  <div class="section">Window Table</div>
  <div style="overflow-x:auto">
  <table>
    <tr>{''.join(f'<th>{h}</th>' for h in hdr)}</tr>
    {rows}
  </table>
  </div>

  <div class="section">Notes</div>
  <div class="verdict" style="border-color:#fb923c;font-size:.88rem;color:#bbb">
    • IWN inception May 2000 · IWD inception May 2000 · ETF era = 2000→2026<br>
    • Pre-2000 window uses French factor returns as proxy (not tradeable — shown for model context only)<br>
    • No transaction costs, no slippage<br>
    • Dev: 1926→2010 walk-forward OOF &nbsp;|&nbsp; Holdout: 2010→2026
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
    print("Factor ETF Strategy Backtest")
    print("=" * 60)

    print("\n[1/4] Loading data...")
    ff3 = load_french()

    prices = load_etf_prices(["IWN","IWD","SPY","IWM"])
    ret    = prices.pct_change().dropna()
    iwd_ret = ret["IWD"]
    iwn_ret = ret["IWN"]
    spy_ret = ret["SPY"]
    smb_etf = ret["IWM"] - ret["SPY"]
    print(f"  ETF data: {ret.index[0].strftime('%Y-%m')} → {ret.index[-1].strftime('%Y-%m')} ({len(ret)} months)")

    print("\n[2/4] Building SMB regime signal...")
    signal = build_smb_signal_full(ff3, smb_etf, spy_ret)
    signal_binary = (signal > THRESH).astype(float)
    pct_iwn = signal_binary.reindex(ret.index).fillna(0).mean()
    print(f"  % months in IWN (small): {pct_iwn:.0%}")
    print(f"  % months in IWD (large): {1-pct_iwn:.0%}")

    print("\n[3/4] Computing strategy returns...")
    # Align all to ETF period
    common = iwd_ret.index.intersection(iwn_ret.index).intersection(spy_ret.index)
    sig    = signal_binary.reindex(common).fillna(0)
    iwd_r  = iwd_ret.reindex(common)
    iwn_r  = iwn_ret.reindex(common)
    spy_r  = spy_ret.reindex(common)

    # Strategy: IWN when signal ON, IWD when signal OFF
    strat_r = iwn_r * sig + iwd_r * (1 - sig)

    strats = {
        "Strategy":     metrics(strat_r),
        "IWD Always":   metrics(iwd_r),
        "IWN Always":   metrics(iwn_r),
        "IWD+IWN 50/50":metrics((iwd_r + iwn_r) / 2),
        "SPY":          metrics(spy_r),
    }

    print(f"\n  {'Strategy':<18}", end="")
    for w in WINDOWS: print(f"  {w:>7}", end="")
    print(f"  {'Full':>7}  {'Sharpe':>7}  {'MaxDD':>8}")
    print("  " + "-"*72)
    for name, s in strats.items():
        print(f"  {name:<18}", end="")
        for y in WINDOWS.values():
            v = window_cagr(s["ret"], y)
            print(f"  {v:>6.1%}" if not np.isnan(v) else f"  {'—':>6}", end="")
        print(f"  {s['cagr']:>6.1%}  {s['sharpe']:>7.2f}  {s['maxdd']:>7.1%}")

    print("\n[4/4] Building report...")
    html = build_report(strats, signal, iwd_ret, iwn_ret)
    with open(OUT_HTML, "w") as f:
        f.write(html)
    print(f"  Wrote {OUT_HTML}")


if __name__ == "__main__":
    main()
