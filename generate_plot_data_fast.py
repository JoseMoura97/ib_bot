"""
Fast version - generates plot data for ALL strategies.
Uses IB for real data, 2020+ date range for speed.
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
    """Normalize an equity curve to start at initial_value."""
    if equity_curve_df is None or equity_curve_df.empty:
        return pd.DataFrame()
    
    # Handle both 'equity' and 'portfolio_value' column names
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

def generate_plot_data_fast():
    """Generate plot data for ALL strategies."""
    print("Generating plot data (ALL strategies)...")
    print("="*80)
    
    load_dotenv()
    api_key = os.getenv("QUIVER_API_KEY")
    if not api_key:
        raise SystemExit("QUIVER_API_KEY is required")
    
    price_source = os.getenv("PRICE_SOURCE", "ib")
    print(f"Using price source: {price_source}")
    
    qs = QuiverSignals(api_key)
    bt = RebalancingBacktestEngine(
        quiver_api_key=api_key,
        initial_capital=100000,
        transaction_cost_bps=0.0,
        price_source=price_source,
    )
    
    # Output structure
    plot_data = {
        "generated_at": datetime.now().isoformat(),
        "data_source": "ib_real_data",
        "synthetic": False,
        "strategies": {},
        "benchmark": None
    }
    
    # ALL strategies from the catalog (22 total)
    strategies = [
        "Congress Buys",
        "Congress Sells",
        "Congress Long-Short",
        "U.S. House Long-Short",
        "Transportation and Infra. Committee (House)",
        "Top Lobbying Spenders",
        "Lobbying Spending Growth",
        "Top Gov Contract Recipients",
        "Sector Weighted DC Insider",
        "Nancy Pelosi",
        "Dan Meuser",
        "Josh Gottheimer",
        "Sheldon Whitehouse",
        "Donald Beyer",
        "Insider Purchases",
        "WSB Top 10",
        "Analyst Long",
        "House Natural Resources",
        "Energy and Commerce Committee (House)",
        "Homeland Security Committee (Senate)",
        # 13F Hedge Fund Managers
        "Michael Burry",
        "Bill Ackman",
        "Howard Marks",
    ]
    
    # Use 2020 start for faster IB data
    min_start_date = datetime(2020, 1, 1)
    
    # Get SPY benchmark - fetch directly from IB price data
    print("\nFetching SPY benchmark...")
    try:
        from backtest_engine import BacktestEngine
        be = BacktestEngine(initial_capital=100000, price_source=price_source)
        spy_data = be.fetch_historical_data(
            ["SPY"], 
            min_start_date.strftime("%Y-%m-%d"), 
            datetime.now().strftime("%Y-%m-%d")
        )
        
        if "SPY" in spy_data and not spy_data["SPY"].empty:
            spy_df = spy_data["SPY"]
            if "Close" in spy_df.columns:
                # Normalize to start at 100
                first_close = spy_df["Close"].iloc[0]
                spy_df = spy_df.copy()
                spy_df["normalized"] = (spy_df["Close"] / first_close) * 100
                
                # Resample to weekly
                spy_weekly = spy_df["normalized"].resample("W-FRI").last().dropna()
                
                plot_data['benchmark'] = {
                    "name": "SPY",
                    "dates": spy_weekly.index.strftime('%Y-%m-%d').tolist(),
                    "values": spy_weekly.round(2).tolist()
                }
                print(f"[OK] SPY: {len(spy_weekly)} weekly points")
            else:
                print(f"[ERROR] SPY: No Close column")
        else:
            print(f"[ERROR] SPY: No data returned from IB")
    except Exception as e:
        print(f"[ERROR] SPY Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Generate data for each strategy
    strategy_count = 0
    for strategy_name in strategies:
        try:
            print(f"\n{strategy_name}...")
            
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
                    
                    cagr = result.get('cagr', 0)
                    sharpe = result.get('sharpe_ratio', 0)
                    max_dd = result.get('max_drawdown', 0)
                    
                    cagr_pct = cagr * 100 if isinstance(cagr, (int, float)) else 0
                    max_dd_pct = max_dd * 100 if isinstance(max_dd, (int, float)) else 0
                    
                    plot_data['strategies'][strategy_name] = {
                        "name": strategy_name,
                        "dates": equity_curve_weekly.index.strftime('%Y-%m-%d').tolist(),
                        "values": equity_curve_weekly['normalized'].round(2).tolist(),
                        "start_date": min_start_date.isoformat(),
                        "cagr": float(cagr_pct),
                        "sharpe": float(sharpe) if isinstance(sharpe, (int, float)) else 0,
                        "max_drawdown": float(max_dd_pct)
                    }
                    
                    strategy_count += 1
                    print(f"  [OK] {len(equity_curve_weekly)} points, CAGR={cagr_pct:.1f}%")
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
    print(f"Generated plot data for {strategy_count}/{len(strategies)} strategies")
    
    # Sync metrics from validation results (more accurate)
    validation_path = '.cache/last_validation_results.json'
    if os.path.exists(validation_path):
        try:
            with open(validation_path, 'r') as f:
                validation_data = json.load(f)
            
            synced = 0
            for name in plot_data.get("strategies", {}):
                val_strat = validation_data.get("strategies", {}).get(name, {})
                if val_strat:
                    plot_data["strategies"][name]["cagr"] = val_strat.get("cagr", 0)
                    plot_data["strategies"][name]["sharpe"] = val_strat.get("sharpe", 0)
                    plot_data["strategies"][name]["max_drawdown"] = val_strat.get("max_drawdown", 0)
                    synced += 1
            
            plot_data["metrics_source"] = "validation_results"
            print(f"[OK] Synced metrics from validation results ({synced} strategies)")
        except Exception as e:
            print(f"[WARN] Could not sync validation metrics: {e}")
    
    # Save to JSON file
    output_file = '.cache/plot_data.json'
    os.makedirs('.cache', exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(plot_data, f, indent=2)
    
    file_size = os.path.getsize(output_file) / 1024
    print(f"[OK] Saved to {output_file} ({file_size:.1f} KB)")
    
    return plot_data

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings('ignore')
    os.environ['PYTHONUNBUFFERED'] = '1'
    
    try:
        plot_data = generate_plot_data_fast()
        
        if plot_data and plot_data.get('strategies'):
            print("\n[OK] Plot data generation complete!")
            print(f"  Strategies: {len(plot_data['strategies'])}")
            if plot_data.get('benchmark'):
                print(f"  Benchmark: SPY")
        else:
            print("\n[ERROR] No plot data generated")
            sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
