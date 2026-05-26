"""
Factor Regime Equity Curves
Builds "always hold" vs "regime-timed" equity curves for HML and SMB.
Saves dark-mode HTML with Plotly charts to factor_regime_equity.html.
Run: python3 research/factor_regime_equity.py
"""
from __future__ import annotations
import json, math, os, warnings
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb

warnings.filterwarnings("ignore")

# Re-use data/feature functions from factor_regime_ml
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from factor_regime_ml import (
    load_french_3factor, load_french_5factor, load_beme_spread,
    build_features, build_targets, walk_forward_folds,
    MIN_TRAIN, EMBARGO, STEP, TEST_LEN, HOLDOUT_START, N_SEEDS, LGBM_BASE,
)

OUT_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "factor_regime_equity.html")

THRESHOLD = 0.52   # prob > this → hold factor, else go to cash (RF)

def make_lr():
    return Pipeline([("s", StandardScaler()),
                     ("c", LogisticRegression(C=0.1, max_iter=500, random_state=42))])

def make_lgbm(seed=0):
    return lgb.LGBMClassifier(**{**LGBM_BASE, "random_state": seed})


def build_oof_probs(X: pd.DataFrame, y: pd.Series,
                    holdout_start_idx: int) -> tuple[pd.Series, pd.Series]:
    """
    Walk-forward OOF LR probabilities.

    Returns:
      oof_prob_filled — dev probs with NaN gaps filled with 1.0 (= always hold,
                        so training-only months and embargo gaps never get a
                        spurious advantage from being skipped)
      holdout_prob    — clean holdout probs (retrained on all dev)

    Gap-filling is the critical fix: without it, the equity curve only compounds
    on test-window months, cherry-picking away early/volatile periods.
    """
    X_dev = X.iloc[:holdout_start_idx]
    y_dev = y.iloc[:holdout_start_idx]
    col_med = X_dev.median()
    X_dev  = X_dev.fillna(col_med)
    X_hold = X.iloc[holdout_start_idx:].fillna(col_med)

    folds = walk_forward_folds(
        n=len(X_dev), min_train=MIN_TRAIN, step=STEP,
        test_len=TEST_LEN, embargo=EMBARGO,
        holdout_start_idx=len(X_dev),
    )

    oof_prob = pd.Series(np.nan, index=X_dev.index)
    for tr_idx, te_idx in folds:
        lr = make_lr()
        lr.fit(X_dev.iloc[tr_idx], y_dev.iloc[tr_idx])
        oof_prob.iloc[te_idx] = lr.predict_proba(X_dev.iloc[te_idx])[:, 1]

    # Fill NaN (training-only months + embargo gaps) with 1.0 = "always hold factor"
    # This is the honest baseline: when the model has no opinion, hold.
    oof_prob_filled = oof_prob.fillna(1.0)

    # Retrain on all dev for holdout
    lr_full = make_lr()
    lr_full.fit(X_dev, y_dev)
    hold_prob = pd.Series(
        lr_full.predict_proba(X_hold)[:, 1],
        index=X_hold.index,
    )

    return oof_prob_filled, hold_prob


def build_equity(factor_returns: pd.Series, prob: pd.Series,
                 rf: pd.Series, threshold: float) -> tuple[pd.Series, pd.Series]:
    """
    always_on: $1 compounding in the raw factor return every month
    timed    : $1 compounding in factor when prob > threshold, else RF
    Returns both as cumulative series starting at 100.
    """
    aligned = pd.DataFrame({
        "factor": factor_returns,
        "prob":   prob,
        "rf":     rf,
    }).dropna()

    always_ret = aligned["factor"]
    timed_ret  = np.where(
        aligned["prob"] > threshold,
        aligned["factor"],
        aligned["rf"],
    )
    timed_ret = pd.Series(timed_ret, index=aligned.index)

    always_eq = (1 + always_ret).cumprod() * 100
    timed_eq  = (1 + timed_ret).cumprod() * 100
    return always_eq, timed_eq


def cagr(s: pd.Series) -> float:
    years = (s.index[-1] - s.index[0]).days / 365.25
    return (s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1 if years > 0 else float("nan")

def sharpe(rets: pd.Series) -> float:
    r = rets.dropna()
    return float(r.mean() / r.std() * math.sqrt(12)) if r.std() > 0 else 0.0

def maxdd(s: pd.Series) -> float:
    return float(((s - s.cummax()) / s.cummax()).min())


def plotly_dark_chart(dates_list, series_list, labels, colors, title,
                      holdout_start_str) -> str:
    """Return Plotly chart as HTML <div>+<script> block."""
    traces = ""
    for i, (vals, label, color) in enumerate(zip(series_list, labels, colors)):
        dash = "'dot'" if i >= 2 else "'solid'"
        pts = ", ".join(
            f"{{x: '{d}', y: {round(v, 2)}}}"
            for d, v in zip(dates_list[i], vals)
            if not (isinstance(v, float) and math.isnan(v))
        )
        traces += f"""{{
          x: [{', '.join(f"'{d}'" for d, v in zip(dates_list[i], vals) if not (isinstance(v, float) and math.isnan(v)))}],
          y: [{', '.join(str(round(v,2)) for d, v in zip(dates_list[i], vals) if not (isinstance(v, float) and math.isnan(v)))}],
          type: 'scatter', mode: 'lines', name: '{label}',
          line: {{color: '{color}', width: 2, dash: {dash}}},
        }},"""

    div_id = title.replace(" ", "_").replace("(", "").replace(")", "")
    return f"""
<div id="{div_id}" style="height:380px;margin-bottom:8px"></div>
<script>
Plotly.newPlot('{div_id}', [{traces}], {{
  title: {{text: '{title}', font: {{color: '#f1f5f9', size: 14}}}},
  paper_bgcolor: '#0f1117', plot_bgcolor: '#111827',
  font: {{color: '#94a3b8', size: 11}},
  legend: {{font: {{color: '#94a3b8'}}}},
  xaxis: {{gridcolor: '#1e2535', zerolinecolor: '#1e2535',
    shapes: [{{type:'line', x0:'{holdout_start_str}', x1:'{holdout_start_str}',
               y0:0, y1:1, yref:'paper',
               line:{{color:'#f59e0b', width:1, dash:'dot'}}}}]}},
  yaxis: {{gridcolor: '#1e2535', zerolinecolor: '#1e2535', title: 'Value ($100 start)'}},
  shapes: [{{type:'line', x0:'{holdout_start_str}', x1:'{holdout_start_str}',
             y0:0, y1:1, yref:'paper',
             line:{{color:'#f59e0b', width:1.5, dash:'dot'}}}}],
  annotations: [{{x:'{holdout_start_str}', y:1, yref:'paper', text:'Holdout →',
                   showarrow:false, font:{{color:'#f59e0b', size:10}},
                   xanchor:'left', yanchor:'bottom'}}],
  margin: {{t:50, l:60, r:20, b:40}},
  hovermode: 'x unified',
}}, {{responsive: true, displayModeBar: false}});
</script>"""


def main():
    print("Building factor regime equity curves...")

    # Load data
    ff3  = load_french_3factor()
    ff5  = None
    try:
        ff5 = load_french_5factor()
    except Exception:
        pass
    beme = load_beme_spread()

    feats = build_features(ff3, ff5, beme)
    tgts  = build_targets(ff3)
    idx   = feats.index.intersection(tgts.index)
    feats, tgts = feats.loc[idx], tgts.loc[idx]
    valid = tgts.notna().any(axis=1)
    feats, tgts = feats[valid], tgts[valid]

    holdout_start    = pd.Timestamp(HOLDOUT_START)
    holdout_start_idx = feats.index.searchsorted(holdout_start)

    rf = ff3.loc[feats.index, "RF"]

    charts_html = ""
    stat_cards  = ""

    for target_col, factor_ret_col, name, color_on, color_off in [
        ("hml_bull_12m", "HML", "HML — Value Premium", "#4ade80", "#f87171"),
        ("smb_bull_12m", "SMB", "SMB — Size Premium",  "#60a5fa", "#f59e0b"),
    ]:
        print(f"\n  {name}...")
        y = tgts[target_col].dropna()
        X = feats.loc[y.index]
        factor_ret = ff3.loc[X.index, factor_ret_col]
        rf_aligned = rf.loc[X.index]

        # Build OOF + holdout probabilities
        oof_prob, hold_prob = build_oof_probs(X, y, holdout_start_idx)

        # Full continuous prob series (dev filled + holdout appended)
        full_prob = pd.concat([oof_prob, hold_prob])
        fret      = factor_ret.loc[full_prob.index]
        rfr       = rf_aligned.loc[full_prob.index]

        always_eq, timed_eq = build_equity(fret, full_prob, rfr, THRESHOLD)

        dev_mask  = always_eq.index < holdout_start
        hold_mask = always_eq.index >= holdout_start

        def _stats(eq, ret_series):
            if len(eq) < 2: return {}
            rets = ret_series.loc[eq.index].dropna()
            return {
                "cagr": cagr(eq),
                "sharpe": sharpe(rets),
                "maxdd": maxdd(eq),
            }

        def _timed_rets(mask):
            p = full_prob[mask]
            return pd.Series(
                np.where(p > THRESHOLD, fret[mask], rfr[mask]),
                index=fret[mask].index)

        always_stats_dev  = _stats(always_eq[dev_mask],  fret)
        timed_stats_dev   = _stats(timed_eq[dev_mask],   _timed_rets(dev_mask))
        always_stats_hold = _stats(always_eq[hold_mask], fret)
        timed_stats_hold  = _stats(timed_eq[hold_mask],  _timed_rets(hold_mask))

        def _p(v): return f"{v*100:.1f}%" if v and math.isfinite(v) else "—"
        def _n(v): return f"{v:.2f}" if v and math.isfinite(v) else "—"

        # Stat cards
        stat_cards += f"""
        <div class="stat-section">
          <div class="stat-title">{name}</div>
          <div class="stat-grid">
            <div class="stat-col">
              <div class="stat-label">DEV PERIOD (OOF, pre-2010)</div>
              <table class="stat-table">
                <thead><tr><th></th><th>Always Hold</th><th>Regime-Timed</th><th>Δ</th></tr></thead>
                <tbody>
                  <tr><td>CAGR</td>
                    <td>{_p(always_stats_dev.get('cagr'))}</td>
                    <td class="{'green' if (timed_stats_dev.get('cagr') or 0) > (always_stats_dev.get('cagr') or 0) else 'red'}">{_p(timed_stats_dev.get('cagr'))}</td>
                    <td class="dim">{_p((timed_stats_dev.get('cagr') or 0) - (always_stats_dev.get('cagr') or 0))}</td>
                  </tr>
                  <tr><td>Sharpe</td>
                    <td>{_n(always_stats_dev.get('sharpe'))}</td>
                    <td class="{'green' if (timed_stats_dev.get('sharpe') or 0) > (always_stats_dev.get('sharpe') or 0) else 'red'}">{_n(timed_stats_dev.get('sharpe'))}</td>
                    <td class="dim">{_n((timed_stats_dev.get('sharpe') or 0) - (always_stats_dev.get('sharpe') or 0))}</td>
                  </tr>
                  <tr><td>MaxDD</td>
                    <td>{_p(always_stats_dev.get('maxdd'))}</td>
                    <td class="{'green' if (timed_stats_dev.get('maxdd') or -1) > (always_stats_dev.get('maxdd') or -1) else 'red'}">{_p(timed_stats_dev.get('maxdd'))}</td>
                    <td class="dim">{_p((timed_stats_dev.get('maxdd') or 0) - (always_stats_dev.get('maxdd') or 0))}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="stat-col">
              <div class="stat-label">HOLDOUT (2010–2026, unseen)</div>
              <table class="stat-table">
                <thead><tr><th></th><th>Always Hold</th><th>Regime-Timed</th><th>Δ</th></tr></thead>
                <tbody>
                  <tr><td>CAGR</td>
                    <td>{_p(always_stats_hold.get('cagr'))}</td>
                    <td class="{'green' if (timed_stats_hold.get('cagr') or 0) > (always_stats_hold.get('cagr') or 0) else 'red'}">{_p(timed_stats_hold.get('cagr'))}</td>
                    <td class="dim">{_p((timed_stats_hold.get('cagr') or 0) - (always_stats_hold.get('cagr') or 0))}</td>
                  </tr>
                  <tr><td>Sharpe</td>
                    <td>{_n(always_stats_hold.get('sharpe'))}</td>
                    <td class="{'green' if (timed_stats_hold.get('sharpe') or 0) > (always_stats_hold.get('sharpe') or 0) else 'red'}">{_n(timed_stats_hold.get('sharpe'))}</td>
                    <td class="dim">{_n((timed_stats_hold.get('sharpe') or 0) - (always_stats_hold.get('sharpe') or 0))}</td>
                  </tr>
                  <tr><td>MaxDD</td>
                    <td>{_p(always_stats_hold.get('maxdd'))}</td>
                    <td class="{'green' if (timed_stats_hold.get('maxdd') or -1) > (always_stats_hold.get('maxdd') or -1) else 'red'}">{_p(timed_stats_hold.get('maxdd'))}</td>
                    <td class="dim">{_p((timed_stats_hold.get('maxdd') or 0) - (always_stats_hold.get('maxdd') or 0))}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>"""

        # Chart: always vs timed, full period
        dates_str   = [d.strftime("%Y-%m") for d in always_eq.index]
        dates_str_t = [d.strftime("%Y-%m") for d in timed_eq.index]
        charts_html += plotly_dark_chart(
            dates_list=[dates_str, dates_str_t],
            series_list=[always_eq.values, timed_eq.values],
            labels=["Always Hold", f"Regime-Timed (p>{THRESHOLD})"],
            colors=[color_off, color_on],
            title=f"{name} — $100 growth (OOF dev + holdout)",
            holdout_start_str=holdout_start.strftime("%Y-%m"),
        )

        print(f"    Dev  — always CAGR={_p(always_stats_dev.get('cagr'))}  timed CAGR={_p(timed_stats_dev.get('cagr'))}")
        print(f"    Hold — always CAGR={_p(always_stats_hold.get('cagr'))}  timed CAGR={_p(timed_stats_hold.get('cagr'))}")

    # Write HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Factor Regime — Equity Curves</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
html,body{{background:#0f1117!important;color:#e2e8f0;font-family:'Inter',system-ui,sans-serif;margin:0;padding:0}}
.container{{max-width:1100px;margin:0 auto;padding:32px 20px 64px}}
h1{{font-size:1.5rem;font-weight:700;color:#f1f5f9;margin:0 0 4px}}
.subtitle{{color:#64748b;font-size:.83rem;margin-bottom:28px}}
.subtitle b{{color:#94a3b8}}
.auc-box{{background:#141824;border:1px solid #1e2535;border-radius:8px;padding:14px 18px;
  margin-bottom:24px;font-size:.82rem;color:#94a3b8;line-height:1.7}}
.auc-box strong{{color:#cbd5e1}}
.auc-box .green{{color:#4ade80}}.auc-box .yellow{{color:#facc15}}.auc-box .red{{color:#f87171}}

.stat-section{{margin-bottom:40px}}
.stat-title{{font-size:.85rem;font-weight:700;color:#cbd5e1;margin-bottom:12px;
  padding-bottom:6px;border-bottom:1px solid #1e2535}}
.stat-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:16px}}
@media(max-width:700px){{.stat-grid{{grid-template-columns:1fr}}}}
.stat-label{{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
  color:#475569;margin-bottom:6px}}
.stat-table{{width:100%;border-collapse:collapse;font-size:.8rem}}
.stat-table thead th{{background:#0f1117;color:#475569;font-size:.67rem;text-transform:uppercase;
  padding:5px 8px;border-bottom:1px solid #1e2535;text-align:right}}
.stat-table thead th:first-child{{text-align:left}}
.stat-table tbody tr{{border-bottom:1px solid #161b27}}
.stat-table td{{padding:6px 8px;text-align:right;font-variant-numeric:tabular-nums}}
.stat-table td:first-child{{text-align:left;color:#94a3b8}}
.green{{color:#4ade80}}.yellow{{color:#facc15}}.red{{color:#f87171}}.dim{{color:#475569}}
.footer{{margin-top:32px;color:#334155;font-size:.72rem;text-align:center}}
.divider{{border:none;border-top:1px solid #1e2535;margin:32px 0}}
</style>
</head>
<body>
<div class="container">
  <h1>Factor Regime — Equity Curves</h1>
  <div class="subtitle">
    <b>Always Hold</b> vs <b>Regime-Timed</b> (LR model, p&gt;{THRESHOLD} = hold factor, else RF) ·
    OOF walk-forward dev (1946–2009) + holdout (2010–2026) · Yellow line = holdout boundary
  </div>

  <div class="auc-box">
    <strong>What AUC means simply:</strong> Show the model 100 random month-pairs — one where the premium went up, one where it went down.
    AUC = how many pairs it gets right. <span class="yellow">0.50 = coin flip</span> ·
    <span class="green">0.60 = 60 right out of 100</span> · 1.0 = perfect.
    &nbsp;HML: <span class="yellow">LR 0.591</span> (null 0.530) ·
    SMB: <span class="yellow">LR 0.568</span> (null 0.493).
    The equity curves below show what that signal is actually worth in dollar terms — before (always hold) and after (switch to T-bills when model says bad regime).
  </div>

  {stat_cards}
  <hr class="divider">
  {charts_html}

  <div class="footer">
    Data: Ken French monthly 1926→2026 · LR model, threshold p&gt;{THRESHOLD} ·
    Dev = OOF predictions · Holdout = retrain on all dev, apply to 2010–2026 ·
    Not investment advice
  </div>
</div>
</body>
</html>"""

    with open(OUT_HTML, "w") as f:
        f.write(html)
    print(f"\nWrote {OUT_HTML}")


if __name__ == "__main__":
    main()
