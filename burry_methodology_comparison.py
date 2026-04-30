"""
MICHAEL BURRY - COMPLETE METHODOLOGY COMPARISON
================================================

This script shows exactly how trades are calculated in each approach.
"""
import json
import pandas as pd
from datetime import datetime

print("=" * 80)
print("MICHAEL BURRY - METHODOLOGY DEEP DIVE")
print("=" * 80)

# -----------------------------------------------------------------------------
# 1. HOW OUR CURRENT BACKTEST CALCULATES TRADES
# -----------------------------------------------------------------------------
print("""
1. CURRENT METHODOLOGY (SEC EDGAR + Options Filtered)
-----------------------------------------------------

a) DATA SOURCE: SEC EDGAR 13F filings
   - Fetches 13F-HR filings directly from SEC
   - Uses `get_holdings_as_of_date()` for each rebalance date
   - NO lookahead: only uses filings available at that date

b) FILTERING:
   - EXCLUDES: PUT options (e.g., NVDA Put)
   - EXCLUDES: CALL options (e.g., HAL Call)  
   - EXCLUDES: Preferred shares (e.g., BRUKER 6.375 PREF SER A)
   - INCLUDES: Only common stock positions

c) WEIGHTING: VALUE-WEIGHTED (portfolio_mirror)
   - Each position weighted by its dollar value in the filing
   - Formula: weight[ticker] = Value[ticker] / Total_Value
   - Example: If LULU = $17M and total = $55M, LULU weight = 31%

d) REBALANCE: Quarterly (45 days after quarter end)
   - Matches SEC 13F filing schedule
""")

# Show current holdings
from sec_edgar import SECEdgarClient
client = SECEdgarClient()

# Clear cache to get fresh filtered data
import glob
import os
for f in glob.glob('.cache/sec_edgar/holdings_CIK0001649339_*.pkl'):
    os.remove(f)

holdings = client.get_latest_holdings('Scion Asset Management')
print("CURRENT HOLDINGS (stock only, options/preferred filtered):")
print("-" * 60)
if not holdings.empty:
    total_val = holdings['Value'].sum() if 'Value' in holdings.columns else 0
    for _, row in holdings.iterrows():
        ticker = row.get('Ticker') or row.get('TickerFromName', 'N/A')
        name = str(row.get('Name', ''))[:30]
        value = row.get('Value', 0)
        weight = (value / total_val * 100) if total_val > 0 else 0
        print(f"  {ticker:<8} {name:<30} ${value:>12,.0f}  ({weight:>5.1f}%)")
    print(f"\n  Total: ${total_val:,.0f}")
    print(f"  Positions: {len(holdings)}")

# -----------------------------------------------------------------------------
# 2. HOW LEGACY BACKTEST CALCULATED (WITH OPTIONS)
# -----------------------------------------------------------------------------
print("""

2. LEGACY METHODOLOGY (SEC EDGAR + Options INCLUDED)
-----------------------------------------------------

a) DATA SOURCE: Same SEC EDGAR 13F filings

b) FILTERING: NONE
   - INCLUDED: PUT options (NVDA Put, PLTR Put)
   - INCLUDED: CALL options (HAL Call, PFE Call)
   - INCLUDED: Preferred shares
   
c) PROBLEM: Options treated as stock ownership
   - NVDA PUT = Bet that NVDA goes DOWN
   - But backtest treated it as LONG NVDA
   - Result: Massive inflated returns when NVDA went up 2000%
   
d) WEIGHTING: VALUE-WEIGHTED (same as current)
   
e) Start Date: 2020 (shorter period, better performance period)
""")

# -----------------------------------------------------------------------------
# 3. HOW QUIVER CALCULATES (BLACK BOX)
# -----------------------------------------------------------------------------
print("""

3. QUIVER METHODOLOGY (from their website)
------------------------------------------

Description: "The Michael Burry Strategy attempts to mirror the portfolio 
of Michael Burry's Scion Asset Management using 13F filings and is 
rebalanced when new filings are reported."

a) DATA SOURCE: SEC EDGAR 13F filings (same as us)

b) FILTERING: Unknown, but likely:
   - May include some option exposure
   - May handle options differently (delta-adjusted?)
   
c) WEIGHTING: Unknown, but likely VALUE-WEIGHTED

d) Start Date: 2016-02-17

e) Key Metrics:
   - CAGR: 30.45%
   - Max DD: -52.10%
   - Trades: 652
   - Win Rate: 71.34%
""")

# -----------------------------------------------------------------------------
# 4. COMPARISON TABLE
# -----------------------------------------------------------------------------
print("""
4. CAGR COMPARISON
------------------
""")

# Load all sources
with open('.cache/plot_data.json', 'r') as f:
    current = json.load(f)
current_burry = current.get('strategies', {}).get('Michael Burry', {})

try:
    with open('.cache/backups/plot_data_23strategies_FINAL.json', 'r') as f:
        legacy = json.load(f)
    legacy_burry = legacy.get('strategies', {}).get('Michael Burry', {})
except:
    legacy_burry = {}

with open('.cache/quiver_strategies_site.json', 'r') as f:
    quiver = json.load(f)
quiver_burry = quiver.get('strategies', {}).get('Michael Burry', {})

print(f"{'Metric':<20} {'Current':<15} {'Legacy':<15} {'Quiver':<15}")
print("-" * 65)
print(f"{'CAGR':<20} {current_burry.get('cagr', 0):>12.2f}%  {legacy_burry.get('cagr', 0):>12.2f}%  {quiver_burry.get('cagr', 'N/A'):>12}")
print(f"{'Sharpe':<20} {current_burry.get('sharpe', 0):>12.2f}   {legacy_burry.get('sharpe', 0):>12.2f}   {quiver_burry.get('sharpe_ratio', 'N/A'):>12}")
print(f"{'Max Drawdown':<20} {current_burry.get('max_drawdown', 0):>12.2f}%  {legacy_burry.get('max_drawdown', 0):>12.2f}%  {quiver_burry.get('max_drawdown', 'N/A'):>12}")
print(f"{'Start Date':<20} {'2016-02-17':>12}   {'2020-01-03':>12}   {'2016-02-17':>12}")
print(f"{'Data Points':<20} {len(current_burry.get('values', [])):>12}   {len(legacy_burry.get('values', [])):>12}   {'N/A':>12}")
print(f"{'Options Filtered':<20} {'YES':>12}   {'NO':>12}   {'Unknown':>12}")

# -----------------------------------------------------------------------------
# 5. WHY 10% GAP BETWEEN CURRENT AND QUIVER
# -----------------------------------------------------------------------------
print("""

5. WHY ~10% GAP BETWEEN CURRENT (20.76%) AND QUIVER (30.45%)?
-------------------------------------------------------------

Possible reasons:

a) MISSING QUARTERS:
   - Our backtest shows n=0 positions in some quarters
   - Burry was 100% in options/cash during those periods
   - We hold cash (0% return), Quiver may do something different

b) OPTION EXPOSURE:
   - Quiver might include some delta-adjusted option exposure
   - A $186M NVDA PUT is NOT the same as being short $186M of NVDA
   - But it's also not 0 exposure

c) PRICE SOURCES:
   - We use Yahoo Finance
   - Quiver likely uses Bloomberg or FactSet

d) TIMING DIFFERENCES:
   - We rebalance on fixed schedule (45 days after quarter end)
   - Quiver says "when new filings are reported" (could be earlier)

e) PORTFOLIO CONSTRUCTION:
   - Quiver might use different top-N selection
   - Quiver might have different value calculations
""")

print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)
print("""
- Legacy 72.77% CAGR was WRONG (options treated as stock)
- Current 20.76% CAGR is MORE ACCURATE (stock-only)
- Quiver 30.45% CAGR is their reference (may include some option exposure)

Bill Ackman shows our methodology is correct:
  - Our CAGR: 17.63%
  - Quiver CAGR: 16.76%
  - Difference: <1% (excellent match!)

The Burry gap exists because he uses OPTIONS heavily, which we filter out.
""")
