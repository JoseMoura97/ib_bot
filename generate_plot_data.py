"""
Generate equity curve plot data for strategies vs SPY benchmark.
Saves JSON data that can be embedded in HTML for interactive charts.
"""

import json
import os
import sys
from datetime import datetime
import pandas as pd
import numpy as np

from dotenv import load_dotenv
from quiver_signals import QuiverSignals
from rebalancing_backtest_engine import RebalancingBacktestEngine

def normalize_equity_curve(equity_curve_df, initial_value=100):
    """Normalize an equity curve to start at initial_value (e.g., 100)."""
    if equity_curve_df.empty or 'equity' not in equity_curve_df.columns:
        return pd.DataFrame()
    
    first_value = equity_curve_df['equity'].iloc[0]
    if first_value <= 0:
        first_value = 1.0
    
    equity_curve_df = equity_curve_df.copy()
    equity_curve_df['normalized'] = (equity_curve_df['equity'] / first_value) * initial_value
    return equity_curve_df

def generate_plot_data():
    """Generate plot data for all strategies vs SPY."""
    print("Generating plot data for all strategies vs SPY...")
    print("="*80)
    
    load_dotenv()
    api_key = os.getenv("QUIVER_API_KEY")
    if not api_key:
        raise SystemExit("QUIVER_API_KEY is required")
    
    qs = QuiverSignals(api_key)
    bt = RebalancingBacktestEngine(
        quiver_api_key=api_key,
        initial_capital=100000,
        transaction_cost_bps=0.0,
        price_source=os.getenv("PRICE_SOURCE", "auto"),
    )
    
    # Output structure
    plot_data = {
        "generated_at": datetime.now().isoformat(),
        "strategies": {},
        "benchmark": None
    }
    
    # List of strategies to plot
    strategies = [
        "Congress Buys",
        "Congress Sells",
        "Congress Long-Short",
        "U.S. House Long-Short",
        "Transportation and Infra. Committee (House)",
        "Energy and Commerce Committee (House)",
        "Homeland Security Committee (Senate)",
        "Top Lobbying Spenders",
        "Lobbying Spending Growth",
        "Top Gov Contract Recipients",
        "Sector Weighted DC Insider",
        "Nancy Pelosi",
        "Dan Meuser",
        "Josh Gottheimer",
        "Donald Beyer",
        "Sheldon Whitehouse",
        "Insider Purchases",
    ]
    
    # Get SPY benchmark data (earliest strategy starts in 2009)
    print("\nFetching SPY benchmark...")
    try:
        from datetime import datetime as dt
        spy_result = bt.run_rebalancing_backtest(
            strategy_name="SPY_Benchmark",
            start_date=dt(2009, 1, 1),
            end_date=datetime.now(),
            lookback_days_override=None,
        )
        
        if spy_result and 'equity_curve' in spy_result and not 'error' in spy_result:
            spy_curve = normalize_equity_curve(spy_result['equity_curve'], 100)
            if not spy_curve.empty:
                # Downsample to weekly
                spy_curve_weekly = spy_curve.resample('W-FRI').last().fillna(method='ffill')
                plot_data['benchmark'] = {
                    "name": "SPY",
                    "dates": spy_curve_weekly.index.strftime('%Y-%m-%d').tolist(),
                    "values": spy_curve_weekly['normalized'].round(2).tolist()
                }
                print(f"✓ SPY: {len(spy_curve_weekly)} weekly points from {spy_curve_weekly.index[0].date()} to {spy_curve_weekly.index[-1].date()}")
    except Exception as e:
        print(f"✗ SPY Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Generate data for each strategy
    strategy_count = 0
    for strategy_name in strategies:
        try:
            print(f"\n{strategy_name}...")
            
            info = qs.get_strategy_info(strategy_name)
            if not info or not info.get("start_date"):
                print(f"  ✗ No strategy info found")
                continue
            
            start_date_str = info['start_date']
            start_date = datetime.fromisoformat(start_date_str)
            
            # Run backtest using run_rebalancing_backtest
            result = bt.run_rebalancing_backtest(
                strategy_name=strategy_name,
                start_date=start_date,
                end_date=datetime.now(),
                lookback_days_override=None,
            )
            
            if result and 'equity_curve' in result and not 'error' in result:
                equity_curve = normalize_equity_curve(result['equity_curve'], 100)
                
                if not equity_curve.empty:
                    # Downsample to weekly data to reduce file size
                    equity_curve_weekly = equity_curve.resample('W-FRI').last().fillna(method='ffill')
                    
                    cagr = result.get('cagr', 0)
                    sharpe = result.get('sharpe_ratio', 0)
                    max_dd = result.get('max_drawdown', 0)
                    
                    # Convert to percentages
                    cagr_pct = cagr * 100 if isinstance(cagr, (int, float)) else 0
                    max_dd_pct = max_dd * 100 if isinstance(max_dd, (int, float)) else 0
                    
                    plot_data['strategies'][strategy_name] = {
                        "name": strategy_name,
                        "dates": equity_curve_weekly.index.strftime('%Y-%m-%d').tolist(),
                        "values": equity_curve_weekly['normalized'].round(2).tolist(),
                        "start_date": start_date_str,
                        "cagr": float(cagr_pct),
                        "sharpe": float(sharpe) if isinstance(sharpe, (int, float)) else 0,
                        "max_drawdown": float(max_dd_pct)
                    }
                    
                    strategy_count += 1
                    print(f"  ✓ {len(equity_curve_weekly)} weekly points, CAGR={cagr_pct:.1f}%")
                else:
                    print(f"  ✗ Empty equity curve")
            elif 'error' in result:
                print(f"  ✗ Backtest error: {result['error']}")
            else:
                print(f"  ✗ No backtest result")
                
        except Exception as e:
            print(f"  ✗ Error: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n{'='*80}")
    print(f"Generated plot data for {strategy_count}/{len(strategies)} strategies")
    
    # Save to JSON file
    output_file = '.cache/plot_data.json'
    os.makedirs('.cache', exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(plot_data, f, indent=2)
    
    print(f"✓ Saved to {output_file}")
    
    # Calculate file size
    file_size = os.path.getsize(output_file) / 1024  # KB
    print(f"  File size: {file_size:.1f} KB")
    
    return plot_data

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings('ignore')
    
    # Set environment variables for backtesting
    os.environ['PYTHONUNBUFFERED'] = '1'
    os.environ['PRICE_SOURCE'] = os.getenv('PRICE_SOURCE', 'auto')
    os.environ['PROGRESS'] = '0'
    
    try:
        plot_data = generate_plot_data()
        
        if plot_data and plot_data.get('strategies'):
            print("\n✓ Plot data generation complete!")
            print(f"  Strategies: {len(plot_data['strategies'])}")
            if plot_data.get('benchmark'):
                print(f"  Benchmark: SPY with {len(plot_data['benchmark']['dates'])} points")
        else:
            print("\n✗ No plot data generated")
            sys.exit(1)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
