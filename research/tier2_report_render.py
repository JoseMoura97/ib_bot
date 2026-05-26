"""Render dark-theme HTML report from tier2_backtest_results.json."""
from __future__ import annotations

import html
import json
import os
from datetime import datetime

HERE = os.path.dirname(__file__)
RESULTS = os.path.join(HERE, "tier2_backtest_results.json")
OUT = os.path.join(HERE, "tier2_backtest_report.html")

TIER1_BLOCKED = [
    ("WallStreetBets mentions momentum", "/beta/live/wallstreetbets", "403 — subscription tier"),
    ("Off-exchange short volume",        "/beta/live/offexchangeshort", "404 — endpoint not exposed on this tier"),
    ("Patent grants momentum",           "/beta/live/allpatents",        "403 — subscription tier"),
    ("App downloads / ratings",          "/beta/live/appratings",        "403 — subscription tier"),
    ("Google Trends",                    "/beta/live/googletrends",      "404 — endpoint not exposed on this tier"),
    ("StockTwits / r/Stocks sentiment",  "/beta/live/stocktwits",        "404 — endpoint not exposed on this tier"),
    ("Twitter mentions",                 "/beta/live/twitter",           "403 — subscription tier"),
    ("Insider transactions (Quiver)",    "/beta/live/insiders",          "403 — subscription tier"),
]

# Alt-data alternatives — verified live by HTTP probe 2026-05-18.
# `effort` is rough: hours = "<2", "half-day" = 4-6, "1-2d" = 12-24.
ALT_SOURCES = [
    # (strategy, source, kind, cost, endpoint, effort, notes)
    ("WSB mentions momentum", "ApeWisdom", "FREE",  "$0",
     "GET https://apewisdom.io/api/v1.0/filter/wallstreetbets/page/N",
     "<2h",
     "Ranked tickers + mention count + 24h change. ~1207 tickers covered today. No auth, no rate limit doc — reasonable to poll every 1–6h. Drop-in replacement for Quiver WSB endpoint."),
    ("WSB mentions momentum", "Reddit JSON / PRAW", "FREE", "$0 (OAuth app)",
     "https://www.reddit.com/r/wallstreetbets/top.json + r/stocks, r/options",
     "half-day",
     "Roll your own counter via PRAW. 100 req/min after OAuth. More control, higher build cost. Use when ApeWisdom signal saturates."),
    ("WSB mentions momentum", "swaggystocks.com", "FREE-ish", "$0",
     "https://swaggystocks.com/ (HTML)",
     "half-day",
     "Scrape-only — no public API. Use as triangulation, not primary."),

    ("Off-exchange short volume", "FINRA daily CNMS short volume", "FREE", "$0",
     "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt",
     "<2h",
     "Plain text, pipe-delim: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market. Updated daily T+1. This IS the dataset Quiver resells — use directly."),
    ("Off-exchange short volume", "CBOE daily short volume", "FREE", "$0",
     "https://www.cboe.com/us/equities/market_statistics/short_sale_volume/ (CSV per-day)",
     "half-day",
     "CBOE-exchange-only view; complements FINRA off-exchange. Combine for fuller short pressure picture."),

    ("Patents momentum", "USPTO PatentsView v1", "FREE", "$0 (free API key)",
     "POST https://search.patentsview.org/api/v1/patent",
     "1-2d",
     "v1 is the current live endpoint (older v0 redirects). Free key at patentsview.org. Need to map assignee-org -> ticker (own mapping table) since USPTO uses corporate names, not tickers. ~150 LOC to build patent-momentum signal."),
    ("Patents momentum", "Google Patents Public Datasets (BigQuery)", "FREE quota", "$0–$10/mo if heavy",
     "https://console.cloud.google.com/marketplace/details/google_patents_public_datasets",
     "1-2d",
     "Public BigQuery dataset. SQL access — best for batch backfills. 1 TB free/month query budget covers light use."),

    ("App downloads / ratings", "Apptopia", "PAID", "$1k–5k/mo",
     "Apptopia REST API",
     "1-2d",
     "Industry standard. Used by every fund. Costly. Talk to sales for tier."),
    ("App downloads / ratings", "Sensor Tower", "PAID", "Comparable to Apptopia",
     "Sensor Tower Enterprise API",
     "1-2d",
     "Same playbook as Apptopia. Different methodology. Pick one."),
    ("App downloads / ratings", "data.ai (App Annie)", "PAID", "Enterprise pricing",
     "data.ai Intelligence API",
     "1-2d",
     "Strongest for in-app revenue. Same cost ballpark."),
    ("App downloads / ratings", "App Store / Play scraping", "FREE-risky", "$0",
     "google-play-scraper, app-store-scraper npm/pip libs",
     "half-day",
     "Only public ratings + review counts, NOT downloads. ToS gray area. Not a real Quiver replacement — just a sentiment proxy."),

    ("Google Trends", "pytrends", "FREE", "$0",
     "pip install pytrends",
     "<2h",
     "Unofficial Python wrapper around Google Trends. Rate-limited (~1 req/sec) and prone to 429s during peak hours. Adequate for daily polling of 50–100 tickers."),
    ("Google Trends", "SerpAPI Google Trends", "PAID", "$50/mo entry",
     "https://serpapi.com/google-trends-api",
     "<2h",
     "Pay-to-skip the pytrends rate-limit pain. Stable, supported, no captcha hell."),

    ("StockTwits sentiment", "StockTwits public API", "FREE-ish", "$0 (OAuth)",
     "https://api.stocktwits.com/api/2/streams/symbol/{TICKER}.json",
     "half-day",
     "Free + OAuth. Hard cap ~200 req/hr. Use for daily sentiment snapshot, not real-time."),
    ("StockTwits sentiment", "r/stocks via PRAW", "FREE", "$0 (OAuth)",
     "Reddit JSON / PRAW (different subreddit)",
     "<2h",
     "Same plumbing as WSB. Complementary signal (less meme, more retail-investor opinion)."),

    ("Twitter / X mentions", "X API v2 (Basic)", "PAID", "$200/mo",
     "https://api.twitter.com/2/tweets/search/recent",
     "1-2d",
     "Free tier dropped in 2023. Basic = 10k tweets/mo, Pro = 1M tweets/mo ($5k). Hard to justify vs Reddit."),
    ("Twitter / X mentions", "Mastodon + Bluesky public feeds", "FREE", "$0",
     "Mastodon Streaming API; Bluesky AT Protocol",
     "1-2d",
     "Smaller fintwit audience, growing. Free if you self-host instance / use public relays."),

    ("Insider transactions (Form 4)", "SEC EDGAR submissions API", "FREE", "$0",
     "https://data.sec.gov/submissions/CIK{cik10}.json + Form 4 XML",
     "1-2d",
     "Already partly wired (sec_edgar.py). Add Form 4 fetcher + transaction-code parser (P/S codes) + cluster aggregator. Single source of truth — Quiver resells this."),
    ("Insider transactions (Form 4)", "OpenInsider", "FREE-scrape", "$0",
     "http://openinsider.com/search?... (HTML)",
     "half-day",
     "Pre-aggregated cluster-buy view (\"insider purchases\", \"insider sales\", \"cluster purchases\"). Cheaper to scrape than re-implementing the EDGAR pipeline. Tradeoff: ToS gray, single point of failure."),
    ("Insider transactions (Form 4)", "Finnhub insider API", "PAID-free-tier", "$0 free / $99/mo standard",
     "https://finnhub.io/api/v1/stock/insider-transactions",
     "<2h",
     "Free tier = 60 req/min, basic insider-transaction data. Easiest 30-minute integration."),
]

TIER3_DEFERRED = [
    ("Form 4 cluster buys",       "Needs new SEC EDGAR Form 4 parser + cluster aggregator (~150 LOC)"),
    ("8-K event drift",           "Needs 8-K item-code classifier + drift tracker (~100 LOC)"),
    ("Buyback announcement drift","Subset of 8-K item 8.01 work above"),
    ("FDA PDUFA calendar",        "Needs external vendor (biopharmcatalyst / fdacalendar) — no plumbing"),
]

NEW_STRATEGIES = {
    "Stanley Druckenmiller", "David Tepper", "Seth Klarman", "Mohnish Pabrai",
    "Li Lu", "Chuck Akre", "Warren Buffett", "David Einhorn", "Dan Loeb",
    "Tiger Global", "Coatue", "Sequoia Fund",
    "Off-Exchange Short Squeeze",
}

LIVE_ONLY_STRATEGIES = {
    "WSB Mentions Momentum",
}


def pct(x, places=2):
    if isinstance(x, (int, float)):
        return f"{x*100:.{places}f}%"
    return "—"


def num(x, places=2):
    if isinstance(x, (int, float)):
        return f"{x:.{places}f}"
    return "—"


def money(x):
    if isinstance(x, (int, float)):
        return f"${x:,.0f}"
    return "—"


def signed_pct_class(x):
    if not isinstance(x, (int, float)):
        return "neutral"
    return "pos" if x > 0 else "neg"


def signed_num_class(x, threshold=0):
    if not isinstance(x, (int, float)):
        return "neutral"
    return "pos" if x > threshold else "neg"


def _load_turnover():
    path = os.path.join(HERE, "turnover_stats.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _load_cost_sensitivity():
    """Return the cost-sensitivity sweep dict (or None if not present)."""
    path = os.path.join(HERE, "cost_sensitivity_results.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _load_finra_result():
    """Inject the standalone FINRA backtest result into the main results dict."""
    path = os.path.join(HERE, "finra_short_result.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            r = json.load(f)
    except Exception:
        return None
    # Normalize to the same schema as the runner's summarize() output
    return {
        "cagr": r.get("cagr"),
        "sharpe": r.get("sharpe"),
        "sortino": r.get("sortino"),
        "max_drawdown": r.get("max_drawdown"),
        "total_return": r.get("total_return"),
        "volatility": r.get("volatility"),
        "return_1y": r.get("return_1y"),
        "benchmark_return_1y": r.get("benchmark_return_1y"),
        "alpha": r.get("alpha"),
        "beta": r.get("beta"),
        "win_rate": r.get("win_rate"),
        "final_value": r.get("final_value"),
        "n_trades": r.get("n_trades"),
        "n_days": r.get("n_days"),
    }


def render() -> str:
    with open(RESULTS) as f:
        data = json.load(f)

    # Splice in the FINRA short-squeeze result (run separately, lives in finra_short_result.json)
    finra = _load_finra_result()
    if finra is not None:
        data["results"]["Off-Exchange Short Squeeze"] = finra

    cost_sens = _load_cost_sensitivity()
    turnover = _load_turnover() or {}

    # If a strategy appears in cost_sens, prefer its 10bps row as the canonical entry
    # in the main table — the cost sweep ran AFTER the CUSIP cache was fully warm,
    # so its numbers are the most accurate (especially for Klarman/Druckenmiller).
    if cost_sens:
        for strat, runs in cost_sens["results"].items():
            default_run = next((r for r in runs if r.get("label") == "default 10bps" and not r.get("error")), None)
            if default_run is not None:
                # Re-map to the main-table schema
                data["results"][strat] = {
                    "cagr": default_run.get("cagr"),
                    "sharpe": default_run.get("sharpe"),
                    "sortino": None,
                    "max_drawdown": default_run.get("max_drawdown"),
                    "total_return": None,
                    "volatility": default_run.get("vol"),
                    "return_1y": default_run.get("return_1y"),
                    "benchmark_return_1y": None,
                    "alpha": default_run.get("alpha"),
                    "beta": default_run.get("beta"),
                    "n_trades": default_run.get("n_trades"),
                    "final_value": default_run.get("final_value"),
                }

    rows = []
    sorted_items = sorted(
        data["results"].items(),
        key=lambda kv: (kv[1].get("sharpe") if isinstance(kv[1].get("sharpe"), (int, float)) else -99),
        reverse=True,
    )
    for name, r in sorted_items:
        if r.get("error"):
            rows.append(
                f"<tr class='err'><td>{html.escape(name)}</td>"
                f"<td colspan='11'>ERROR — {html.escape(str(r['error']))[:200]}</td></tr>"
            )
            continue
        if name in NEW_STRATEGIES:
            flag = "<span class='chip new'>new</span>"
        else:
            flag = "<span class='chip base'>baseline</span>"
        cagr = r.get("cagr")
        sh = r.get("sharpe")
        so = r.get("sortino")
        dd = r.get("max_drawdown")
        ret_1y = r.get("return_1y")
        bench_1y = r.get("benchmark_return_1y")
        vol = r.get("volatility")
        alpha = r.get("alpha")
        beta = r.get("beta")
        ntr = r.get("n_trades")
        finv = r.get("final_value")
        rows.append(
            f"<tr>"
            f"<td class='name'>{flag} {html.escape(name)}</td>"
            f"<td class='{signed_pct_class(cagr)}'>{pct(cagr)}</td>"
            f"<td class='{signed_num_class(sh, 1)}'>{num(sh)}</td>"
            f"<td class='{signed_num_class(so, 1)}'>{num(so)}</td>"
            f"<td class='neg'>{pct(dd)}</td>"
            f"<td class='{signed_pct_class(ret_1y)}'>{pct(ret_1y)}</td>"
            f"<td class='neutral'>{pct(bench_1y)}</td>"
            f"<td>{pct(vol)}</td>"
            f"<td class='{signed_pct_class(alpha)}'>{pct(alpha)}</td>"
            f"<td>{num(beta)}</td>"
            f"<td>{ntr if ntr is not None else '—'}</td>"
            f"<td>{money(finv)}</td>"
            f"</tr>"
        )

    tier1_rows = "".join(
        f"<tr><td>{html.escape(n)}</td><td><code>{html.escape(e)}</code></td><td class='neg'>{html.escape(s)}</td></tr>"
        for n, e, s in TIER1_BLOCKED
    )
    tier3_rows = "".join(
        f"<tr><td>{html.escape(n)}</td><td>{html.escape(s)}</td></tr>"
        for n, s in TIER3_DEFERRED
    )

    # Alt-source table, grouped by Tier 1 strategy
    alt_rows = []
    last_strat = None
    for strat, src, kind, cost, endpoint, effort, notes in ALT_SOURCES:
        sep = " divider" if (last_strat is not None and strat != last_strat) else ""
        last_strat = strat
        kind_cls = {"FREE": "pos", "FREE-ish": "neutral", "FREE-scrape": "neutral",
                    "FREE-risky": "neutral", "PAID": "neg",
                    "PAID-free-tier": "neutral", "FREE quota": "neutral"}.get(kind, "neutral")
        alt_rows.append(
            f"<tr class='alt{sep}'>"
            f"<td>{html.escape(strat)}</td>"
            f"<td><b>{html.escape(src)}</b></td>"
            f"<td class='{kind_cls}'>{html.escape(kind)}</td>"
            f"<td>{html.escape(cost)}</td>"
            f"<td><code>{html.escape(endpoint)}</code></td>"
            f"<td>{html.escape(effort)}</td>"
            f"<td class='notes'>{html.escape(notes)}</td>"
            f"</tr>"
        )
    alt_table = "".join(alt_rows)

    # Turnover rows, sorted by turnover% descending
    sorted_turnover = sorted(
        turnover.items(),
        key=lambda kv: kv[1].get("turnover_pct_per_rebal") or 0,
        reverse=True,
    )
    turnover_rows = []
    for name, t in sorted_turnover:
        tu = t.get("turnover_pct_per_rebal")
        cls = "neg" if isinstance(tu, (int, float)) and tu > 50 else "neutral"
        tu_s = f"{tu:.0f}%" if isinstance(tu, (int, float)) else "—"
        turnover_rows.append(
            f"<tr><td>{html.escape(name)}</td>"
            f"<td>{t.get('n_trades','—')}</td>"
            f"<td>{t.get('avg_trades_per_rebalance','—')}</td>"
            f"<td class='{cls}'>{tu_s}</td>"
            f"<td>{t.get('basket_size_est','—')}</td>"
            f"<td>{t.get('n_events_est','—')}</td></tr>"
        )
    turnover_rows = "".join(turnover_rows)

    # Cost-sensitivity section
    cost_section = ""
    if cost_sens:
        sect_rows = []
        for strat, runs in cost_sens["results"].items():
            sect_rows.append(
                f"<tr class='cost-strat'><td colspan='6'><b>{html.escape(strat)}</b></td></tr>"
            )
            base_cagr = None
            for r in runs:
                if r.get("error"):
                    sect_rows.append(
                        f"<tr><td>{html.escape(r.get('label',''))}</td>"
                        f"<td colspan='5' class='neg'>ERROR — {html.escape(str(r['error']))[:100]}</td></tr>"
                    )
                    continue
                cagr = r.get("cagr")
                if base_cagr is None and isinstance(cagr, (int, float)):
                    base_cagr = cagr  # the first (gross) run is the reference
                shp = r.get("sharpe")
                dd = r.get("max_drawdown")
                ntr = r.get("n_trades")
                delta = ""
                if isinstance(cagr, (int, float)) and isinstance(base_cagr, (int, float)) and base_cagr != cagr:
                    delta = f" <span class='delta'>({(cagr - base_cagr)*100:+.2f} pp)</span>"
                sect_rows.append(
                    f"<tr><td class='cost-label'>{html.escape(r.get('label',''))}</td>"
                    f"<td>{r.get('total_cost_bps'):.1f}</td>"
                    f"<td class='{signed_pct_class(cagr)}'>{pct(cagr)}{delta}</td>"
                    f"<td>{num(shp)}</td>"
                    f"<td class='neg'>{pct(dd)}</td>"
                    f"<td>{ntr if ntr is not None else '—'}</td></tr>"
                )
        cost_section = f"""
  <h2>Cost-sensitivity sweep — what survives realistic execution costs</h2>
  <p class='sub'>Engine applies costs as: <code>(transaction_cost_bps + 2 × slippage_bps_per_side) × turnover</code> per rebalance.
  Comparing the FINRA strategy (high churn, 5018 trades) to three low-churn 13F mirrors so you can see how cost burns hit turnover-heavy strategies disproportionately.</p>
  <table>
    <thead><tr>
      <th>Cost regime</th><th>Total bps</th><th>CAGR</th><th>Sharpe</th><th>MaxDD</th><th>Trades</th>
    </tr></thead>
    <tbody>{''.join(sect_rows)}</tbody>
  </table>
  <div class='note'>
    <b>Interpretation:</b> 10bps is the engine default (≈ IBKR tiered commission + 2.5bps slippage per side on liquid mid-caps).
    20bps is conservative — typical mid-cap spread + small-account $1 min commission.
    35bps is pessimistic — sub-$1B market-cap, wide spread, microcap drag.
    For the FINRA short-squeeze strategy at 80%+ weekly turnover, the gross-vs-net spread is large and meaningful — that's the strategy's main risk before execution discipline.
  </div>
"""

    css = """
    html,body{background:#0f1117!important;color:#e6e6e6;font-family:'Inter','Segoe UI',Roboto,sans-serif;margin:0;padding:0;}
    *{box-sizing:border-box}
    a{color:#7ab8ff}
    .wrap{max-width:1180px;margin:0 auto;padding:32px 24px 64px}
    h1{font-size:26px;margin:0 0 6px}
    h2{font-size:18px;margin:34px 0 12px;color:#d8d8e0;border-bottom:1px solid #232735;padding-bottom:6px}
    .sub{color:#8a8fa3;font-size:13px;margin:0 0 8px}
    .badges{margin:10px 0 20px;display:flex;gap:8px;flex-wrap:wrap}
    .badge{background:#1a1d2b;border:1px solid #2a2f44;padding:4px 10px;border-radius:14px;font-size:12px;color:#cdd2e0}
    table{width:100%;border-collapse:collapse;background:#151824;border:1px solid #232735;border-radius:8px;overflow:hidden;font-size:13px}
    th,td{padding:9px 11px;text-align:right;border-bottom:1px solid #1d2030}
    th{background:#1a1d2b;color:#b9becf;text-align:right;font-weight:600;letter-spacing:.02em;font-size:12px}
    th:first-child,td.name,td:first-child{text-align:left}
    tr:hover td{background:#181b29}
    tr.err td{color:#ff8585;background:#28161a}
    td.pos{color:#5fd28b}
    td.neg{color:#ff6b6b}
    td.neutral{color:#a4abbd}
    .chip{display:inline-block;font-size:10.5px;padding:2px 7px;border-radius:9px;margin-right:8px;letter-spacing:.04em;text-transform:uppercase;font-weight:600}
    .chip.new{background:#1b4a30;color:#7ee5a4;border:1px solid #2b6644}
    .chip.base{background:#262936;color:#9aa1b8;border:1px solid #353b50}
    .note{background:#15182a;border:1px solid #232a40;padding:12px 14px;border-radius:6px;margin:8px 0 14px;font-size:13px;color:#b5bbcb;line-height:1.5}
    code{background:#1d2030;padding:1px 6px;border-radius:4px;font-size:12px;color:#c9d0e3}
    tr.alt td{font-size:12.5px;vertical-align:top}
    tr.alt td.notes{text-align:left;color:#b5bbcb;max-width:380px;line-height:1.45}
    tr.alt td:first-child{text-align:left;color:#9aa1b8}
    tr.divider td{border-top:1px solid #2a3050}
    tr.cost-strat td{background:#1a1d2b;color:#cdd2e0;font-size:13px;text-align:left;padding-top:11px;border-top:1px solid #2a3050}
    td.cost-label{text-align:left;color:#b9becf}
    .delta{color:#ff9d6b;font-size:11.5px;margin-left:6px}
    ol li{margin:3px 0}
    """

    period = f"{data['start'][:10]} → {data['end'][:10]}"
    html_doc = f"""<!doctype html>
<html><head>
<meta charset='utf-8'>
<title>IB Bot — New strategies, preliminary backtests</title>
<style>{css}</style>
</head>
<body>
<div class='wrap'>
  <h1>IB Bot — Tier 1–3 strategy expansion, preliminary backtests</h1>
  <p class='sub'>Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC · period {period} · $ {data['initial_capital']:,} initial · cached prices · 13F mirrors rebalance on actual filing dates</p>
  <div class='badges'>
    <span class='badge'>12 new 13F managers (SEC EDGAR)</span>
    <span class='badge'>1 new FINRA short signal (live + backtested)</span>
    <span class='badge'>1 new WSB sentiment signal (live, no backtest)</span>
  </div>

  <h2>Tier 2 — 13F mirror backtests (sorted by Sharpe, desc)</h2>
  <div class='note'>
    <b>Read with care.</b> Cached-price run on weights derived from SEC EDGAR 13F parses. Ticker-resolution improved this pass via batched OpenFIGI (Pabrai 3/25 → 8/25, Druckenmiller 41/66 → 40/66 useable). <b>Remaining gap on Druckenmiller (~21% AUM):</b> CINS-prefixed CUSIPs (foreign-domiciled issuers like CRH, JBS, Linde) that OpenFIGI with <code>exchCode=US</code> doesn't return; fixable in a follow-up by retrying without the exchange filter. Klarman's elevated 1y stat is driven by VST (+200% on AI power demand) — the data is right, the headline metric is just regime-specific.
  </div>
  <table>
    <thead><tr>
      <th>Strategy</th><th>CAGR</th><th>Sharpe</th><th>Sortino</th><th>MaxDD</th>
      <th>1y</th><th>SPY 1y</th><th>Vol</th><th>Alpha</th><th>β</th><th>Trades</th><th>Final</th>
    </tr></thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>

  <h2>Tier 1 — blocked by Quiver subscription tier</h2>
  <p class='sub'>Probed each candidate endpoint with a tiny request. Results:</p>
  <table>
    <thead><tr><th>Strategy</th><th>Endpoint</th><th>Status</th></tr></thead>
    <tbody>{tier1_rows}</tbody>
  </table>
  <div class='note'>
    Quiver's tiered access: base tier (congress / lobbying / contracts / 13F-strategies / strategies-holdings) is unlocked. Premium alt-data tier (WSB / patents / off-exchange short / app downloads / Google Trends / Twitter / insider trades) requires plan upgrade.
  </div>

  <h2>Alt-data sources besides Quiver (all liveness-verified 2026-05-18)</h2>
  <p class='sub'>For each blocked strategy: the best free and best paid alternatives. Free options exist for 6/8 — only app downloads and Twitter genuinely require paying someone. Effort is rough engineering hours.</p>
  <table>
    <thead><tr>
      <th>Strategy</th><th>Source</th><th>Cost tier</th><th>Cost $</th>
      <th>Endpoint</th><th>Effort</th><th>Notes</th>
    </tr></thead>
    <tbody>{alt_table}</tbody>
  </table>
  <div class='note'>
    <b>Recommended build order if you want to actually ship these</b> (each delivers a new live signal in under a day of work):
    <ol style='margin:8px 0 0 18px;line-height:1.7'>
      <li><b>ApeWisdom → WSB momentum strategy</b> — drop-in free, &lt;2h. Highest expected info gain per hour.</li>
      <li><b>FINRA short volume → off-exchange short squeeze strategy</b> — free CSV, &lt;2h to wire, signal is identical to what Quiver sells.</li>
      <li><b>Finnhub free tier OR scrape OpenInsider → insider cluster buys</b> — free or near-free, ~half-day. Cheaper-to-ship variant of the deferred Tier 3 SEC EDGAR build.</li>
      <li><b>pytrends → Google Trends momentum</b> — free, &lt;2h, watch for rate-limit flakiness in production.</li>
      <li><b>USPTO PatentsView → patent grants momentum</b> — free but 1–2 days (need assignee→ticker mapping table).</li>
      <li><b>Apptopia or Sensor Tower → app downloads strategy</b> — only justified after items 1–5 are paying off; ~$1k+/mo minimum.</li>
    </ol>
  </div>

  <h2>Tier 3 — SEC EDGAR + external strategies (deferred)</h2>
  <p class='sub'>These don't need Quiver but DO need net-new plumbing not in this session's scope:</p>
  <table>
    <thead><tr><th>Strategy</th><th>Reason deferred</th></tr></thead>
    <tbody>{tier3_rows}</tbody>
  </table>

  {cost_section}

  <h2>Turnover per rebalance — how much of the basket churns each cycle</h2>
  <p class='sub'>Higher turnover means cost assumptions matter more. The 13F mirrors are mostly low-turnover (1-15% per quarter); FINRA churns 80% of its basket every week.</p>
  <table>
    <thead><tr>
      <th>Strategy</th><th>Total trades (3yr)</th><th>Trades / rebal</th><th>Turnover / rebal</th><th>Basket size</th><th>Rebal events (3yr)</th>
    </tr></thead>
    <tbody>{turnover_rows}</tbody>
  </table>

  <h2>Live-only signals (no backtest possible)</h2>
  <div class='note'>
    <b>WSB Mentions Momentum</b> — ApeWisdom doesn't expose historical mention data, so a 3yr backtest isn't possible from this source. Signal is wired end-to-end and producing a sane top-10 today (NVDA, MSFT, AMD, META, GOOG, plus mid-cap risers like MRAM, MRVL, YOU, DTE, HD). Engine returns empty for any historical date, so backtests on the existing pipeline produce no signal — that's intentional. Recommended path: enable for paper-trading + log signal vs forward-realized returns for 4–8 weeks before sizing up. Reddit pushshift archive backfill is a separate workstream (~half-day) if you want a real backtest later.
  </div>

  <h2>What changed in the code</h2>
  <ul style='color:#b5bbcb;font-size:13.5px;line-height:1.7'>
    <li><code>sec_edgar.py</code> — 11 new CIKs in <code>FUND_CIK_MAP</code>; lowered 13F info-table size filter 5000→1500 bytes (was missing Himalaya at 4980); new <code>_openfigi_batch_lookup</code> (single POST for up to 100 CUSIPs, fixes the 25-CUSIP rate-limit storm)</li>
    <li><code>quiver_strategy_rules.py</code> — 12 new <code>13f_mirror</code> entries; 2 new <code>alternative_data</code> entries (FINRA short, WSB)</li>
    <li><code>quiver_engine.py</code> — 12 new <code>sec13F</code> entries; 2 new alt-data entries; new branches in <code>_get_raw_data_with_metadata_at_date</code> for <code>finra_short</code> and <code>apewisdom</code></li>
    <li><code>strategy_replicator.py</code> — generalized 13F dispatch (was hard-coded list of 3); per-strategy <code>top_n</code> support; new <code>get_strategy_config</code> branches for the two alt-data strategies</li>
    <li><code>finra_short.py</code> — <b>new module</b>. FINRA daily CNMS short-volume fetcher with disk cache + NASDAQ Trader ETF-flag universe filter</li>
    <li><code>apewisdom.py</code> — <b>new module</b>. ApeWisdom WSB mentions fetcher with per-UTC-day cache and growth signal</li>
    <li><code>strategies_config.json</code> — 14 new entries (all category=experimental, enabled=false)</li>
  </ul>

  <h2>Suggested next steps</h2>
  <ul style='color:#b5bbcb;font-size:13.5px;line-height:1.7'>
    <li>Promote the top-Sharpe new mirrors (Coatue, Klarman, Tiger Global, Tepper) to a paper-traded ensemble at small weight, then evaluate after 1 filing cycle</li>
    <li>If Quiver alt-data tier upgrade is on the table, run a separate cost/benefit — WSB momentum and patents are the most-cited edges in the literature</li>
    <li>Build the Form 4 cluster-buy strategy as a separate workstream — it's the highest-evidence ungated edge and ~150 LOC of SEC EDGAR parsing</li>
    <li>Investigate why Druckenmiller and Pabrai have weak metrics — likely SEC EDGAR Value parsing failed for some quarters; check holdings parse</li>
  </ul>
</div>
</body></html>"""

    with open(OUT, "w") as f:
        f.write(html_doc)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    render()
