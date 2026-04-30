"""Test Michael Burry with delta-adjusted option exposure."""
import json
import os
import glob
import pandas as pd
from datetime import datetime

# Clear SEC Edgar cache
for f in glob.glob('.cache/sec_edgar/holdings_*.pkl'):
    try: os.remove(f)
    except: pass

print("=" * 70)
print("TEST: DELTA-ADJUSTED OPTION EXPOSURE")
print("=" * 70)

from sec_edgar import SECEdgarClient

# Test delta-adjusted mode (new default)
print("\n1. CURRENT HOLDINGS - DELTA-ADJUSTED MODE (default)")
print("-" * 60)
os.environ['SEC_13F_OPTIONS_MODE'] = 'delta_adjusted'
os.environ['SEC_13F_PUT_DELTA'] = '0.40'
os.environ['SEC_13F_CALL_DELTA'] = '0.40'

# Clear cache
for f in glob.glob('.cache/sec_edgar/holdings_CIK0001649339_*.pkl'):
    try: os.remove(f)
    except: pass

client = SECEdgarClient()
holdings = client.get_latest_holdings('Scion Asset Management')

if not holdings.empty:
    print(f"{'Ticker':<8} {'Value':<18} {'Delta':<8} {'Type':<8} {'Original':<18}")
    print("-" * 60)
    
    total_long = 0
    total_short = 0
    
    for _, row in holdings.iterrows():
        ticker = row.get('Ticker') or row.get('TickerFromName', 'N/A')
        value = row.get('Value', 0)
        delta = row.get('Delta', 1.0)
        exp_type = row.get('ExposureType', 'LONG')
        put_call = row.get('PutCall', '')
        
        # Calculate original value (before delta adjustment)
        if put_call:
            if delta != 0:
                original = abs(value / delta)
            else:
                original = abs(value)
        else:
            original = abs(value)
        
        if value < 0:
            total_short += abs(value)
        else:
            total_long += value
            
        print(f"{ticker:<8} ${value:>15,.0f}  {delta:>6.2f}  {exp_type:<8} ${original:>15,.0f}")
    
    print("-" * 60)
    print(f"Total LONG exposure:  ${total_long:>15,.0f}")
    print(f"Total SHORT exposure: ${total_short:>15,.0f}")
    print(f"NET exposure:         ${total_long - total_short:>15,.0f}")
    print(f"Gross exposure:       ${total_long + total_short:>15,.0f}")

# Run backtest
print("\n" + "=" * 70)
print("RUNNING BACKTEST WITH DELTA-ADJUSTED EXPOSURE")
print("=" * 70)

# Clear cache for fresh backtest
for f in glob.glob('.cache/sec_edgar/holdings_*.pkl'):
    try: os.remove(f)
    except: pass

from rebalancing_backtest_engine import RebalancingBacktestEngine

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
    
    print(f"\nBACKTEST RESULTS (delta-adjusted):")
    print(f"  CAGR: {cagr * 100:.2f}%")
    print(f"  Sharpe: {sharpe:.2f}")
    print(f"  Max Drawdown: {max_dd * 100:.2f}%")

# Final comparison
print("\n" + "=" * 70)
print("FINAL COMPARISON")
print("=" * 70)
print(f"{'Approach':<40} {'CAGR':<12} {'Max DD':<12}")
print("-" * 65)
print(f"{'Filter options (stock only)':<40} {'20.76%':<12} {'-38.62%':<12}")
print(f"{'Options 100% exposure (PUT=SHORT)':<40} {'15.26%':<12} {'-50.92%':<12}")
print(f"{'Delta-adjusted (40% exposure)':<40} {f'{cagr*100:.2f}%':<12} {f'{max_dd*100:.2f}%':<12}")
print(f"{'Quiver reference':<40} {'30.45%':<12} {'-52.10%':<12}")
