"""Re-run all 13F strategy backtests with fixed SEC parser (no options/preferred)."""
import json
import os
import glob
import pandas as pd
from datetime import datetime

from rebalancing_backtest_engine import RebalancingBacktestEngine
from quiver_strategy_rules import QuiverStrategyRules

# Clear SEC Edgar cache for all funds
for f in glob.glob('.cache/sec_edgar/holdings_*.pkl'):
    os.remove(f)
    print(f"Removed cache: {f}")

# Initialize
api_key = os.getenv("QUIVER_API_KEY", "")
backtest_engine = RebalancingBacktestEngine(
    quiver_api_key=api_key,
    initial_capital=100000
)

# 13F strategies to re-run
strategies = {
    "Michael Burry": {"start": "2016-02-17", "quiver_cagr": 30.45},
    "Bill Ackman": {"start": "2015-02-18", "quiver_cagr": 16.76},
    "Howard Marks": {"start": "2015-02-17", "quiver_cagr": 14.49},
}

# Load existing plot data
plot_path = '.cache/plot_data.json'
with open(plot_path, 'r') as f:
    plot_data = json.load(f)

results_summary = []

for strategy_name, config in strategies.items():
    print(f"\n{'='*60}")
    print(f"Running {strategy_name} backtest ({config['start']}-present, stock only)...")
    print('='*60)
    
    result = backtest_engine.run_rebalancing_backtest(
        strategy_name=strategy_name,
        start_date=config['start'],
        end_date=datetime.now().strftime("%Y-%m-%d")
    )
    
    if "error" in result:
        print(f"ERROR: {result['error']}")
        results_summary.append({
            "strategy": strategy_name,
            "our_cagr": "ERROR",
            "quiver_cagr": config['quiver_cagr']
        })
        continue
    
    cagr = result.get('cagr', 0)
    sharpe = result.get('sharpe_ratio', 0)
    max_dd = result.get('max_drawdown', 0)
    
    print(f"\nResults:")
    print(f"  Our CAGR: {cagr * 100:.2f}%")
    print(f"  Quiver CAGR: {config['quiver_cagr']}%")
    print(f"  Sharpe: {sharpe:.2f}")
    print(f"  Max Drawdown: {max_dd * 100:.2f}%")
    
    results_summary.append({
        "strategy": strategy_name,
        "our_cagr": f"{cagr * 100:.2f}%",
        "quiver_cagr": f"{config['quiver_cagr']}%"
    })
    
    # Process equity curve
    equity_curve = result.get('equity_curve', [])
    if isinstance(equity_curve, (pd.DataFrame, pd.Series)):
        if isinstance(equity_curve, pd.DataFrame):
            dates = [str(d)[:10] for d in equity_curve.index]
            values = list(equity_curve.iloc[:, 0].values)
        else:
            dates = [str(d)[:10] for d in equity_curve.index]
            values = list(equity_curve.values)
    else:
        values = list(equity_curve) if equity_curve else []
        dates = []
    
    # Normalize to start at 100
    if values:
        initial = values[0] if values[0] != 0 else 1
        normalized = [v / initial * 100 for v in values]
        
        plot_data['strategies'][strategy_name] = {
            'name': strategy_name,
            'dates': dates,
            'values': normalized,
            'start_date': config['start'],
            'cagr': cagr * 100,
            'sharpe': sharpe,
            'max_drawdown': max_dd * 100
        }
        print(f"[OK] Updated {strategy_name} in plot_data.json")

# Save updated plot data
with open(plot_path, 'w') as f:
    json.dump(plot_data, f, indent=2)

# Print summary
print(f"\n{'='*60}")
print("SUMMARY")
print('='*60)
print(f"{'Strategy':<20} {'Our CAGR':<15} {'Quiver CAGR':<15}")
print('-'*50)
for r in results_summary:
    print(f"{r['strategy']:<20} {r['our_cagr']:<15} {r['quiver_cagr']:<15}")
