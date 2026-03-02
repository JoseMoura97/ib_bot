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
from rebalancing_backtest_engine import RebalancingBacktestEngine, _ProgressBar

def normalize_equity_curve(equity_curve_df, initial_value=100):
    """Normalize an equity curve to start at initial_value (e.g., 100)."""
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

def generate_plot_data(use_cache_only: bool = False):
    """Generate plot data for all strategies vs SPY.
    
    Args:
        use_cache_only: If True, use only cached price data (no API calls).
                        This runs real backtests on cached historical prices.
    """
    print("Generating plot data for all strategies vs SPY...")
    print("="*80)
    
    load_dotenv()
    api_key = os.getenv("QUIVER_API_KEY")
    if not api_key:
        raise SystemExit("QUIVER_API_KEY is required")
    
    # Determine price source
    if use_cache_only:
        price_source = "cache_only"
        print("Using CACHE_ONLY mode - no external API calls")
    else:
        price_source = os.getenv("PRICE_SOURCE", "auto")
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
        "data_source": "cached_prices" if use_cache_only else "live_api",
        "synthetic": False,  # These are REAL backtests, not synthetic curves
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
        "Michael Burry",
        "Bill Ackman",
        "Howard Marks",
    ]
    
    # Get SPY benchmark data — start from earliest strategy date for fair comparison
    overall = _ProgressBar(total=len(strategies) + 1, prefix="Plot data", width=30)

    print("\nFetching SPY benchmark...")
    try:
        from datetime import datetime as dt
        benchmark_start = dt(2014, 1, 1)
        spy_result = bt.run_rebalancing_backtest(
            strategy_name="SPY_Benchmark",
            start_date=benchmark_start,
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
                print(f"[OK] SPY: {len(spy_curve_weekly)} weekly points from {spy_curve_weekly.index[0].date()} to {spy_curve_weekly.index[-1].date()}")
        overall.step(extra="SPY")
    except Exception as e:
        print(f"[ERROR] SPY Error: {e}")
        import traceback
        traceback.print_exc()
        overall.step(extra="SPY error")
    
    # Generate data for each strategy — use each strategy's actual start date
    # for accurate CAGR (previously clipped to 2020-01-01 which understated returns)
    
    strategy_count = 0
    for strategy_name in strategies:
        try:
            print(f"\n{strategy_name}...")
            
            info = qs.get_strategy_info(strategy_name)
            if not info or not info.get("start_date"):
                print(f"  [SKIP] No strategy info found")
                overall.step(extra=f"skip: {strategy_name}")
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
                    print(f"  [OK] {len(equity_curve_weekly)} weekly points, CAGR={cagr_pct:.1f}%")
                    overall.step(extra=f"ok: {strategy_name}")
                else:
                    print(f"  [SKIP] Empty equity curve")
                    overall.step(extra=f"skip: {strategy_name}")
            elif 'error' in result:
                print(f"  [ERROR] Backtest error: {result['error']}")
                overall.step(extra=f"error: {strategy_name}")
            else:
                print(f"  [SKIP] No backtest result")
                overall.step(extra=f"skip: {strategy_name}")
                
        except Exception as e:
            print(f"  [ERROR] Error: {e}")
            import traceback
            traceback.print_exc()
            overall.step(extra=f"error: {strategy_name}")
            continue
    
    print(f"\n{'='*80}")
    print(f"Generated plot data for {strategy_count}/{len(strategies)} strategies")
    
    output_file = '.cache/plot_data.json'
    os.makedirs('.cache', exist_ok=True)

    if strategy_count == 0:
        print("[SKIP] Not writing plot_data.json — 0 strategies succeeded")
        return plot_data
    
    with open(output_file, 'w') as f:
        json.dump(plot_data, f, indent=2)
    
    file_size = os.path.getsize(output_file) / 1024
    print(f"[OK] Saved to {output_file} ({file_size:.1f} KB)")
    
    return plot_data

if __name__ == "__main__":
    import warnings
    import argparse
    warnings.filterwarnings('ignore')
    
    parser = argparse.ArgumentParser(description="Generate plot data for strategies")
    parser.add_argument("--cache-only", action="store_true",
                        help="Use only cached price data (no external API calls)")
    parser.add_argument("--cache-dir", type=str, default=".cache",
                        help="Cache directory path")
    parser.add_argument("--no-progress", action="store_true",
                        help="Disable progress bars")
    args = parser.parse_args()
    
    # Set environment variables for backtesting
    os.environ['PYTHONUNBUFFERED'] = '1'
    if not args.cache_only:
        os.environ['PRICE_SOURCE'] = os.getenv('PRICE_SOURCE', 'auto')
    if args.no_progress:
        os.environ['NO_PROGRESS'] = '1'
    else:
        # Default progress to ON unless user has explicitly disabled it.
        if os.getenv("NO_PROGRESS", "").strip().lower() not in {"1", "true", "yes"}:
            if os.getenv("PROGRESS", "").strip() == "":
                os.environ["PROGRESS"] = "1"
    
    try:
        plot_data = generate_plot_data(use_cache_only=args.cache_only)
        
        if plot_data and plot_data.get('strategies'):
            print("\n[OK] Plot data generation complete!")
            print(f"  Strategies: {len(plot_data['strategies'])}")
            print(f"  Data source: {plot_data.get('data_source', 'unknown')}")
            print(f"  Synthetic: {plot_data.get('synthetic', False)}")
            if plot_data.get('benchmark'):
                print(f"  Benchmark: SPY with {len(plot_data['benchmark']['dates'])} points")
        else:
            print("\n[ERROR] No plot data generated")
            sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
