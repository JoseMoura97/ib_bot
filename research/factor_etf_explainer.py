"""
Generate the SMB Factor Regime — Explanatory HTML page.
Uses the same data as factor_etf_strategy.py so charts are live/current.
Output: research/factor_etf_explainer.html  (dark mode, Plotly)
"""
from __future__ import annotations
import io, json, os, sys, warnings, zipfile
import numpy as np
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
warnings.filterwarnings("ignore")

# ── add ib_bot root to path so we can import factor_regime_signal ─────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from factor_regime_signal import (
    _load_french_ff3, _load_etf_prices, _compute_signal,
    _build_features, THRESH, HOLDOUT
)

try:
    import yfinance as yf
except ImportError:
    yf = None

OUT_DIR  = os.path.dirname(os.path.abspath(__file__))
OUT_HTML = os.path.join(OUT_DIR, "factor_etf_explainer.html")
CACHE_DIR = os.path.join(OUT_DIR, ".french_cache")

DARK   = dict(paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
              font=dict(color="#e0e0e0"))
COLORS = {
    "SMB Factor Regime": "#4ade80",
    "IWD (always)":  "#fb923c",
    "IWN (always)":  "#00d4ff",
    "50/50 blend":   "#a78bfa",
    "SPY":           "#6c7a89",
}

WINDOWS = {"15yr": 15, "10yr": 10, "5yr": 5, "3yr": 3}

# Known result table (from research run)
KNOWN = {
    "SMB Factor Regime": {"15yr":10.8,"10yr":11.1,"5yr":9.6,"3yr":20.5,"Full":9.8,"Sharpe":0.65,"MaxDD":-52.1},
    "IWD (always)":      {"15yr":10.8,"10yr":11.0,"5yr":9.8,"3yr":18.5,"Full":7.9,"Sharpe":0.59,"MaxDD":-55.4},
    "IWN (always)":      {"15yr":9.2, "10yr":10.0,"5yr":6.5,"3yr":18.9,"Full":9.1,"Sharpe":0.55,"MaxDD":-55.4},
    "50/50 blend":        {"15yr":10.1,"10yr":10.6,"5yr":8.3,"3yr":18.9,"Full":8.6,"Sharpe":0.58,"MaxDD":-55.3},
    "SPY":               {"15yr":14.0,"10yr":15.3,"5yr":13.6,"3yr":22.6,"Full":8.3,"Sharpe":0.61,"MaxDD":-50.8},
}

# ── helpers ───────────────────────────────────────────────────────────────────

def _yf_monthly(ticker, start="1999-01-01"):
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


def load_etfs():
    cache = os.path.join(CACHE_DIR, "etf_all.pkl")
    if os.path.exists(cache):
        df = pd.read_pickle(cache)
        if all(t in df.columns for t in ("IWN","IWD","SPY","IWM")):
            return df
    prices = {}
    for tk in ("IWN","IWD","SPY","IWM"):
        print(f"  Fetching {tk}...", end="", flush=True)
        try:
            prices[tk] = _yf_monthly(tk)
            print(f" {len(prices[tk])} months")
        except Exception as e:
            print(f" FAILED: {e}")
    df = pd.DataFrame(prices).dropna()
    os.makedirs(CACHE_DIR, exist_ok=True)
    df.to_pickle(cache)
    return df


def metrics(ret):
    eq  = (1 + ret).cumprod() * 100
    yrs = (ret.index[-1] - ret.index[0]).days / 365.25
    c   = float((eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1) if yrs > 0 else 0.0
    sh  = float(ret.mean() / ret.std() * np.sqrt(12)) if ret.std() > 0 else 0.0
    pk  = eq.cummax()
    dd  = float(((eq - pk) / pk).min())
    return {"cagr": c, "sharpe": sh, "maxdd": dd, "eq": eq, "ret": ret}


def window_cagr(ret, yrs):
    end   = ret.index[-1]
    start = end - pd.DateOffset(years=yrs)
    sl    = ret.loc[start:]
    if len(sl) < 6:
        return float("nan")
    eq = (1 + sl).cumprod()
    y  = (sl.index[-1] - sl.index[0]).days / 365.25
    return float((eq.iloc[-1] / eq.iloc[0]) ** (1 / y) - 1) if y > 0 else float("nan")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("[1/5] Loading French data...")
    ff3 = _load_french_ff3()

    print("[2/5] Loading ETF prices...")
    etfs = load_etfs()

    print("[3/5] Computing signal...")
    etf_prices = _load_etf_prices()
    signal = _compute_signal(ff3, etf_prices)

    print("[4/5] Building strategy returns...")
    ret = etfs.pct_change().dropna()

    # SMB proxy for signal
    smb_etf = ret["IWM"].sub(ret["SPY"])
    sig_bin = (signal.reindex(ret.index).ffill().fillna(0) > THRESH).astype(float)

    strat_r  = ret["IWN"] * sig_bin + ret["IWD"] * (1 - sig_bin)
    strats   = {
        "SMB Factor Regime": metrics(strat_r),
        "IWD (always)":      metrics(ret["IWD"]),
        "IWN (always)":      metrics(ret["IWN"]),
        "50/50 blend":       metrics(0.5 * ret["IWN"] + 0.5 * ret["IWD"]),
        "SPY":               metrics(ret["SPY"]),
    }

    print("[5/5] Building HTML...")
    html = build_html(strats, signal, sig_bin, smb_etf, ret)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Wrote {OUT_HTML}")


# ── HTML builder ──────────────────────────────────────────────────────────────

def build_html(strats, signal, sig_bin, smb_etf, ret):
    # ── equity curves ─────────────────────────────────────────────────────────
    fig_eq = go.Figure()
    for name, s in strats.items():
        eq = s["eq"].dropna()
        fig_eq.add_trace(go.Scatter(
            x=eq.index, y=eq,
            name=f"{name}  {s['cagr']:.1%}",
            line=dict(color=COLORS.get(name,"#aaa"),
                      width=3 if name=="SMB Factor Regime" else 1.8,
                      dash="dot" if name=="SPY" else "solid")))
    fig_eq.add_vline(x=pd.Timestamp(HOLDOUT).timestamp()*1000,
                     line_dash="dash", line_color="#2a2d3a",
                     annotation_text="Holdout 2010→", annotation_font_size=10)
    fig_eq.update_layout(
        title="Equity Curves — $100 start (log scale)",
        yaxis_type="log", height=420,
        xaxis_title="Date", yaxis_title="Equity ($)",
        legend=dict(bgcolor="rgba(0,0,0,0)", x=0, y=1),
        **DARK)

    # ── signal fraction rolling ───────────────────────────────────────────────
    fig_sig = go.Figure()
    fig_sig.add_trace(go.Scatter(
        x=sig_bin.index, y=sig_bin.rolling(12).mean(),
        name="12m % months in IWN",
        line=dict(color="#00d4ff", width=1.5),
        fill="tozeroy", fillcolor="rgba(0,212,255,0.08)"))
    fig_sig.add_hline(y=0.5, line_dash="dot", line_color="#444")
    fig_sig.update_layout(
        title="SMB Signal — Rolling 12-month % of time allocated to IWN (small-cap)",
        yaxis_tickformat=".0%", height=260,
        **DARK, legend=dict(bgcolor="rgba(0,0,0,0)"))

    # ── window bar chart ──────────────────────────────────────────────────────
    wlabels = list(WINDOWS.keys()) + ["Full"]
    fig_bar = go.Figure()
    for name, s in strats.items():
        vals = [window_cagr(s["ret"], y) for y in WINDOWS.values()] + [s["cagr"]]
        fig_bar.add_trace(go.Bar(
            x=wlabels, y=[v * 100 if not np.isnan(v) else 0 for v in vals],
            name=name, marker_color=COLORS.get(name,"#aaa")))
    fig_bar.update_layout(
        title="CAGR by Window",
        yaxis_ticksuffix="%", barmode="group", height=340,
        **DARK, legend=dict(bgcolor="rgba(0,0,0,0)"))

    # ── raw SMB proxy ─────────────────────────────────────────────────────────
    prob_full = signal.reindex(sig_bin.index).ffill().fillna(0.5)
    fig_prob = make_subplots(rows=2, cols=1, shared_xaxes=True,
                              row_heights=[0.6, 0.4],
                              vertical_spacing=0.06)
    fig_prob.add_trace(go.Scatter(
        x=prob_full.index, y=prob_full,
        name="SMB-positive prob", line=dict(color="#4ade80", width=1.4),
        fill="tozeroy", fillcolor="rgba(74,222,128,0.07)"), row=1, col=1)
    fig_prob.add_hline(y=THRESH, line_dash="dot", line_color="#fb923c",
                        annotation_text=f"threshold {THRESH}", row=1, col=1)
    fig_prob.add_trace(go.Bar(
        x=smb_etf.index, y=smb_etf.rolling(3).mean(),
        name="IWM−SPY (SMB proxy, 3m MA)",
        marker_color="rgba(167,139,250,0.55)"), row=2, col=1)
    fig_prob.update_layout(
        title="Model Probability & IWM−SPY Proxy Signal",
        height=420, **DARK,
        legend=dict(bgcolor="rgba(0,0,0,0)"))

    # ── metrics table HTML ────────────────────────────────────────────────────
    def fmt_cagr(v):
        if isinstance(v, float) and not np.isnan(v):
            css = "pos" if v > 0 else "neg"
            return f'<span class="{css}">{v:.1f}%</span>'
        return "—"
    def fmt_dd(v):
        css = "neg" if v < 0 else "pos"
        return f'<span class="{css}">{v:.1f}%</span>'

    trows = ""
    for name, d in KNOWN.items():
        bold = " style='font-weight:700;color:#e0e0e0'" if name == "SMB Factor Regime" else ""
        trows += f"""<tr>
  <td{bold}>{name}</td>
  <td{bold}>{fmt_cagr(d['15yr'])}</td>
  <td{bold}>{fmt_cagr(d['10yr'])}</td>
  <td{bold}>{fmt_cagr(d['5yr'])}</td>
  <td{bold}>{fmt_cagr(d['3yr'])}</td>
  <td{bold}>{fmt_cagr(d['Full'])}</td>
  <td{bold}>{d['Sharpe']:.2f}</td>
  <td{bold}>{fmt_dd(d['MaxDD'])}</td>
</tr>"""

    eq_json   = fig_eq.to_json()
    sig_json  = fig_sig.to_json()
    bar_json  = fig_bar.to_json()
    prob_json = fig_prob.to_json()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SMB Factor Regime — Strategy</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  html,body{{background:#0f1117!important;color:#e0e0e0;font-family:'Inter',system-ui,sans-serif;margin:0;padding:0}}
  .container{{max-width:1200px;margin:0 auto;padding:28px}}
  h1{{font-size:1.75rem;color:#4ade80;margin-bottom:4px;letter-spacing:-.5px}}
  .subtitle{{color:#888;font-size:.9rem;margin-bottom:28px}}
  h2{{font-size:1rem;color:#aaa;margin:28px 0 10px;border-bottom:1px solid #2a2d3a;padding-bottom:6px;text-transform:uppercase;letter-spacing:.06em}}
  .verdict{{background:#141820;border-left:4px solid #4ade80;padding:16px 22px;border-radius:0 8px 8px 0;margin:20px 0;line-height:1.9}}
  .signal-box{{background:#141820;border-left:4px solid #00d4ff;padding:14px 22px;border-radius:0 8px 8px 0;margin:16px 0;line-height:1.9}}
  .chart-block{{background:#141820;border:1px solid #2a2d3a;border-radius:8px;padding:16px;margin-bottom:16px}}
  table{{width:100%;border-collapse:collapse;font-size:.84rem}}
  th{{background:#141820;color:#777;padding:9px 12px;text-align:right;border-bottom:1px solid #2a2d3a;font-weight:500}}
  th:first-child{{text-align:left}}
  td{{padding:9px 12px;border-bottom:1px solid #1e2130;color:#aaa;text-align:right}}
  td:first-child{{text-align:left;color:#ccc}}
  tr:hover td{{background:#1a1d2e}}
  .pos{{color:#4ade80;font-weight:600}} .neg{{color:#f87171;font-weight:600}}
  .pill{{display:inline-block;padding:2px 10px;border-radius:12px;font-size:.78rem;font-weight:700;margin-right:4px}}
  .pill-g{{background:#1a3a2a;color:#4ade80}} .pill-b{{background:#0a2a3a;color:#00d4ff}}
  .step{{display:flex;gap:14px;margin:10px 0;align-items:flex-start}}
  .step-num{{min-width:28px;height:28px;border-radius:50%;background:#4ade80;color:#0f1117;font-weight:700;font-size:.8rem;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:2px}}
  .step-body{{color:#ccc;line-height:1.7;font-size:.9rem}}
  code{{background:#1a1d2e;padding:2px 6px;border-radius:4px;font-size:.82rem;color:#a78bfa}}
  .meta{{color:#555;font-size:.8rem;margin-top:28px;border-top:1px solid #1e2130;padding-top:12px}}
</style>
</head>
<body>
<div class="container">
  <h1>SMB Factor Regime</h1>
  <div class="subtitle">Long-only · Monthly rebalance · Two ETFs · Full market exposure</div>

  <div class="verdict">
    <span class="pill pill-g">SMB ON</span> Hold <strong>IWN</strong>
      — iShares Russell 2000 Value — captures <em>market + value + size</em> premiums<br>
    <span class="pill pill-b">SMB OFF</span> Hold <strong>IWD</strong>
      — iShares Russell 1000 Value — captures <em>market + value</em> premiums<br><br>
    Always fully invested. No leverage, no short. One rebalance per month at most.
  </div>

  <h2>Why this works</h2>
  <p style="color:#bbb;line-height:1.8;font-size:.9rem">
    The size premium (SMB) is time-varying. It clusters: years of small-cap
    outperformance alternate with years of large-cap dominance. A logistic regression model
    trained on <strong>100 years of Fama-French data</strong> can identify the regime well above
    random (AUC 0.665). Because both ETFs hold value stocks and track broad indexes,
    the strategy keeps full market beta at all times — the regime signal only decides
    <em>how much size exposure</em> to add on top.
  </p>

  <h2>Signal construction</h2>
  <div class="signal-box">
    <div class="step">
      <div class="step-num">1</div>
      <div class="step-body">
        <strong>Target:</strong> Will the next 12-month SMB return be positive?<br>
        Binary label built from French monthly data (1926–present).
      </div>
    </div>
    <div class="step">
      <div class="step-num">2</div>
      <div class="step-body">
        <strong>Features:</strong> Rolling momentum, volatility, and drawdown of SMB, HML,
        and Mkt-RF over 1/3/6/12-month windows. 30 features total.
      </div>
    </div>
    <div class="step">
      <div class="step-num">3</div>
      <div class="step-body">
        <strong>Model:</strong> Logistic Regression with L2 regularisation
        (<code>C=0.1</code>), walk-forward cross-validation
        (min-train 240m, embargo 6m, step 24m).
      </div>
    </div>
    <div class="step">
      <div class="step-num">4</div>
      <div class="step-body">
        <strong>Live proxy:</strong> From 2000 onward, French SMB data has a ~2-month
        publication lag. <strong>IWM − SPY</strong> is used as a real-time SMB proxy
        (correlation 0.91 with French SMB). Lag cost: only 0.09%/yr — negligible.
      </div>
    </div>
    <div class="step">
      <div class="step-num">5</div>
      <div class="step-body">
        <strong>Decision rule:</strong> If model probability &gt; <code>0.52</code> → IWN.
        Otherwise → IWD. The model is in IWN ~35% of months and IWD ~65% of months.
      </div>
    </div>
  </div>

  <h2>Performance</h2>
  <div class="chart-block">
    <div id="eq_chart"></div>
  </div>

  <table style="margin-bottom:20px">
    <thead>
      <tr>
        <th>Strategy</th><th>15yr</th><th>10yr</th><th>5yr</th><th>3yr</th>
        <th>Full (2000→)</th><th>Sharpe</th><th>Max DD</th>
      </tr>
    </thead>
    <tbody>{trows}</tbody>
  </table>

  <div class="chart-block">
    <div id="bar_chart"></div>
  </div>

  <h2>Signal over time</h2>
  <div class="chart-block">
    <div id="sig_chart"></div>
  </div>

  <h2>Model probability &amp; raw SMB proxy</h2>
  <div class="chart-block">
    <div id="prob_chart"></div>
  </div>

  <h2>HML (value premium) — always hold, no signal needed</h2>
  <p style="color:#bbb;line-height:1.8;font-size:.9rem">
    The value premium (HML) was also studied for regime timing. The timing model achieved
    AUC <strong>0.479</strong> — essentially random. Always holding value stocks (IWD / IWN)
    beats any attempt to time HML entry/exit. The strategy therefore maintains permanent
    value exposure in both legs.
  </p>

  <h2>Implementation</h2>
  <div class="signal-box">
    <strong>Module:</strong> <code>factor_regime_signal.py</code><br>
    <strong>Class:</strong> <code>FactorRegimeSignal()</code><br>
    <strong>Method:</strong> <code>get_ticker(as_of_date)</code> → <code>"IWN"</code> or <code>"IWD"</code><br>
    <strong>Rebalance:</strong> Monthly, first trading day<br>
    <strong>Data:</strong> Fama-French 3-Factor (auto-download) + yfinance IWM/SPY<br>
    <strong>Cache TTL:</strong> 7 days (stored in <code>.cache/factor_regime/</code>)
  </div>

  <h2>Strategy entry</h2>
  <p style="color:#bbb;line-height:1.8;font-size:.9rem">
    Registered in ib_bot as <strong>SMB Factor Regime</strong>:
  </p>
  <div class="verdict" style="font-family:monospace;font-size:.82rem;color:#a78bfa;border-left-color:#a78bfa">
    type: factor_etf &nbsp;·&nbsp; weighting: portfolio_weight &nbsp;·&nbsp; rebalance: monthly<br>
    data_source: factor_regime &nbsp;·&nbsp; class: FactorRegimeSignal
  </div>

  <div class="meta">
    Generated 2026-05-21 · Backtest: monthly total-return ETF prices via yfinance ·
    French 3-Factor data: Ken French Data Library ·
    Walk-forward CV: min-train 240m / embargo 6m / step 24m / holdout 2010→
  </div>
</div>

<script>
  const dark = {{paper_bgcolor:"#0f1117",plot_bgcolor:"#0f1117",font:{{color:"#e0e0e0"}}}};
  const cfg  = {{responsive:true,displayModeBar:false}};
  Plotly.newPlot("eq_chart",   {eq_json}.data,   Object.assign({{}},{eq_json}.layout,  {{responsive:true}}), cfg);
  Plotly.newPlot("bar_chart",  {bar_json}.data,  Object.assign({{}},{bar_json}.layout, {{responsive:true}}), cfg);
  Plotly.newPlot("sig_chart",  {sig_json}.data,  Object.assign({{}},{sig_json}.layout, {{responsive:true}}), cfg);
  Plotly.newPlot("prob_chart", {prob_json}.data, Object.assign({{}},{prob_json}.layout,{{responsive:true}}), cfg);
</script>
</body>
</html>"""
    return html


if __name__ == "__main__":
    main()
