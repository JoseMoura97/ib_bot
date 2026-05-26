"""
Track 1 report renderer — dark mode tearsheet.
Reads track1_results.json and writes track1_report.html.
Run from host (no Docker needed).
"""
from __future__ import annotations
import json, math, os

IN_PATH  = os.path.join(os.path.dirname(__file__), "track1_results.json")
OUT_PATH = os.path.join(os.path.dirname(__file__), "track1_report.html")

WINDOWS  = ["17yr", "15yr", "10yr", "5yr", "3yr"]
FACTORS  = ["Momentum", "Low Volatility", "Mom+LowVol", "Quality"]
# Populated dynamically from results JSON (look_ahead_bias key set by runner)
LOOK_AHEAD: set = set()

# SPY reference (approximate, for context)
SPY_REF = {
    "17yr": dict(cagr=0.155, sharpe=0.78, max_drawdown=-0.339),
    "15yr": dict(cagr=0.148, sharpe=0.82, max_drawdown=-0.339),
    "10yr": dict(cagr=0.155, sharpe=0.87, max_drawdown=-0.338),
    "5yr":  dict(cagr=0.138, sharpe=0.72, max_drawdown=-0.338),
    "3yr":  dict(cagr=0.226, sharpe=1.05, max_drawdown=-0.188),
}

def p(v, d=1):
    if v is None or (isinstance(v, float) and not math.isfinite(v)): return "—"
    return f"{v*100:.{d}f}%"

def n(v, d=2):
    if v is None or (isinstance(v, float) and not math.isfinite(v)): return "—"
    return f"{v:.{d}f}"

def cls_cagr(v):
    if v is None: return "dim"
    return "green" if v >= 0.15 else ("yellow" if v >= 0.08 else "red")

def cls_sh(v):
    if v is None: return "dim"
    return "green" if v >= 1.0 else ("yellow" if v >= 0.6 else "red")

def cls_dd(v):
    if v is None: return "dim"
    return "green" if v >= -0.25 else ("yellow" if v >= -0.45 else "red")

def cls_alpha(v):
    if v is None: return "dim"
    return "green" if v > 0.02 else ("yellow" if v >= 0 else "red")

def is_anomaly(m):
    """Flag results with implausible values (data artefacts)."""
    vol = m.get("volatility", 0) or 0
    beta = abs(m.get("beta", 1) or 1)
    return vol > 5.0 or beta > 3.0

def build_html(data):
    # ── summary cards ──────────────────────────────────────────────────────
    cards_html = ""
    highlights = [
        ("Best CAGR (10yr)", "10yr", max(FACTORS, key=lambda f: data["10yr"][f].get("cagr",0))),
        ("Best Sharpe (3yr)", "3yr",  max(FACTORS, key=lambda f: data["3yr"][f].get("sharpe",0))),
        ("Best Alpha (10yr)", "10yr", max(FACTORS, key=lambda f: data["10yr"][f].get("alpha",0))),
        ("Lowest DD (15yr)",  "15yr", min(FACTORS, key=lambda f: data["15yr"][f].get("max_drawdown",0))),
    ]
    for title, win, factor in highlights:
        m = data[win][factor]
        bias = " *" if factor in LOOK_AHEAD else ""
        cards_html += f"""
        <div class="card">
          <div class="card-title">{title}</div>
          <div class="card-factor">{factor}{bias}</div>
          <div class="card-cagr {cls_cagr(m['cagr'])}">{p(m['cagr'])} CAGR</div>
          <div class="card-sub">Sh {n(m['sharpe'])} · DD {p(m['max_drawdown'])} · α {p(m['alpha'])}</div>
        </div>"""

    # ── per-window tables + equity curves ─────────────────────────────────
    COLORS = {
        "Momentum":      "#4ade80",
        "Low Volatility":"#60a5fa",
        "Mom+LowVol":    "#f59e0b",
        "Quality":       "#c084fc",
        "SPY":           "#64748b",
    }

    tables_html = ""
    chart_id = 0
    for win in WINDOWS:
        spy = SPY_REF.get(win, {})
        rows = data[win]
        chart_id += 1
        cid = f"chart_{chart_id}"

        # Build Chart.js datasets
        import json as _json
        datasets = []
        for factor in FACTORS:
            m = rows.get(factor, {})
            ec = m.get("equity_curve")
            if ec and not is_anomaly(m):
                datasets.append({
                    "label": factor,
                    "data": [{"x": d, "y": v} for d, v in zip(ec["dates"], ec["values"])],
                    "borderColor": COLORS.get(factor, "#fff"),
                    "backgroundColor": "transparent",
                    "borderWidth": 2,
                    "pointRadius": 0,
                    "tension": 0.1,
                })
        # SPY from first strategy's spy_curve
        for factor in FACTORS:
            sc = rows.get(factor, {}).get("spy_curve")
            if sc:
                datasets.append({
                    "label": "SPY",
                    "data": [{"x": d, "y": v} for d, v in zip(sc["dates"], sc["values"])],
                    "borderColor": COLORS["SPY"],
                    "backgroundColor": "transparent",
                    "borderWidth": 1.5,
                    "borderDash": [5, 4],
                    "pointRadius": 0,
                    "tension": 0.1,
                })
                break

        datasets_json = _json.dumps(datasets)

        tables_html += f"""
        <div class="window-section">
          <div class="window-label">{win} window</div>
          <div class="chart-wrap">
            <canvas id="{cid}" height="110"></canvas>
          </div>
          <script>
          (function(){{
            var ctx = document.getElementById('{cid}').getContext('2d');
            new Chart(ctx, {{
              type: 'line',
              data: {{ datasets: {datasets_json} }},
              options: {{
                responsive: true,
                maintainAspectRatio: true,
                interaction: {{ mode: 'index', intersect: false }},
                plugins: {{
                  legend: {{
                    labels: {{ color: '#94a3b8', font: {{ size: 11 }}, boxWidth: 14 }}
                  }},
                  tooltip: {{
                    backgroundColor: '#1a1f2e',
                    titleColor: '#cbd5e1',
                    bodyColor: '#94a3b8',
                    callbacks: {{
                      label: function(ctx) {{
                        return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(0);
                      }}
                    }}
                  }}
                }},
                scales: {{
                  x: {{
                    type: 'time',
                    time: {{ unit: 'year' }},
                    ticks: {{ color: '#475569', maxTicksLimit: 8 }},
                    grid: {{ color: '#1e2535' }}
                  }},
                  y: {{
                    type: 'logarithmic',
                    ticks: {{
                      color: '#475569',
                      callback: function(v) {{ return v >= 100 ? v.toFixed(0) : ''; }}
                    }},
                    grid: {{ color: '#1e2535' }}
                  }}
                }}
              }}
            }});
          }})();
          </script>
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th class="left">Strategy</th>
                <th>CAGR</th><th>Sharpe</th><th>Sortino</th>
                <th>MaxDD</th><th>Alpha</th><th>Beta</th>
                <th>Vol</th><th>Total</th><th>Yrs</th>
              </tr></thead>
              <tbody>"""

        for factor in FACTORS:
            m = rows.get(factor, {})
            if not m or "error" in m:
                tables_html += f'<tr><td class="left mono">{factor}</td><td colspan="9" class="red">ERROR</td></tr>'
                continue
            bias  = " <span class='bias-tag'>LOOK-AHEAD</span>" if factor in LOOK_AHEAD else ""
            anom  = is_anomaly(m)
            anom_tag = " <span class='anom-tag'>⚠ DATA</span>" if anom else ""
            rc = "anom-row" if anom else ""
            tables_html += f"""
                <tr class="{rc}">
                  <td class="left mono">{factor}{bias}{anom_tag}</td>
                  <td class="{cls_cagr(m['cagr'])}">{p(m['cagr'])}</td>
                  <td class="{cls_sh(m['sharpe'])}">{n(m['sharpe'])}</td>
                  <td class="dim">{n(m.get('sortino'))}</td>
                  <td class="{cls_dd(m['max_drawdown'])}">{p(m['max_drawdown'])}</td>
                  <td class="{cls_alpha(m['alpha'])}">{p(m['alpha'])}</td>
                  <td class="dim">{n(m.get('beta'))}</td>
                  <td class="dim">{p(m.get('volatility'))}</td>
                  <td class="dim">{p(m.get('total_return'),0)}</td>
                  <td class="dim">{n(m.get('years'),1)}</td>
                </tr>"""

        # SPY reference row
        tables_html += f"""
                <tr class="bench-row">
                  <td class="left mono">◄ SPY (ref)</td>
                  <td class="dim">{p(spy.get('cagr'))}</td>
                  <td class="dim">{n(spy.get('sharpe'))}</td>
                  <td class="dim">—</td>
                  <td class="dim">{p(spy.get('max_drawdown'))}</td>
                  <td class="dim">—</td><td class="dim">1.00</td>
                  <td class="dim">—</td><td class="dim">—</td><td class="dim">—</td>
                </tr>"""

        tables_html += "</tbody></table></div></div>"

    # ── CAGR heatmap across windows ────────────────────────────────────────
    heatmap_html = """
    <div class="window-section">
      <div class="window-label">CAGR across windows</div>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th class="left">Strategy</th>
            <th>15yr</th><th>10yr</th><th>5yr</th><th>3yr</th>
          </tr></thead>
          <tbody>"""
    for factor in FACTORS:
        bias = " *" if factor in LOOK_AHEAD else ""
        heatmap_html += f'<tr><td class="left mono">{factor}{bias}</td>'
        for win in WINDOWS:
            m = data[win].get(factor, {})
            if "error" in m or is_anomaly(m):
                heatmap_html += '<td class="dim">⚠</td>'
            else:
                c = m.get("cagr", 0)
                heatmap_html += f'<td class="{cls_cagr(c)}">{p(c)}</td>'
        heatmap_html += "</tr>"
    # SPY ref
    heatmap_html += '<tr class="bench-row"><td class="left mono">◄ SPY (ref)</td>'
    for win in WINDOWS:
        spy = SPY_REF.get(win, {})
        heatmap_html += f'<td class="dim">{p(spy.get("cagr"))}</td>'
    heatmap_html += "</tr></tbody></table></div></div>"

    if "Quality" in LOOK_AHEAD:
        quality_caveat_li = (
            "<li><strong>Quality (*):</strong> Uses a static fundamentals snapshot. "
            "15yr/10yr results have look-ahead bias — the model knows which companies "
            "survived with high ROE/margins. Run "
            "<code>factor_fundamentals_historical_fetch.py</code> to fix.</li>"
        )
        fund_footer = "Fundamentals: static yfinance snapshot"
    else:
        quality_caveat_li = (
            "<li><strong>Quality:</strong> Uses point-in-time quarterly fundamentals "
            "(60-day reporting lag). No look-ahead bias.</li>"
        )
        fund_footer = "Fundamentals: point-in-time quarterly (no look-ahead)"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Track 1 — Factor Backtests</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
html,body{{background:#0f1117!important;color:#e2e8f0;font-family:'Inter',system-ui,sans-serif;margin:0;padding:0}}
.container{{max-width:1100px;margin:0 auto;padding:32px 20px 64px}}
h1{{font-size:1.5rem;font-weight:700;color:#f1f5f9;margin:0 0 4px}}
.subtitle{{color:#64748b;font-size:.83rem;margin-bottom:28px}}
.subtitle b{{color:#94a3b8}}

/* cards */
.cards{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:32px}}
.card{{background:#141824;border:1px solid #1e2535;border-radius:10px;padding:16px 20px;flex:1;min-width:190px}}
.card-title{{font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:#475569;margin-bottom:6px}}
.card-factor{{font-size:.85rem;font-weight:600;color:#cbd5e1;margin-bottom:4px;font-family:monospace}}
.card-cagr{{font-size:1.5rem;font-weight:700;margin-bottom:4px}}
.card-sub{{font-size:.73rem;color:#64748b}}

/* tables */
.window-section{{margin-bottom:32px}}
.window-label{{font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;
  color:#475569;margin-bottom:8px;padding:4px 0;border-bottom:1px solid #1e2535}}
.table-wrap{{overflow-x:auto;border:1px solid #1e2535;border-radius:8px}}
table{{width:100%;border-collapse:collapse;font-size:.82rem}}
thead th{{background:#141824;color:#64748b;font-size:.68rem;text-transform:uppercase;
  letter-spacing:.06em;padding:9px 12px;white-space:nowrap;border-bottom:1px solid #1e2535;text-align:right}}
th.left{{text-align:left}}
tbody tr{{border-bottom:1px solid #161b27;transition:background .12s}}
tbody tr:hover{{background:#1a1f2e}}
tbody tr:last-child{{border-bottom:none}}
td{{padding:9px 12px;text-align:right;font-variant-numeric:tabular-nums}}
td.left{{text-align:left}}
td.mono{{font-family:monospace;font-size:.8rem;color:#cbd5e1;font-weight:600;white-space:nowrap}}
tr.bench-row td{{color:#475569;font-style:italic}}
tr.anom-row td{{opacity:.6}}

.bias-tag{{font-size:.62rem;background:#2d1f00;color:#f59e0b;border-radius:3px;
  padding:1px 5px;margin-left:4px;font-style:normal;font-family:sans-serif}}
.anom-tag{{font-size:.62rem;background:#2d1010;color:#f87171;border-radius:3px;
  padding:1px 5px;margin-left:4px;font-style:normal;font-family:sans-serif}}

.green{{color:#4ade80}} .yellow{{color:#facc15}} .red{{color:#f87171}} .dim{{color:#64748b}}

/* legend */
.legend{{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:24px;font-size:.75rem}}
.leg{{display:flex;align-items:center;gap:6px;color:#64748b}}
.dot{{width:8px;height:8px;border-radius:50%}}
.dot.green{{background:#4ade80}}.dot.yellow{{background:#facc15}}.dot.red{{background:#f87171}}

/* caveat */
.caveat{{background:#1a1f2e;border:1px solid #2d3748;border-radius:8px;padding:14px 18px;
  margin-bottom:24px;font-size:.79rem;color:#94a3b8;line-height:1.65}}
.caveat strong{{color:#cbd5e1}}
.caveat ul{{margin:6px 0 0 16px;padding:0}}
.caveat li{{margin-bottom:4px}}

.chart-wrap{{background:#0d1117;border:1px solid #1e2535;border-radius:8px;padding:16px;margin-bottom:12px}}
.footer{{margin-top:32px;color:#334155;font-size:.72rem;text-align:center}}
</style>
</head>
<body>
<div class="container">
  <h1>Track 1 — Factor Strategy Backtests</h1>
  <div class="subtitle">
    Strategies: <b>Momentum · Low Volatility · Mom+LowVol · Quality</b> &nbsp;·&nbsp;
    Universe: ~2600 US equities &nbsp;·&nbsp; Top-20 equal weight · Monthly rebalance · 10bps cost
    &nbsp;·&nbsp; Benchmark: SPY
  </div>

  <div class="caveat">
    <strong>Caveats:</strong>
    <ul>
      {quality_caveat_li}
      <li><strong>Low Volatility:</strong> Very low CAGR (2–5%) but near-zero beta and drawdown — functions as a defensive sleeve, not a return driver.</li>
      <li>Alpha/Beta vs SPY (US large-cap), which understates alpha for a small-cap focused universe.</li>
    </ul>
  </div>

  <div class="legend">
    <div class="leg"><div class="dot green"></div> Strong (CAGR≥15%, Sh≥1.0, DD≥-25%)</div>
    <div class="leg"><div class="dot yellow"></div> Moderate</div>
    <div class="leg"><div class="dot red"></div> Weak</div>
  </div>

  <div class="cards">{cards_html}</div>

  {heatmap_html}

  {tables_html}

  <div class="footer">
    Data: yfinance price cache · {fund_footer} ·
    Alpha/Beta vs SPY · Monthly rebalance on 15th · 10bps one-way cost ·
    Not investment advice
  </div>
</div>
</body>
</html>"""


def main():
    global LOOK_AHEAD
    with open(IN_PATH) as f:
        data = json.load(f)
    # Read look-ahead flags written by runner into results
    meta = data.get("_meta", {})
    if meta.get("quality_look_ahead", True):
        LOOK_AHEAD = {"Quality"}
    else:
        LOOK_AHEAD = set()
    html = build_html(data)
    with open(OUT_PATH, "w") as f:
        f.write(html)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
