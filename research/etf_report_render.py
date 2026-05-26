"""
ETF portfolio comparison report — dark mode.

Fetches price history for the user's UCITS holdings + long-history US proxies,
computes performance across multiple windows, and renders a tearsheet HTML.

Run from host:
    python3 research/etf_report_render.py
"""
from __future__ import annotations
import math, os, sys
import pandas as pd
import numpy as np
import yfinance as yf

OUT_PATH = os.path.join(os.path.dirname(__file__), "etf_report.html")

# ── ETF definitions ────────────────────────────────────────────────────────────

HOLDINGS = {
    "ZPRX": ("ZPRX.DE", "US Small Cap Value",        "your ETF"),
    "ZPRV": ("ZPRV.DE", "Europe Small Cap Value",     "your ETF"),
    "AVWS": ("AVWS.DE", "Intl Small Cap Value",       "your ETF (Avantis)"),
    "JPGL": ("JPGL.L",  "Global Multi-Factor",        "your ETF"),
    "VWCE": ("VWCE.DE", "All-World",                  "your benchmark"),
}

PROXIES = {
    "IWN":  ("IWN",   "US SC Value (Russell 2k)",    "25yr proxy for ZPRX"),
    "IJS":  ("IJS",   "US SC Value (S&P 600)",        "25yr proxy for ZPRX"),
    "VBR":  ("VBR",   "US SC Value (Vanguard)",       "22yr proxy for ZPRX"),
    "DLS":  ("DLS",   "Intl SC Dividend",             "20yr proxy for ZPRV/AVWS"),
    "AVDV": ("AVDV",  "Intl SC Value (Avantis US)",   "same mgr as AVWS"),
    "EFV":  ("EFV",   "EAFE Value",                   "21yr intl value proxy"),
    "VT":   ("VT",    "Total World",                  "global benchmark"),
    "SPY":  ("SPY",   "S&P 500",                      "US benchmark"),
}

WINDOWS = [
    ("25yr", "2000-08-01"),
    ("20yr", "2005-08-01"),
    ("15yr", "2010-08-01"),
    ("10yr", "2015-08-01"),
    ("5yr",  "2021-05-01"),
    ("3yr",  "2023-05-01"),
    ("1yr",  "2025-05-01"),
]

# ── data fetch ────────────────────────────────────────────────────────────────

def fetch_all():
    all_etfs = {**HOLDINGS, **PROXIES}
    data = {}
    print("Fetching price history…")
    for key, (ticker, desc, note) in all_etfs.items():
        try:
            hist = yf.Ticker(ticker).history(period="max")
            if len(hist) < 20:
                print(f"  {key}: no data")
                continue
            s = hist["Close"].copy()
            s.index = pd.to_datetime(
                s.index.tz_localize(None) if s.index.tz else s.index
            )
            s = s.dropna().sort_index()
            data[key] = s
            print(f"  {key}: {s.index[0].date()} → {s.index[-1].date()} ({len(s)} rows)")
        except Exception as e:
            print(f"  {key}: ERROR {e}")
    return data

# ── metrics ───────────────────────────────────────────────────────────────────

def compute(s: pd.Series, bench: pd.Series | None = None):
    s = s.dropna()
    if len(s) < 20:
        return None
    years = (s.index[-1] - s.index[0]).days / 365.25
    total = s.iloc[-1] / s.iloc[0] - 1
    cagr  = (1 + total) ** (1 / years) - 1 if years > 0.1 else float("nan")
    rets  = s.pct_change().dropna()
    sharpe = float(rets.mean() / rets.std() * math.sqrt(252)) if rets.std() > 0 else 0
    neg = rets[rets < 0]
    sortino = float(rets.mean() / neg.std() * math.sqrt(252)) if len(neg) > 0 and neg.std() > 0 else 0
    maxdd  = float(((s - s.cummax()) / s.cummax()).min())
    vol    = float(rets.std() * math.sqrt(252))
    alpha, beta = float("nan"), float("nan")
    if bench is not None:
        br = bench.pct_change().dropna()
        common = rets.index.intersection(br.index)
        if len(common) > 30:
            p = rets.reindex(common).values
            b = br.reindex(common).values
            cov = np.cov(p, b)
            beta = float(cov[0, 1] / cov[1, 1]) if cov[1, 1] > 0 else float("nan")
            alpha = float((np.mean(p) - beta * np.mean(b)) * 252)
    return dict(
        cagr=round(cagr, 4), total=round(total, 4),
        sharpe=round(sharpe, 3), sortino=round(sortino, 3),
        maxdd=round(maxdd, 4), vol=round(vol, 4),
        alpha=round(alpha, 4) if math.isfinite(alpha) else None,
        beta=round(beta, 3) if math.isfinite(beta) else None,
        years=round(years, 1),
    )

# ── HTML helpers ──────────────────────────────────────────────────────────────

def _cls_cagr(v):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "dim"
    return "green" if v >= 0.12 else ("yellow" if v >= 0.07 else "red")

def _cls_sh(v):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "dim"
    return "green" if v >= 1.0 else ("yellow" if v >= 0.6 else "red")

def _cls_dd(v):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "dim"
    return "green" if v >= -0.20 else ("yellow" if v >= -0.35 else "red")

def _cls_alpha(v):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "dim"
    return "green" if v > 0.01 else ("yellow" if v >= 0 else "red")

def _p(v, d=1):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "—"
    return f"{v*100:.{d}f}%"

def _n(v, d=2):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "—"
    return f"{v:.{d}f}"

# ── build HTML ────────────────────────────────────────────────────────────────

def build_html(data: dict) -> str:

    all_etfs = {**HOLDINGS, **PROXIES}

    # ── per-window tables ─────────────────────────────────────────────────────
    def window_table(label, start_str):
        start = pd.Timestamp(start_str)
        bench_key = "VT"
        bench_s = data.get(bench_key)

        rows = []
        groups = [("Your holdings", HOLDINGS), ("Long-history proxies", PROXIES)]
        for group_label, group in groups:
            group_rows = []
            for key, (ticker, desc, note) in group.items():
                s = data.get(key)
                if s is None:
                    continue
                sub = s[s.index >= start]
                if len(sub) < 60:
                    continue
                bench_sub = bench_s[bench_s.index >= start] if bench_s is not None else None
                if bench_sub is not None:
                    bench_sub = bench_sub.reindex(sub.index, method="ffill")
                m = compute(sub, bench_sub)
                if m is None:
                    continue
                is_bench = (key in ("VWCE", "VT", "SPY"))
                group_rows.append((key, desc, note, m, is_bench))

            if group_rows:
                rows.append(("group", group_label))
                # Sort: benchmarks last, then by CAGR desc
                group_rows.sort(key=lambda x: (x[4], -(x[3]["cagr"] or -99)))
                rows.extend(group_rows)

        if not any(r[0] != "group" for r in rows):
            return f'<p class="dim" style="padding:12px">No data for {label} window</p>'

        html = f"""
        <div class="window-section">
          <div class="window-label">{label}</div>
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th class="left">ETF</th>
                <th class="left">Strategy</th>
                <th>CAGR</th>
                <th>Sharpe</th>
                <th>MaxDD</th>
                <th>Alpha</th>
                <th>Beta</th>
                <th>Vol</th>
                <th>Total</th>
                <th>Yrs</th>
              </tr></thead>
              <tbody>"""

        for row in rows:
            if row[0] == "group":
                html += f'<tr class="group-header"><td colspan="10">{row[1]}</td></tr>'
                continue
            key, desc, note, m, is_bench = row
            rc = "bench-row" if is_bench else ""
            icon = "◄ " if key in ("VWCE", "VT") else ""
            html += f"""
                <tr class="{rc}">
                  <td class="left mono">{key}</td>
                  <td class="left desc">{icon}{desc} <span class="note">{note}</span></td>
                  <td class="{_cls_cagr(m['cagr'])}">{_p(m['cagr'])}</td>
                  <td class="{_cls_sh(m['sharpe'])}">{_n(m['sharpe'])}</td>
                  <td class="{_cls_dd(m['maxdd'])}">{_p(m['maxdd'])}</td>
                  <td class="{_cls_alpha(m['alpha'])}">{_p(m['alpha'])}</td>
                  <td class="dim">{_n(m['beta'])}</td>
                  <td class="dim">{_p(m['vol'])}</td>
                  <td class="dim">{_p(m['total'],0)}</td>
                  <td class="dim">{_n(m['years'],1)}</td>
                </tr>"""

        html += "</tbody></table></div></div>"
        return html

    windows_html = ""
    for label, start in WINDOWS:
        windows_html += window_table(label, start)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ETF Portfolio Analysis</title>
<style>
html,body{{background:#0f1117!important;color:#e2e8f0;font-family:'Inter',system-ui,sans-serif;margin:0;padding:0}}
.container{{max-width:1200px;margin:0 auto;padding:32px 20px 64px}}
h1{{font-size:1.5rem;font-weight:700;color:#f1f5f9;margin:0 0 4px}}
.subtitle{{color:#64748b;font-size:.83rem;margin-bottom:32px}}
.subtitle b{{color:#94a3b8}}

.window-section{{margin-bottom:36px}}
.window-label{{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;
  color:#475569;margin-bottom:8px;padding:4px 0;border-bottom:1px solid #1e2535}}
.table-wrap{{overflow-x:auto;border:1px solid #1e2535;border-radius:8px}}
table{{width:100%;border-collapse:collapse;font-size:.82rem}}
thead th{{background:#141824;color:#64748b;font-size:.68rem;text-transform:uppercase;
  letter-spacing:.06em;padding:9px 12px;white-space:nowrap;border-bottom:1px solid #1e2535}}
th.left{{text-align:left}}
tbody tr{{border-bottom:1px solid #161b27;transition:background .12s}}
tbody tr:hover{{background:#1a1f2e}}
tbody tr:last-child{{border-bottom:none}}
td{{padding:9px 12px;text-align:right;font-variant-numeric:tabular-nums}}
td.left{{text-align:left}}
td.mono{{font-family:monospace;font-size:.8rem;color:#cbd5e1;font-weight:600;white-space:nowrap}}
td.desc{{color:#94a3b8;white-space:nowrap}}
td.desc .note{{font-size:.72rem;color:#475569}}
tr.bench-row td{{color:#64748b;font-style:italic}}
tr.bench-row td.mono{{color:#64748b}}
tr.group-header td{{background:#111827;color:#475569;font-size:.68rem;font-weight:700;
  text-transform:uppercase;letter-spacing:.08em;padding:6px 12px;text-align:left}}

.green{{color:#4ade80}}
.yellow{{color:#facc15}}
.red{{color:#f87171}}
.dim{{color:#64748b}}

.legend{{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:24px;font-size:.75rem}}
.leg{{display:flex;align-items:center;gap:6px;color:#64748b}}
.dot{{width:8px;height:8px;border-radius:50%}}
.dot.green{{background:#4ade80}}.dot.yellow{{background:#facc15}}.dot.red{{background:#f87171}}

.caveat{{background:#1a1f2e;border:1px solid #2d3748;border-radius:8px;padding:16px 20px;
  margin-bottom:28px;font-size:.8rem;color:#94a3b8;line-height:1.6}}
.caveat strong{{color:#cbd5e1}}
.footer{{margin-top:32px;color:#334155;font-size:.72rem;text-align:center}}
</style>
</head>
<body>
<div class="container">
  <h1>ETF Portfolio Analysis</h1>
  <div class="subtitle">
    Holdings: <b>ZPRX · ZPRV · AVWS · JPGL · VWCE</b> &nbsp;·&nbsp;
    Benchmark: <b>VT</b> (global) &nbsp;·&nbsp;
    Alpha/Beta vs <b>VT</b>
  </div>

  <div class="caveat">
    <strong>Currency note:</strong> Your UCITS ETFs trade in EUR/GBP. US proxies (IWN, VBR, DLS…) trade in USD.
    Returns are not currency-adjusted — EUR-hedged performance may differ slightly.
    <br><strong>Proxy note:</strong> IWN/IJS/VBR are US-listed small cap value with the same factor exposure as ZPRX.
    DLS/AVDV are best available proxies for ZPRV/AVWS.
    Use these for the long-window picture; your UCITS ETFs for recent accuracy.
  </div>

  <div class="legend">
    <div class="leg"><div class="dot green"></div> Strong (CAGR≥12%, Sh≥1.0, DD≥-20%)</div>
    <div class="leg"><div class="dot yellow"></div> Moderate</div>
    <div class="leg"><div class="dot red"></div> Weak</div>
  </div>

  {windows_html}

  <div class="footer">Data: yfinance · Alpha/Beta vs VT (Vanguard Total World) · Not investment advice</div>
</div>
</body>
</html>"""


def main():
    data = fetch_all()
    html = build_html(data)
    with open(OUT_PATH, "w") as f:
        f.write(html)
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
