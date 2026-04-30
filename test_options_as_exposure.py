"""Test Michael Burry with options treated as stock exposure (PUT=SHORT, CALL=LONG)."""
import json
import os
import glob
import pandas as pd
from datetime import datetime

# Clear SEC Edgar cache
for f in glob.glob('.cache/sec_edgar/holdings_CIK0001649339_*.pkl'):
    os.remove(f)

print("=" * 70)
print("TEST: OPTIONS AS STOCK EXPOSURE (PUT=SHORT, CALL=LONG)")
print("=" * 70)

# First, show current holdings in both modes
from sec_edgar import SECEdgarClient

print("\n1. CURRENT HOLDINGS - FILTER MODE (default)")
print("-" * 50)
os.environ['SEC_13F_OPTIONS_MODE'] = 'filter'
# Need to clear cache to get fresh data
for f in glob.glob('.cache/sec_edgar/holdings_CIK0001649339_*.pkl'):
    try: os.remove(f)
    except: pass

client = SECEdgarClient()
holdings_filter = client.get_latest_holdings('Scion Asset Management')
if not holdings_filter.empty:
    for _, row in holdings_filter.iterrows():
        ticker = row.get('Ticker') or row.get('TickerFromName', 'N/A')
        value = row.get('Value', 0)
        print(f"  {ticker:<8} ${value:>15,.0f}  LONG")
    print(f"  Total positions: {len(holdings_filter)}")

print("\n2. CURRENT HOLDINGS - EXPOSURE MODE (PUT=SHORT, CALL=LONG)")
print("-" * 50)
os.environ['SEC_13F_OPTIONS_MODE'] = 'as_exposure'
# Clear cache again
for f in glob.glob('.cache/sec_edgar/holdings_CIK0001649339_*.pkl'):
    try: os.remove(f)
    except: pass

client2 = SECEdgarClient()
holdings_exposure = client2.get_latest_holdings('Scion Asset Management')
if not holdings_exposure.empty:
    total_long = 0
    total_short = 0
    for _, row in holdings_exposure.iterrows():
        ticker = row.get('Ticker') or row.get('TickerFromName', 'N/A')
        value = row.get('Value', 0)
        exp_type = row.get('ExposureType', 'LONG')
        if value < 0:
            total_short += abs(value)
            print(f"  {ticker:<8} ${value:>15,.0f}  SHORT")
        else:
            total_long += value
            print(f"  {ticker:<8} ${value:>15,.0f}  LONG")
    print(f"\n  Total LONG: ${total_long:,.0f}")
    print(f"  Total SHORT: ${total_short:,.0f}")
    print(f"  Net exposure: ${total_long - total_short:,.0f}")
    print(f"  Positions: {len(holdings_exposure)}")

# Now run backtest with exposure mode
print("\n" + "=" * 70)
print("RUNNING BACKTEST WITH OPTIONS AS EXPOSURE")
print("=" * 70)

from rebalancing_backtest_engine import RebalancingBacktestEngine

# Clear cache again for fresh backtest
for f in glob.glob('.cache/sec_edgar/holdings_*.pkl'):
    try: os.remove(f)
    except: pass

api_key = os.getenv("QUIVER_API_KEY", "")
backtest_engine = RebalancingBacktestEngine(
    quiver_api_key=api_key,
    initial_capital=100000
)

result = backtest_engine.run_rebalancing_backtest(
    strategy_name="Michael Burry",
    start_date="2016-02-17",
    end_date=datetime.now().strftime("%Y-%m-%d")
)

if "error" in result:
    print(f"ERROR: {result['error']}")
else:
    cagr = result.get('cagr', 0)
    sharpe = result.get('sharpe_ratio', 0)
    max_dd = result.get('max_drawdown', 0)
    
    print(f"\nBACKTEST RESULTS (options as exposure):")
    print(f"  CAGR: {cagr * 100:.2f}%")
    print(f"  Sharpe: {sharpe:.2f}")
    print(f"  Max Drawdown: {max_dd * 100:.2f}%")

# Compare all three approaches
print("\n" + "=" * 70)
print("COMPARISON")
print("=" * 70)
print(f"{'Approach':<35} {'CAGR':<15}")
print("-" * 50)
print(f"{'Filter options (current)':<35} {'20.76%':<15}")
print(f"{'Options as exposure (new)':<35} {f'{cagr * 100:.2f}%':<15}")
print(f"{'Include options as stock (legacy)':<35} {'72.77%':<15}")
print(f"{'Quiver reference':<35} {'30.45%':<15}")

# Reset to filter mode
os.environ['SEC_13F_OPTIONS_MODE'] = 'filter'
