"""
Render a dark-mode HTML tearsheet for factor investing backtest results.

Usage (inside Docker):
    python3 /app/research/factor_report_render.py
  or (host):
    python3 research/factor_report_render.py

Reads:  research/factor_backtest_results.json
Writes: research/factor_backtest_report.html
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RESULTS_PATH = os.path.join(os.path.dirname(__file__), "factor_backtest_results.json")
OUT_PATH     = os.path.join(os.path.dirname(__file__), "factor_backtest_report.html")

# ── colour helpers ─────────────────────────────────────────────────────────────

def _cagr_class(v):
    if v is None: return "neutral"
    return "good" if v >= 0.15 else ("ok" if v >= 0.08 else "bad")

def _sharpe_class(v):
    if v is None: return "neutral"
    return "good" if v >= 1.0 else ("ok" if v >= 0.6 else "bad")

def _alpha_class(v):
    if v is None: return "neutral"
    return "good" if v > 0.02 else ("ok" if v >= 0 else "bad")

def _dd_class(v):
    if v is None: return "neutral"
    return "good" if v >= -0.15 else ("ok" if v >= -0.25 else "bad")

def _pct(v, decimals=1):
    if v is None: return "—"
    return f"{v*100:+.{decimals}f}%"

def _pct_pos(v, decimals=1):
    if v is None: return "—"
    return f"{v*100:.{decimals}f}%"

def _num(v, decimals=2):
    if v is None: return "—"
    return f"{v:.{decimals}f}"


def build_html(data: dict) -> str:
    results  = data["results"]
    window   = data["window"]
    spy      = data["spy_benchmark"]
    as_of    = data.get("as_of", "")[:10]

    # Sort by CAGR desc, errors at bottom
    ok_rows = [(k, v) for k, v in results.items() if "error" not in v]
    err_rows = [(k, v) for k, v in results.items() if "error" in v]
    ok_rows.sort(key=lambda x: x[1].get("cagr", -99), reverse=True)
    sorted_rows = ok_rows + err_rows

    # ── table rows ────────────────────────────────────────────────────────────

    def make_row(label, r, is_spy=False, rank=None):
        if "error" in r:
            return f"""
            <tr class="err-row">
              <td class="rank">{'—'}</td>
              <td class="label">{label}</td>
              <td colspan="7" class="err-msg">{r['error']}</td>
            </tr>"""

        cagr = r.get("cagr")
        sh   = r.get("sharpe")
        srt  = r.get("sortino")
        dd   = r.get("max_drawdown")
        alp  = r.get("alpha")
        bet  = r.get("beta")
        vol  = r.get("volatility")
        nreb = r.get("n_rebalances", "—")
        extra_class = "spy-row" if is_spy else ""

        rank_cell = "SPY" if is_spy else (str(rank) if rank else "—")

        return f"""
            <tr class="{extra_class}">
              <td class="rank">{rank_cell}</td>
              <td class="label">{'📊 ' if is_spy else ''}{label}</td>
              <td class="{_cagr_class(cagr)}">{_pct_pos(cagr)}</td>
              <td class="{_sharpe_class(sh)}">{_num(sh)}</td>
              <td class="{_sharpe_class(srt) if srt is not None else 'neutral'}">{_num(srt)}</td>
              <td class="{_dd_class(dd)}">{_pct_pos(dd)}</td>
              <td class="{_alpha_class(alp)}">{_pct(alp)}</td>
              <td class="neutral">{_num(bet)}</td>
              <td class="neutral">{_pct_pos(vol) if vol else '—'}</td>
            </tr>"""

    rows_html = ""
    for i, (label, r) in enumerate(sorted_rows, 1):
        rows_html += make_row(label, r, rank=i)

    spy_row = make_row(
        "S&P 500 (SPY)",
        {"cagr": spy["cagr"], "sharpe": spy["sharpe"],
         "max_drawdown": spy["max_drawdown"],
         "sortino": None, "alpha": 0.0, "beta": 1.0, "volatility": None},
        is_spy=True,
    )

    # ── metrics cards ─────────────────────────────────────────────────────────

    best_cagr_label, best_cagr_r = max(ok_rows, key=lambda x: x[1].get("cagr", -99)) if ok_rows else ("—", {})
    best_sh_label, best_sh_r = max(ok_rows, key=lambda x: x[1].get("sharpe", -99)) if ok_rows else ("—", {})
    best_alp_label, best_alp_r = max(ok_rows, key=lambda x: x[1].get("alpha", -99)) if ok_rows else ("—", {})

    beat_spy_count = sum(1 for _, r in ok_rows if r.get("cagr", 0) > spy["cagr"])

    factor_used = set()
    for _, r in ok_rows:
        f = r.get("factor", "")
        if f:
            factor_used.add(f)

    cards_html = f"""
    <div class="cards">
      <div class="card">
        <div class="card-label">Best CAGR</div>
        <div class="card-value good">{_pct_pos(best_cagr_r.get('cagr'))}</div>
        <div class="card-sub">{best_cagr_label}</div>
      </div>
      <div class="card">
        <div class="card-label">Best Sharpe</div>
        <div class="card-value good">{_num(best_sh_r.get('sharpe'))}</div>
        <div class="card-sub">{best_sh_label}</div>
      </div>
      <div class="card">
        <div class="card-label">Best Alpha</div>
        <div class="card-value {'good' if (best_alp_r.get('alpha') or 0) > 0 else 'bad'}">{_pct(best_alp_r.get('alpha'))}</div>
        <div class="card-sub">{best_alp_label}</div>
      </div>
      <div class="card">
        <div class="card-label">Beat SPY</div>
        <div class="card-value {'good' if beat_spy_count > 0 else 'bad'}">{beat_spy_count} / {len(ok_rows)}</div>
        <div class="card-sub">factors by CAGR</div>
      </div>
    </div>"""

    # ── HTML ──────────────────────────────────────────────────────────────────

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Factor Investing Backtest Report</title>
<style>
  html, body {{
    background: #0f1117 !important;
    color: #e2e8f0;
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    margin: 0; padding: 0;
  }}
  .container {{
    max-width: 1100px;
    margin: 0 auto;
    padding: 32px 24px 64px;
  }}
  h1 {{
    font-size: 1.6rem;
    font-weight: 700;
    color: #f1f5f9;
    margin: 0 0 4px;
  }}
  .subtitle {{
    color: #64748b;
    font-size: 0.85rem;
    margin-bottom: 28px;
  }}
  .subtitle span {{
    color: #94a3b8;
    font-weight: 500;
  }}

  /* Cards */
  .cards {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin-bottom: 32px;
  }}
  @media (max-width: 700px) {{
    .cards {{ grid-template-columns: repeat(2, 1fr); }}
  }}
  .card {{
    background: #1a1f2e;
    border: 1px solid #2d3748;
    border-radius: 10px;
    padding: 16px 18px;
  }}
  .card-label {{
    font-size: 0.72rem;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 6px;
  }}
  .card-value {{
    font-size: 1.5rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }}
  .card-sub {{
    font-size: 0.75rem;
    color: #64748b;
    margin-top: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  /* Table */
  .table-wrap {{
    overflow-x: auto;
    border: 1px solid #1e2535;
    border-radius: 10px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }}
  thead th {{
    background: #141824;
    color: #64748b;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 10px 14px;
    text-align: right;
    border-bottom: 1px solid #1e2535;
    white-space: nowrap;
  }}
  thead th:first-child, thead th:nth-child(2) {{
    text-align: left;
  }}
  tbody tr {{
    border-bottom: 1px solid #1a1f2e;
    transition: background 0.15s;
  }}
  tbody tr:hover {{
    background: #1a1f2e;
  }}
  tbody tr:last-child {{
    border-bottom: none;
  }}
  td {{
    padding: 11px 14px;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }}
  td.rank {{
    text-align: center;
    color: #475569;
    font-size: 0.75rem;
    width: 36px;
  }}
  td.label {{
    text-align: left;
    font-weight: 600;
    color: #cbd5e1;
  }}
  .spy-row td {{
    background: #141824;
    color: #94a3b8;
    font-style: italic;
  }}
  .spy-row td.label {{
    color: #94a3b8;
  }}
  .err-row td {{
    color: #ef4444;
    font-size: 0.8rem;
  }}
  .err-msg {{
    text-align: left;
  }}

  /* Colour classes */
  .good  {{ color: #4ade80; }}
  .ok    {{ color: #facc15; }}
  .bad   {{ color: #f87171; }}
  .neutral {{ color: #94a3b8; }}

  /* Footer */
  .footer {{
    margin-top: 32px;
    color: #334155;
    font-size: 0.75rem;
    text-align: center;
  }}

  /* Legend */
  .legend {{
    display: flex;
    gap: 18px;
    margin-bottom: 20px;
    flex-wrap: wrap;
  }}
  .legend-item {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.75rem;
    color: #64748b;
  }}
  .legend-dot {{
    width: 8px; height: 8px;
    border-radius: 50%;
  }}
  .legend-dot.good  {{ background: #4ade80; }}
  .legend-dot.ok    {{ background: #facc15; }}
  .legend-dot.bad   {{ background: #f87171; }}

  /* Section header */
  .section-label {{
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #475569;
    margin: 28px 0 12px;
  }}
</style>
</head>
<body>
<div class="container">
  <h1>Factor Investing Backtest Report</h1>
  <div class="subtitle">
    Window <span>{window['start']} → {window['end']}</span> &nbsp;·&nbsp;
    Universe <span>~2,600 tickers (all cached)</span> &nbsp;·&nbsp;
    Portfolio <span>Top 20, equal weight, monthly rebalance, 10 bps cost</span> &nbsp;·&nbsp;
    As of <span>{as_of}</span>
  </div>

  {cards_html}

  <div class="legend">
    <div class="legend-item"><div class="legend-dot good"></div> Strong</div>
    <div class="legend-item"><div class="legend-dot ok"></div> Moderate</div>
    <div class="legend-item"><div class="legend-dot bad"></div> Weak</div>
  </div>

  <div class="section-label">Factor Portfolios vs Benchmark</div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Factor / Strategy</th>
          <th>CAGR</th>
          <th>Sharpe</th>
          <th>Sortino</th>
          <th>Max DD</th>
          <th>Alpha (ann.)</th>
          <th>Beta</th>
          <th>Volatility</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
        {spy_row}
      </tbody>
    </table>
  </div>

  <div class="footer">
    Generated by ib_bot factor engine &nbsp;·&nbsp;
    Data source: yfinance price cache &nbsp;·&nbsp;
    Not investment advice
  </div>
</div>
</body>
</html>"""


def main():
    if not os.path.exists(RESULTS_PATH):
        print(f"Results file not found: {RESULTS_PATH}")
        sys.exit(1)

    with open(RESULTS_PATH) as f:
        data = json.load(f)

    html = build_html(data)

    with open(OUT_PATH, "w") as f:
        f.write(html)

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
