#!/usr/bin/env python
"""
Test the Strategy Replicator with proper weighting vs simple equal-weight
"""

import sys
import os
import time

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

from datetime import datetime, timedelta
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

def test_strategy_comparison(strategy_name: str):
    """Compare equal-weight vs strategy-specific weighting."""
    from quiver_signals import QuiverSignals
    from backtest_engine import BacktestEngine
    from strategy_replicator import StrategyReplicator
    
    api_key = os.getenv('QUIVER_API_KEY')
    if not api_key:
        print("ERROR: QUIVER_API_KEY not set")
        return
    
    print(f"\n{'='*100}")
    print(f"Testing Strategy: {strategy_name}")
    print(f"{'='*100}")
    
    qs = QuiverSignals(api_key)
    strategy_info = QuiverSignals.get_strategy_info(strategy_name)
    
    # Get raw data with metadata
    try:
        raw_df = qs.engine._get_raw_data_with_metadata(strategy_name)
        if raw_df is None or raw_df.empty:
            print(f"❌ No data available for {strategy_name}")
            return
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return
    
    print(f"✓ Fetched {len(raw_df)} data points")
    print(f"  Columns: {list(raw_df.columns)}")
    
    # Get tickers only
    if 'Ticker' not in raw_df.columns:
        print("❌ No Ticker column in data")
        return
    
    tickers = raw_df['Ticker'].unique().tolist()
    print(f"✓ Found {len(tickers)} unique tickers")
    
    # Setup dates
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    # Test 1: Equal Weight (our current method)
    print(f"\n--- Test 1: Equal Weight (Current Method) ---")
    engine = BacktestEngine(initial_capital=100000)
    test_tickers = tickers[:30]  # Limit for performance
    
    equal_weight_results = engine.run_equal_weight_backtest(
        test_tickers,
        str(start_date.date()),
        str(end_date.date())
    )
    
    if 'error' in equal_weight_results:
        print(f"❌ Equal weight backtest failed: {equal_weight_results['error']}")
    else:
        print(f"✓ Equal Weight Results:")
        print(f"  Total Return: {equal_weight_results['total_return']:.2%}")
        print(f"  CAGR: {equal_weight_results['cagr']:.2%}")
        print(f"  Sharpe: {equal_weight_results['sharpe_ratio']:.2f}")
        print(f"  Max DD: {equal_weight_results['max_drawdown']:.2%}")
    
    # Test 2: Strategy-Specific Weighting
    print(f"\n--- Test 2: Strategy-Specific Weighting (Replicator) ---")
    replicator = StrategyReplicator(initial_capital=100000)
    
    weighted_results = replicator.run_strategy_backtest(
        strategy_name,
        raw_df,
        str(start_date.date()),
        str(end_date.date())
    )
    
    if 'error' in weighted_results:
        print(f"❌ Weighted backtest failed: {weighted_results['error']}")
    else:
        print(f"✓ Weighted Results:")
        print(f"  Total Return: {weighted_results['total_return']:.2%}")
        print(f"  CAGR: {weighted_results['cagr']:.2%}")
        print(f"  Sharpe: {weighted_results['sharpe_ratio']:.2f}")
        print(f"  Max DD: {weighted_results['max_drawdown']:.2%}")
        print(f"  Strategy Type: {weighted_results.get('strategy_type', 'N/A')}")
        
        if weighted_results.get('strategy_type') == 'long_short':
            print(f"  Long Exposure: {weighted_results['long_exposure']:.2%}")
            print(f"  Short Exposure: {weighted_results['short_exposure']:.2%}")
            print(f"  Net Exposure: {weighted_results['net_exposure']:.2%}")
    
    # Compare to Quiver's published metrics
    print(f"\n--- Quiver's Published Metrics ---")
    print(f"  1Y Return: {strategy_info.get('return_1y', 'N/A')}")
    print(f"  CAGR (full period): {strategy_info.get('cagr', 'N/A')}")
    print(f"  Sharpe (full period): {strategy_info.get('sharpe', 'N/A')}")
    print(f"  Start Date: {strategy_info.get('start_date', 'N/A')}")
    
    # Show comparison
    print(f"\n--- Comparison Summary ---")
    if 'error' not in equal_weight_results and 'error' not in weighted_results:
        improvement = weighted_results['total_return'] - equal_weight_results['total_return']
        sharpe_improvement = weighted_results['sharpe_ratio'] - equal_weight_results['sharpe_ratio']
        
        print(f"  Return Improvement: {improvement:+.2%}")
        print(f"  Sharpe Improvement: {sharpe_improvement:+.2f}")
        
        if improvement > 0:
            print(f"  ✓ Weighted approach outperformed by {improvement:.2%}")
        else:
            print(f"  ⚠ Equal weight outperformed by {abs(improvement):.2%}")

def main():
    """Test several key strategies."""
    print("="*100)
    print("STRATEGY REPLICATOR TEST - Weighted vs Equal Weight")
    print("="*100)
    
    # Test these strategies
    strategies_to_test = [
        "Congress Buys",          # Should benefit from purchase-size weighting
        "Dan Meuser",            # Should benefit from portfolio mirroring
        "Top Gov Contract Recipients",  # Should benefit from value weighting
    ]
    
    for strategy_name in strategies_to_test:
        try:
            test_strategy_comparison(strategy_name)
            time.sleep(1)  # Rate limiting
        except Exception as e:
            print(f"❌ Error testing {strategy_name}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*100)
    print("TEST COMPLETE")
    print("="*100)

if __name__ == '__main__':
    main()
