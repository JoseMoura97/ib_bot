### IB Bot — Full Summary (comparisons + trading rules)

#### Current state
- **Strategy metadata + Quiver benchmarks**: scraped from `https://www.quiverquant.com/strategies/` into `.cache/quiver_strategies_site.json` (About + Key Metrics).
- **Signals**: fetched via Quiver API (raw feeds and/or `beta/strategies/holdings` time-series) in `quiver_engine.py`.
- **Pricing**: `backtest_engine.py` supports `PRICE_SOURCE=yfinance|ib|auto` with disk caching for both sources.
- **Backtesting**: `rebalancing_backtest_engine.py` runs rolling, rebalance-based replication with long/short support and now prints optional progress bars.
- **Rules**: Congress/committee/LS lookback drift is unified: **120d** is now the single source of truth in `quiver_strategy_rules.py` and read by `strategy_replicator.py`.
- **“Other metrics” added**: the backtest now computes additional stats (beta/alpha/IR/treynor vs **SPY**, win rate, avg win/loss, std dev, 1d/30d/1y returns, trades).

---

#### Trading rules (what we implement)
Source of truth:
- **Scheduling + defaults**: `quiver_strategy_rules.py`
- **Replication knobs (basket size, etc.)**: `strategy_replicator.py` (now reads lookback from rules)
- **Execution**: `rebalancing_backtest_engine.py`

| Strategy | Signal source | Selection / universe | Weighting | Rebalance | Lookback | Notes |
|---|---|---|---|---|---:|---|
| Congress Buys | Bulk congress trades | Top **10** purchases (all Congress) | $ size (Amount/Range) | Weekly (Mon) | 120 | Long-only |
| Congress Sells | Bulk congress trades | Top **10** sales (all Congress) | $ size (Amount/Range) | Weekly (Mon) | 120 | Long-only (matches Quiver page naming, not a short book) |
| Congress Long-Short | Bulk congress trades | Long **top 20 buys**, short **top 20 sells** | Transaction-size | Weekly (Mon) | 120 | 130/30 exposure |
| U.S. House Long-Short | Bulk congress trades | Long **top 10 House buys**, short **top 10 House sells** | Count/frequency | Weekly (Mon) | 120 | 130/30 exposure |
| Transportation and Infra. Committee (House) | Bulk congress trades | Committee-member purchases, top **10** | $ size | Weekly (Mon) | 120 | Committee inferred from Quiver naming; implemented as “committee strategy family” |
| Nancy Pelosi | Bulk congress trades | Mirror traded tickers (incl family) | Equal | **On trade dates** | 365 | Event-driven rebalance dates (not daily approximation) |
| Dan Meuser | Bulk congress trades | Mirror traded tickers (incl family) | Equal | On trade dates | 365 |  |
| Josh Gottheimer | Bulk congress trades | Mirror traded tickers (incl family) | Equal | On trade dates | 365 |  |
| Donald Beyer | Bulk congress trades | Mirror traded tickers (incl family) | Equal | On trade dates | 365 |  |
| Sheldon Whitehouse | Bulk congress trades | Mirror traded tickers (incl family) | Equal | On trade dates | 365 |  |
| Top Lobbying Spenders | Lobbying feed / holdings | Top **10** by trailing spend | Equal | Monthly (day 1) | 90 | If holdings time-series exists, we prefer Quiver weights snapshot |
| Lobbying Spending Growth | Lobbying feed / holdings | Top by QoQ growth | Equal | Monthly (day 1) | 90 | Same holdings preference behavior |
| Top Gov Contract Recipients | Contracts / holdings | Top **20** recipients | Contract value | Monthly (day 1) | 90 | Same holdings preference behavior |
| Sector Weighted DC Insider | Holdings time-series | Provided | Provided | Monthly (day 1) | — | Uses Quiver holdings snapshot when available |
| WSB Top 10 / Analyst Long / House Natural Resources / Energy & Commerce (House) / Homeland Security (Senate) | Holdings time-series | Provided | Provided | Weekly/Monthly (per rule) | — | Designed to follow Quiver holdings snapshots (closest match) |
| Insider Purchases | Insider feed / holdings | Top **10** proprietary score | Equal | Weekly (Mon) | 90 | Uses Quiver holdings snapshot when available; otherwise uses underlying feed |

---

#### Comparison table (Quiver vs our backtests) — core metrics
These are the latest recorded comparisons for **CAGR / Sharpe / MaxDD** (from our local runs) vs Quiver site metrics.

| Strategy | Status | Q Start | Q_CAGR | Our_CAGR | Diff | Q_Sharpe | Our_Sharpe | Diff | Q_MaxDD | Our_MaxDD | Diff |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Congress Buys | done | 2020-04-01 | 35.13% | 29.00% | -6.13% | 1.059 | 1.136 | 0.077 | -22.80% | -34.62% | -11.82% |
| Congress Sells | done | 2020-04-01 | 22.46% | 13.28% | -9.18% | 0.724 | 0.480 | -0.244 | -26.40% | -27.17% | -0.77% |
| Congress Long-Short | done | 2020-04-01 | 32.29% | 34.01% | 1.72% | 0.904 | 1.013 | 0.109 | -24.60% | -30.41% | -5.81% |
| U.S. House Long-Short | done | 2020-04-01 | 32.08% | 26.11% | -5.97% | 0.908 | 0.929 | 0.021 | -24.30% | -29.55% | -5.25% |
| Transportation and Infra. Committee (House) | done | 2020-04-01 | 33.96% | 31.81% | -2.15% | 1.104 | 1.207 | 0.103 | -39.90% | -35.28% | 4.62% |
| Energy and Commerce Committee (House) | done | 2020-04-01 | 19.14% | 33.87% | 14.73% | 0.605 | 1.292 | 0.687 | -39.90% | -33.93% | 5.97% |
| Homeland Security Committee (Senate) | done | 2020-04-01 | 12.32% | 6.92% | -5.40% | 0.384 | 0.209 | -0.175 | -32.90% | -51.28% | -18.38% |
| Top Lobbying Spenders | done | 2009-03-01 | 16.67% | 17.26% | 0.59% | 0.736 | 0.867 | 0.131 | -28.80% | -33.56% | -4.76% |
| Lobbying Spending Growth | done | 2009-03-01 | 26.61% | 21.55% | -5.06% | 0.864 | 0.758 | -0.106 | -42.80% | -44.38% | -1.58% |
| Top Gov Contract Recipients | done | 2009-03-01 | 19.37% | 19.01% | -0.36% | 0.769 | 0.873 | 0.104 | -41.20% | -41.61% | -0.41% |
| Sector Weighted DC Insider | done | 2020-04-01 | 24.05% | 24.43% | 0.38% | 0.994 | 1.318 | 0.324 | -18.70% | -18.17% | 0.53% |
| Nancy Pelosi | done | 2014-05-16 | 21.06% | 44.13% | 23.07% | 0.733 | 1.090 | 0.357 | -37.40% | -33.45% | 3.95% |
| Dan Meuser | done | 2019-08-14 | 38.58% | 32.79% | -5.79% | 1.037 | 0.829 | -0.208 | -43.30% | -60.80% | -17.50% |
| Josh Gottheimer | done | 2019-01-01 | 21.11% | 15.51% | -5.60% | 0.652 | 0.605 | -0.047 | -33.70% | -35.71% | -2.01% |
| Donald Beyer | done | 2016-05-09 | 20.07% | 12.65% | -7.42% | 0.728 | 0.477 | -0.251 | -32.50% | -32.54% | -0.04% |
| Sheldon Whitehouse | done | 2014-02-28 | 18.38% | 11.13% | -7.25% | 0.711 | 0.471 | -0.240 | -30.60% | -37.20% | -6.60% |
| Insider Purchases | done | 2014-01-01 | 18.67% | 34.37% | 15.70% | 0.540 | 1.193 | 0.653 | -52.90% | -34.68% | 18.22% |

---

#### “Other metrics” (beta/alpha/IR/treynor/win-rate/trades) vs SPY
We compute these now, benchmarked vs **SPY** using daily returns alignment and a standard RF \(2% annualized\).

How to generate a full table for all strategies:

```powershell
$env:PYTHONUNBUFFERED='1'
$env:PRICE_SOURCE='auto'   # or 'ib'
$env:PROGRESS='0'
& "venv_stable\Scripts\python.exe" -u validate_quiver_replication.py
& "venv_stable\Scripts\python.exe" print_summary_table.py
```

Notes:
- Validation writes/merges to `.cache/last_validation_results.json` so you can run strategies incrementally.
- Quiver’s “Total Trades” may not match our “trades” proxy; our current implementation counts **position weight changes across rebalance events**.

