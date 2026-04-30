"""Re-run Michael Burry backtest with fixed SEC parser (no options/preferred)."""
import json
import os
from datetime import datetime

# Clear all SEC Edgar cache to ensure fresh data
import glob
for f in glob.glob('.cache/sec_edgar/holdings_CIK0001649339_*.pkl'):
    os.remove(f)
    print(f"Removed cache: {f}")

from rebalancing_backtest_engine import RebalancingBacktestEngine
from quiver_strategy_rules import QuiverStrategyRules

# Initialize
api_key = os.getenv("QUIVER_API_KEY", "")
backtest_engine = RebalancingBacktestEngine(
    quiver_api_key=api_key,
    initial_capital=100000
)

# Run backtest from 2016 (matching Quiver's start date)
print("\nRunning Michael Burry backtest (2016-present, stock only)...")
print("=" * 60)

result = backtest_engine.run_rebalancing_backtest(
    strategy_name="Michael Burry",
    start_date="2016-02-17",  # Quiver's start date
    end_date=datetime.now().strftime("%Y-%m-%d")
)

if "error" in result:
    print(f"ERROR: {result['error']}")
else:
    # Print available keys for debugging
    print(f"\nAvailable result keys: {list(result.keys())}")
    
    cagr = result.get('cagr', 0)
    sharpe = result.get('sharpe_ratio', result.get('sharpe', 0))
    max_dd = result.get('max_drawdown', 0)
    volatility = result.get('volatility', 0)
    
    print(f"\nBacktest Results:")
    print(f"  CAGR: {cagr * 100:.2f}%")
    print(f"  Sharpe: {sharpe:.2f}")
    print(f"  Max Drawdown: {max_dd * 100:.2f}%")
    print(f"  Volatility: {volatility * 100:.2f}%")
    
    equity_curve = result.get('equity_curve', [])
    # Handle DataFrame or Series equity curve
    import pandas as pd
    if isinstance(equity_curve, (pd.DataFrame, pd.Series)):
        if isinstance(equity_curve, pd.DataFrame):
            # Get first column if DataFrame
            dates = list(equity_curve.index.astype(str))
            values = list(equity_curve.iloc[:, 0].values)
        else:
            dates = list(equity_curve.index.astype(str))
            values = list(equity_curve.values)
    else:
        values = list(equity_curve) if equity_curve else []
        dates = [str(d) for d in result.get('dates', [])]
    
    print(f"  Equity curve points: {len(values)}")
    print(f"  Date points: {len(dates)}")
    
    print(f"\nQuiver Reference (for comparison):")
    print(f"  CAGR: 30.45%")
    print(f"  Sharpe: 0.96")
    print(f"  Max Drawdown: -45.66%")
    
    # Update plot_data.json
    plot_path = '.cache/plot_data.json'
    if os.path.exists(plot_path) and len(values) > 0:
        with open(plot_path, 'r') as f:
            plot_data = json.load(f)
        
        # Normalize equity curve to start at 100
        initial = values[0] if values[0] != 0 else 1
        normalized = [v / initial * 100 for v in values]
        
        plot_data['strategies']['Michael Burry'] = {
            'name': 'Michael Burry',
            'dates': [str(d)[:10] for d in dates],
            'values': normalized,
            'start_date': '2016-02-17',
            'cagr': cagr * 100,
            'sharpe': sharpe,
            'max_drawdown': max_dd * 100
        }
        
        with open(plot_path, 'w') as f:
            json.dump(plot_data, f, indent=2)
        
        print(f"\n[OK] Updated plot_data.json with corrected Michael Burry data")
