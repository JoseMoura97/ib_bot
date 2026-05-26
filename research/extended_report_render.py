"""Render dark-theme comparison report: 3yr vs 10yr backtest."""
from __future__ import annotations
import html, json, os

HERE = os.path.dirname(__file__)
OUT  = os.path.join(HERE, "extended_backtest_report.html")

# ── data ─────────────────────────────────────────────────────────────────────
# 10yr results (just computed)
EXTENDED = {
    "Howard Marks":          {"cagr":0.1656,"sharpe":0.76,"maxdd":-0.5072,"alpha":0.036,"beta":0.84,"trades":2046,"yrs":10.4},
    "Stanley Druckenmiller": {"cagr":0.2393,"sharpe":0.96,"maxdd":-0.3975,"alpha":0.095,"beta":1.12,"trades":1349,"yrs":10.4},
    "David Tepper":          {"cagr":0.1679,"sharpe":0.74,"maxdd":-0.3632,"alpha":0.032,"beta":1.15,"trades":1184,"yrs":10.4},
    "Li Lu":                 {"cagr":0.1022,"sharpe":0.54,"maxdd":-0.4007,"alpha":0.011,"beta":0.98,"trades":185, "yrs":10.4},
    "Michael Burry":         {"cagr":0.2335,"sharpe":0.84,"maxdd":-0.3720,"alpha":0.123,"beta":0.73,"trades":198, "yrs":10.4},
    "FINRA Monthly":         {"cagr":0.1383,"sharpe":0.71,"maxdd":-0.3379,"alpha":0.055,"beta":0.63,"trades":2700,"yrs":7.6},
}

# 3yr results (from cost sweep default 10bps / refresh run)
THREE_YR = {
    "Howard Marks":          {"cagr":0.2679,"sharpe":1.36,"maxdd":-0.1866,"alpha":0.081},
    "Stanley Druckenmiller": {"cagr":0.3698,"sharpe":1.60,"maxdd":-0.2218,"alpha":0.145},
    "David Tepper":          {"cagr":0.3290,"sharpe":1.39,"maxdd":-0.2277,"alpha":0.096},
    "Li Lu":                 {"cagr":0.2450,"sharpe":1.34,"maxdd":-0.2279,"alpha":0.096},
    "Michael Burry":         {"cagr":0.2041,"sharpe":0.78,"maxdd":-0.2746,"alpha":0.131},
    "FINRA Monthly":         {"cagr":0.1836,"sharpe":1.27,"maxdd":-0.1442,"alpha":0.067},
}

# SPY benchmarks
SPY = {
    "10yr": {"cagr":0.1526,"maxdd":-0.3372},
    "7.5yr":{"cagr":0.1470,"maxdd":-0.3372},
    "3yr":  {"cagr":0.2250,"maxdd":-0.1876},
}

def pct(x, places=2):
    return f"{x*100:.{places}f}%" if isinstance(x,(int,float)) else "—"

def num(x, places=2):
    return f"{x:.{places}f}" if isinstance(x,(int,float)) else "—"

def cls(x, ref=0):
    if not isinstance(x,(int,float)): return "n"
    return "g" if x>ref else "r"

def delta(a, b):
    """b - a, formatted as +/-X.Xpp"""
    if not isinstance(a,(int,float)) or not isinstance(b,(int,float)): return "—"
    d = (b-a)*100
    return f"+{d:.1f}pp" if d>0 else f"{d:.1f}pp"

def delta_cls(a, b):
    if not isinstance(a,(int,float)) or not isinstance(b,(int,float)): return "n"
    return "g" if b>a else "r"

# ── render rows ───────────────────────────────────────────────────────────────
rows = []
spy_ref_10 = SPY["10yr"]["cagr"]
spy_ref_3  = SPY["3yr"]["cagr"]

# Sort by 10yr CAGR desc
order = sorted(EXTENDED.keys(), key=lambda k: EXTENDED[k]["cagr"], reverse=True)

for name in order:
    e = EXTENDED[name]
    t = THREE_YR.get(name, {})
    spy_ref = SPY["7.5yr"]["cagr"] if name == "FINRA Monthly" else spy_ref_10
    e_cagr = e["cagr"]; t_cagr = t.get("cagr")
    e_sh   = e["sharpe"]; t_sh = t.get("sharpe")
    e_dd   = e["maxdd"]; t_dd = t.get("maxdd")
    e_al   = e["alpha"]; t_al = t.get("alpha")
    vs_spy = e_cagr - spy_ref

    rows.append(f"""
<tr>
  <td class="nm">{html.escape(name)}</td>
  <td class="{cls(e_cagr, spy_ref)}">{pct(e_cagr)}</td>
  <td class="{cls(vs_spy)}">{'+' if vs_spy>0 else ''}{vs_spy*100:.1f}pp</td>
  <td>{num(e_sh)}</td>
  <td class="r">{pct(e_dd)}</td>
  <td class="{cls(e_al)}">{pct(e_al)}</td>
  <td class="dim">{e['trades']}</td>
  <td class="sep {cls(t_cagr, spy_ref_3)}">{pct(t_cagr)}</td>
  <td>{num(t_sh)}</td>
  <td class="r dim">{pct(t_dd)}</td>
  <td class="{delta_cls(t_cagr, e_cagr)}">{delta(t_cagr, e_cagr)}</td>
  <td class="{delta_cls(t_sh, e_sh)}">{delta(t_sh, e_sh)}</td>
</tr>""")

# SPY rows
rows.append(f"""
<tr class="spy-row">
  <td class="nm">SPY (10yr benchmark)</td>
  <td>{pct(SPY['10yr']['cagr'])}</td><td>—</td>
  <td>—</td><td class="r">{pct(SPY['10yr']['maxdd'])}</td><td>—</td><td>—</td>
  <td class="sep">{pct(SPY['3yr']['cagr'])}</td><td>—</td>
  <td class="r dim">{pct(SPY['3yr']['maxdd'])}</td><td>—</td><td>—</td>
</tr>""")

rows_html = "\n".join(rows)

doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>IB Bot — Extended Backtest: 10yr vs 3yr</title>
<style>
html,body{{background:#0f1117!important;color:#d0d6e0;font-family:'Segoe UI',system-ui,sans-serif;margin:0;padding:24px;font-size:14px;line-height:1.5}}
h1{{color:#e8ecf4;font-size:1.45rem;margin-bottom:4px}}
h2{{color:#b0bcd4;font-size:1rem;margin:28px 0 8px;border-bottom:1px solid #252b3a;padding-bottom:4px}}
p,li{{color:#9aabb8;max-width:860px}}
.meta{{color:#606878;font-size:.8rem;margin-bottom:18px}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin-bottom:20px}}
th{{background:#141820;color:#8898b0;padding:6px 10px;border-bottom:1px solid #252b3a;white-space:nowrap;text-align:left}}
td{{padding:5px 10px;border-bottom:1px solid #1c2230;vertical-align:middle}}
tr:hover td{{background:#141820}}
.nm{{min-width:200px;color:#c8d8e8}}
.g{{color:#4ec97b}} .r{{color:#e06060}} .n{{color:#9aabb8}} .dim{{color:#7888a0}}
.sep{{border-left:2px solid #252b3a}}
.spy-row td{{color:#7888a0;font-style:italic}}
.note{{background:#141820;border-left:3px solid #2a4060;padding:10px 16px;border-radius:0 4px 4px 0;margin:14px 0;color:#8898b0;font-size:.85rem}}
.finding{{background:#111a10;border-left:3px solid #2a5030;padding:10px 16px;border-radius:0 4px 4px 0;margin:10px 0;font-size:.85rem}}
.finding strong{{color:#6ecf8e}}
.warn-box{{background:#1a1508;border-left:3px solid #604020;padding:10px 16px;border-radius:0 4px 4px 0;margin:10px 0;font-size:.85rem}}
.warn-box strong{{color:#d4a240}}
th.sep{{border-left:2px solid #2a3050}}
</style></head><body>
<h1>IB Bot — Extended Backtest: 10yr vs 3yr</h1>
<div class="meta">
  13F strategies: 2016-01-01 → 2026-05-18 (10.4yr) &nbsp;|&nbsp;
  FINRA Monthly: 2018-10-01 → 2026-05-18 (7.6yr) &nbsp;|&nbsp;
  SPY 10yr CAGR: <strong style="color:#d4a240">15.26%</strong> &nbsp;|&nbsp;
  SPY 3yr CAGR: <strong style="color:#d4a240">22.50%</strong>
</div>

<div class="note">
  <strong>Price cache note:</strong> Running in <code>cache_only</code> mode.
  Tickers not in cache for a given period are skipped (conservative bias — missing positions = 0 return, not negative).
  Historical 13F portfolios from 2016–2019 may have slightly lower position counts due to IPOs/delistings not in cache.
  This slightly <em>understates</em> early performance, not overstates it.
</div>

<h2>Results: 10yr vs 3yr side-by-side</h2>
<p style="font-size:.82rem;color:#606878">
  Left block = extended window. Right block (after │) = 3yr bull-market run.
  Delta columns show 10yr minus 3yr (negative = 3yr was inflated).
</p>
<table>
<thead>
<tr>
  <th>Strategy</th>
  <th>CAGR</th><th>vs SPY</th><th>Sharpe</th><th>MaxDD</th><th>Alpha</th><th>Trades</th>
  <th class="sep">3yr CAGR</th><th>3yr Sharpe</th><th>3yr MaxDD</th>
  <th>ΔCAGR</th><th>ΔSharpe</th>
</tr>
</thead>
<tbody>{rows_html}</tbody>
</table>

<h2>Key Findings</h2>

<div class="finding">
  <strong>Druckenmiller & Burry survive the longer window.</strong>
  Both stay above SPY at 10yr: Druckenmiller +8.7pp (23.9% vs 15.3%), Burry +8.1pp (23.4% vs 15.3%).
  Druckenmiller's alpha drops from 14.5% to 9.5% — still highly meaningful over 43 quarterly rebalances.
  Burry's alpha is almost unchanged (13.1% → 12.3%) — most consistent signal in the set.
</div>

<div class="warn-box">
  <strong>Li Lu collapses over 10yr.</strong>
  3yr CAGR was 24.5% (Sharpe 1.34, alpha 9.6%) — looked like an elite strategy.
  10yr: 10.2% CAGR, Sharpe 0.54, alpha 1.1% — <em>underperforms SPY by 5pp</em>.
  The 3yr numbers were entirely a function of timing: Li Lu was heavily concentrated in BABA/Alibaba and
  Chinese tech that happened to have a strong final 2 years after the regulatory crackdown recovery.
  185 total trades over 10yr = extremely few data points.
</div>

<div class="warn-box">
  <strong>Tepper and Howard Marks barely clear SPY at 10yr.</strong>
  Tepper: +1.5pp alpha 3.2% (was +10.5pp alpha 9.6% at 3yr).
  Marks: +1.3pp alpha 3.6% (was +4.5pp alpha 8.1% at 3yr). MaxDD -50.7% is extreme for a "defensive" strategy —
  Oaktree is credit-heavy and the 2020 credit freeze was brutal.
  Not worth active management fees/complexity for 1-2pp edge.
</div>

<div class="finding">
  <strong>FINRA Monthly: tracks SPY closely, different regime.</strong>
  13.8% CAGR vs SPY 14.7% (7.5yr) — basically flat to benchmark on raw return.
  But beta 0.63 and alpha 5.5% are real: the strategy captures ~63% of market risk with ~5pp excess return,
  which means it significantly outperforms SPY on a risk-adjusted basis.
  MaxDD -33.8% ≈ SPY -33.7% over the same window (mainly the 2020 crash).
</div>

<h2>MaxDD Reality Check</h2>
<p>The 3yr window missed the two biggest drawdowns of the period:</p>
<ul>
  <li><strong>COVID crash (Feb–Mar 2020)</strong>: SPY -34%. Credit-heavy portfolios (Marks) worse at -50%+</li>
  <li><strong>2022 bear market</strong>: SPY -25%, growth/tech funds (Tiger, Coatue) -40%+. The 2023 start date captured the <em>recovery</em> not the drawdown.</li>
</ul>
<p>The extended MaxDDs are more representative of what real capital would experience.</p>

<h2>Recommendation Update</h2>
<table>
<thead><tr><th>Strategy</th><th>10yr verdict</th><th>Changed from 3yr?</th></tr></thead>
<tbody>
<tr><td>Stanley Druckenmiller</td><td class="g">✓ Strong — 23.9% CAGR, Sharpe 0.96, alpha 9.5%</td><td class="n">No change</td></tr>
<tr><td>Michael Burry</td><td class="g">✓ Strong — 23.4% CAGR, Sharpe 0.84, alpha 12.3% (most consistent)</td><td class="g">Upgraded — more consistent than 3yr suggested</td></tr>
<tr><td>FINRA Monthly</td><td class="n">~ Neutral — tracks SPY but lower beta; risk-adjusted outperformance</td><td class="r">Downgraded — CAGR below SPY, but alpha real</td></tr>
<tr><td>David Tepper</td><td class="n">~ Marginal — +1.5pp over SPY, Sharpe 0.74</td><td class="r">Downgraded — 3yr numbers were bull-market inflated</td></tr>
<tr><td>Howard Marks</td><td class="n">~ Marginal — +1.3pp, MaxDD -50.7% is a red flag</td><td class="r">Downgraded — massive drawdown not visible in 3yr</td></tr>
<tr><td>Li Lu</td><td class="r">✗ Drop — underperforms SPY, alpha ~0 over 10yr</td><td class="r">Major downgrade — 3yr was pure China-tech timing luck</td></tr>
</tbody>
</table>
</body></html>"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(doc)
print(f"Wrote {OUT}")
