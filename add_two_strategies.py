"""
Add Michael Burry and Bill Ackman strategies to plot_data.json.
These are the only 2 that work from the 5 missing (others need premium API access).
"""
import json
import os
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

# Only the 2 strategies that work
STRATEGIES_TO_ADD = [
    "Michael Burry",
    "Bill Ackman", 
]

print("=" * 80)
print("Adding 2 working strategies to plot_data.json")
print("=" * 80)

# Load current plot_data
plot_path = ".cache/plot_data.json"
plot_data = json.loads(open(plot_path).read())
print(f"Current strategies: {len(plot_data['strategies'])}")

from rebalancing_backtest_engine import RebalancingBacktestEngine

api_key = os.getenv("QUIVER_API_KEY")
price_source = os.getenv("PRICE_SOURCE", "ib")

bt = RebalancingBacktestEngine(
    quiver_api_key=api_key,
    initial_capital=100000,
    transaction_cost_bps=0.0,
    price_source=price_source,
)

min_start_date = datetime(2020, 1, 1)

def normalize_equity_curve(equity_curve_df, initial_value=100):
    if equity_curve_df is None or equity_curve_df.empty:
        return pd.DataFrame()
    if 'equity' in equity_curve_df.columns:
        value_col = 'equity'
    elif 'portfolio_value' in equity_curve_df.columns:
        value_col = 'portfolio_value'
    else:
        return pd.DataFrame()
    first_value = equity_curve_df[value_col].iloc[0]
    if first_value <= 0:
        first_value = 1.0
    equity_curve_df = equity_curve_df.copy()
    equity_curve_df['normalized'] = (equity_curve_df[value_col] / first_value) * initial_value
    return equity_curve_df

added = 0
for strategy_name in STRATEGIES_TO_ADD:
    print(f"\n{strategy_name}...")
    
    try:
        result = bt.run_rebalancing_backtest(
            strategy_name=strategy_name,
            start_date=min_start_date,
            end_date=datetime.now(),
            lookback_days_override=None,
        )
        
        if result and 'equity_curve' in result and 'error' not in result:
            equity_curve = normalize_equity_curve(result['equity_curve'], 100)
            
            if not equity_curve.empty:
                equity_curve_weekly = equity_curve.resample('W-FRI').last().fillna(method='ffill')
                
                cagr = result.get('cagr', 0) * 100
                sharpe = result.get('sharpe_ratio', 0)
                max_dd = result.get('max_drawdown', 0) * 100
                
                plot_data['strategies'][strategy_name] = {
                    "name": strategy_name,
                    "dates": equity_curve_weekly.index.strftime('%Y-%m-%d').tolist(),
                    "values": equity_curve_weekly['normalized'].round(2).tolist(),
                    "start_date": min_start_date.isoformat(),
                    "cagr": float(cagr),
                    "sharpe": float(sharpe),
                    "max_drawdown": float(max_dd)
                }
                
                added += 1
                print(f"  [OK] {len(equity_curve_weekly)} points, CAGR={cagr:.1f}%")
            else:
                print(f"  [SKIP] Empty equity curve")
        elif 'error' in result:
            print(f"  [ERROR] {result['error']}")
        else:
            print(f"  [SKIP] No result")
            
    except Exception as e:
        print(f"  [ERROR] {e}")
        continue

print(f"\n{'='*80}")
print(f"Added {added}/{len(STRATEGIES_TO_ADD)} strategies")
print(f"Total strategies now: {len(plot_data['strategies'])}")

# Save updated plot_data
plot_data["updated_at"] = datetime.now().isoformat()
with open(plot_path, 'w') as f:
    json.dump(plot_data, f, indent=2)

print(f"[OK] Saved to {plot_path}")
