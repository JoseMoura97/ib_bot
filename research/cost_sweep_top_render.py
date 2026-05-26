"""Render dark-theme cost-sensitivity report from cost_sweep_top_results.json."""
from __future__ import annotations

import html
import json
import os

HERE = os.path.dirname(__file__)
RESULTS = os.path.join(HERE, "cost_sweep_top_results.json")
OUT = os.path.join(HERE, "cost_sweep_top_report.html")

# SPY 3yr CAGR over the same window (2023-05-18 → 2026-05-08, from cache)
SPY_CAGR = 0.2228

STRATEGY_META = {
    "Howard Marks":      {"alpha": 0.081, "beta": 0.84,  "note": "Oaktree — credit-heavy, defensive"},
    "Michael Burry":     {"alpha": 0.131, "beta": 0.73,  "note": "Scion — concentrated contrarian value"},
    "Stanley Druckenmiller": {"alpha": 0.145, "beta": 1.12, "note": "Duquesne — macro, CINS-fixed"},
    "Li Lu":             {"alpha": 0.096, "beta": 0.98,  "note": "Himalaya — concentrated long-term value"},
    "David Tepper":      {"alpha": 0.096, "beta": 1.15,  "note": "Appaloosa — macro + diversified"},
    "Off-Exchange Short Squeeze (Monthly)": {
        "alpha": 0.067, "beta": 0.63, "note": "FINRA signal — low beta, uncorrelated"
    },
}

COST_ORDER = ["gross (0 bps)", "default (10 bps)", "conservative (20 bps)", "pessimistic (35 bps)"]


def pct(x, places=2):
    if isinstance(x, (int, float)):
        return f"{x*100:.{places}f}%"
    return "—"


def num(x, places=2):
    if isinstance(x, (int, float)):
        return f"{x:.{places}f}"
    return "—"


def color_cagr(cagr):
    if not isinstance(cagr, (int, float)):
        return "neutral"
    if cagr > SPY_CAGR:
        return "pos"
    if cagr > 0.10:
        return "warn"
    return "neg"


def render() -> str:
    with open(RESULTS) as f:
        data = json.load(f)

    strategy_blocks = []
    for strat_name, runs in data["results"].items():
        meta = STRATEGY_META.get(strat_name, {})
        alpha_s = pct(meta.get("alpha"))
        beta_s = num(meta.get("beta"))
        note = meta.get("note", "")

        # Sort runs in standard cost order
        run_map = {r["label"]: r for r in runs}
        rows = []
        for label in COST_ORDER:
            r = run_map.get(label)
            if not r:
                continue
            cagr = r.get("cagr")
            sh = r.get("sharpe")
            dd = r.get("max_drawdown")
            vol = r.get("volatility")
            r1y = r.get("return_1y")
            n = r.get("n_trades")
            cost_bps = r.get("total_cost_bps", 0)
            cagr_class = color_cagr(cagr)
            rows.append(
                f"<tr>"
                f"<td>{html.escape(label)}</td>"
                f"<td>{cost_bps:.0f} bps</td>"
                f"<td class='{cagr_class}'>{pct(cagr)}</td>"
                f"<td>{num(sh)}</td>"
                f"<td class='neg'>{pct(dd)}</td>"
                f"<td>{pct(r1y)}</td>"
                f"<td>{pct(vol)}</td>"
                f"<td>{n if n is not None else '—'}</td>"
                f"</tr>"
            )

        # Cost sensitivity: gross → pessimistic spread
        gross = run_map.get("gross (0 bps)", {}).get("cagr")
        pess = run_map.get("pessimistic (35 bps)", {}).get("cagr")
        spread_s = f"{(gross - pess)*100:.2f}pp" if isinstance(gross, (int, float)) and isinstance(pess, (int, float)) else "—"
        pess_cagr_s = pct(pess)

        block = f"""
<div class="strat-block">
  <h3>{html.escape(strat_name)}</h3>
  <div class="strat-meta">
    Alpha (CAPM): <strong>{alpha_s}</strong> &nbsp;|&nbsp;
    Beta: <strong>{beta_s}</strong> &nbsp;|&nbsp;
    {html.escape(note)}
    &nbsp;&nbsp;<span class="spread-badge">Cost drag 0→35 bps: <strong>{spread_s}</strong> &nbsp;|&nbsp; At 35 bps: <strong>{pess_cagr_s}</strong></span>
  </div>
  <table>
  <thead>
    <tr><th>Cost regime</th><th>Total cost</th><th>CAGR</th><th>Sharpe</th><th>Max DD</th><th>1yr Return</th><th>Vol</th><th>Trades</th></tr>
  </thead>
  <tbody>{"".join(rows)}</tbody>
  </table>
</div>"""
        strategy_blocks.append(block)

    blocks_html = "\n".join(strategy_blocks)
    spy_s = pct(SPY_CAGR)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>IB Bot — Cost Sensitivity: Top Strategies</title>
<style>
html,body{{background:#0f1117!important;color:#d0d6e0;font-family:'Segoe UI',system-ui,sans-serif;
  margin:0;padding:24px;font-size:14px;line-height:1.55}}
h1{{color:#e8ecf4;font-size:1.5rem;margin-bottom:4px}}
h2{{color:#b0bcd4;font-size:1.1rem;margin:32px 0 8px;border-bottom:1px solid #252b3a;padding-bottom:4px}}
h3{{color:#7ecfc8;font-size:1rem;margin:0 0 4px}}
p,li{{color:#9aabb8;max-width:900px}}
code{{background:#1a2030;color:#7ec8e3;padding:1px 5px;border-radius:3px;font-size:.85em}}
.meta{{color:#606878;font-size:.8rem;margin-bottom:20px}}

table{{border-collapse:collapse;width:100%;margin-bottom:8px;font-size:13px}}
th{{background:#141820;color:#8898b0;text-align:left;padding:6px 10px;
   border-bottom:1px solid #252b3a;white-space:nowrap}}
td{{padding:5px 10px;border-bottom:1px solid #1c2230}}
tr:hover td{{background:#141820}}

.pos{{color:#4ec97b}} .neg{{color:#e06060}} .warn{{color:#d4a240}} .neutral{{color:#9aabb8}}

.strat-block{{background:#111622;border:1px solid #1e2840;border-radius:6px;
             padding:16px 20px;margin:20px 0}}
.strat-meta{{color:#8898b0;font-size:.82rem;margin-bottom:10px}}
.strat-meta strong{{color:#b0c8e0}}
.spread-badge{{background:#1a2030;border:1px solid #252b3a;border-radius:10px;
              padding:2px 8px;font-size:.8rem;color:#9ab8d4}}
.spread-badge strong{{color:#e8ecf4}}

.note-box{{background:#141820;border-left:3px solid #2a4060;padding:10px 16px;
          border-radius:0 4px 4px 0;margin:16px 0;color:#8898b0;font-size:.85rem}}
.verdict-table td,th{{padding:6px 12px}}
.verdict-good{{color:#4ec97b;font-weight:600}}
.verdict-ok{{color:#d4a240;font-weight:600}}
.verdict-skip{{color:#e06060;font-weight:600}}
</style>
</head>
<body>
<h1>IB Bot — Cost Sensitivity: Top Strategies by Alpha</h1>
<div class="meta">
  Window: 2023-05-18 → 2026-05-18 (3yr) &nbsp;|&nbsp;
  Benchmark (SPY 3yr CAGR): <strong style="color:#d4a240">{spy_s}</strong> &nbsp;|&nbsp;
  Selection: positive CAPM alpha + defensible interpretation (high-beta tech funds excluded)
</div>

<div class="note-box">
  <strong>Key finding:</strong> All 13F quarterly strategies are <em>nearly cost-insensitive</em> — the spread between 0 bps gross and 35 bps pessimistic is &lt;2pp CAGR for every manager.
  This is because they trade infrequently (~40–80 trades per quarterly rebalance across a diversified portfolio).
  The FINRA Monthly strategy is partially cost-sensitive (20.7% → 12.7%) because it has 10× more trades (1164 over 3yr).
</div>

<h2>Strategy-by-Strategy Cost Breakdown</h2>
<p style="color:#606878;font-size:.82rem">
  Green CAGR = beats SPY ({spy_s}). Yellow = above 10% but below SPY. Red = below 10%.
</p>

{blocks_html}

<h2>Summary Verdict</h2>
<table>
<thead>
<tr><th>Strategy</th><th>Default CAGR (10bps)</th><th>Pessimistic (35bps)</th><th>Cost drag</th><th>Verdict</th></tr>
</thead>
<tbody>
<tr><td>Stanley Druckenmiller</td><td class="pos">36.98%</td><td class="pos">36.11%</td><td>0.87pp</td><td class="verdict-good">✓ Enable — cost-robust, positive alpha, CINS fixed</td></tr>
<tr><td>David Tepper</td><td class="pos">32.90%</td><td class="pos">32.25%</td><td>0.65pp</td><td class="verdict-good">✓ Enable — cost-robust, diversified macro</td></tr>
<tr><td>Howard Marks</td><td class="pos">26.91%</td><td class="pos">26.44%</td><td>0.47pp</td><td class="verdict-good">✓ Enable — defensive beta 0.84, best Sharpe</td></tr>
<tr><td>Li Lu</td><td class="pos">24.50%</td><td class="pos">24.24%</td><td>0.26pp</td><td class="verdict-good">✓ Enable — near-zero cost drag, concentrated value</td></tr>
<tr><td>Michael Burry</td><td class="warn">20.41%</td><td class="warn">19.19%</td><td>1.22pp</td><td class="verdict-ok">~ Consider — near SPY, very concentrated (68 trades)</td></tr>
<tr><td>FINRA Monthly</td><td class="warn">18.36%</td><td class="warn">12.74%</td><td>7.94pp</td><td class="verdict-ok">~ Consider — good Sharpe/DD, but cost drag is real; use only at ≤10bps</td></tr>
</tbody>
</table>

<div class="note-box">
  <strong>Caveats (unchanged):</strong> 3yr window = 12 quarterly rebalances — statistically thin.
  2023–2026 was a strong bull market (SPY +83% total). The numbers are directional signals,
  not vetted alpha. Druckenmiller/Tepper at beta&gt;1.1 in a bull market = partially beta-driven CAGR.
  Howard Marks (beta 0.84) and Li Lu (beta 0.98) are the most conservative reads.
</div>
</body>
</html>"""


def main():
    doc = render()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
