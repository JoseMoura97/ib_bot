#!/usr/bin/env python
"""
Final Comparison: Equal-Weight vs Proper Weighted Replication vs Quiver Metrics
Shows the improvement from implementing proper strategy weighting.
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

load_dotenv()

def test_strategy_full_comparison(strategy_name: str):
    """Run equal-weight, weighted, and compare to Quiver."""
    from quiver_signals import QuiverSignals
    from backtest_engine import BacktestEngine
    from strategy_replicator import StrategyReplicator
    
    api_key = os.getenv('QUIVER_API_KEY')
    if not api_key:
        print("ERROR: QUIVER_API_KEY not set")
        return None
    
    qs = QuiverSignals(api_key)
    strategy_info = QuiverSignals.get_strategy_info(strategy_name)
    
    print(f"\n{'='*100}")
    print(f"Strategy: {strategy_name}")
    print(f"Category: {strategy_info.get('subcategory', 'N/A')}")
    print(f"{'='*100}")
    
    # Get raw data with metadata
    try:
        raw_df = qs.engine._get_raw_data_with_metadata(strategy_name)
        if raw_df is None or raw_df.empty:
            print(f"❌ No data available")
            return None
        
        print(f"✓ Fetched {len(raw_df)} data points")
        if 'Amount' in raw_df.columns:
            print(f"  → Has Amount column (transaction size weighting available)")
        if 'Transaction' in raw_df.columns:
            print(f"  → Has Transaction column (long-short available)")
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return None
    
    if 'Ticker' not in raw_df.columns:
        print("❌ No Ticker column")
        return None
    
    tickers = raw_df['Ticker'].unique().tolist()
    print(f"✓ {len(tickers)} unique tickers")
    
    # Setup dates
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    # Test 1: Equal Weight
    print(f"\n--- Equal Weight (Current Method) ---")
    engine = BacktestEngine(initial_capital=100000)
    test_tickers = tickers[:30]
    
    equal_results = engine.run_equal_weight_backtest(
        test_tickers,
        str(start_date.date()),
        str(end_date.date())
    )
    
    if 'error' not in equal_results:
        print(f"  Return: {equal_results['total_return']:>8.2%}")
        print(f"  Sharpe: {equal_results['sharpe_ratio']:>8.2f}")
        print(f"  Max DD: {equal_results['max_drawdown']:>8.2%}")
    else:
        print(f"  ❌ {equal_results['error']}")
        equal_results = None
    
    # Test 2: Weighted Replication
    print(f"\n--- Weighted Replication (Strategy-Specific) ---")
    replicator = StrategyReplicator(initial_capital=100000)
    
    weighted_results = replicator.run_strategy_backtest(
        strategy_name,
        raw_df,
        str(start_date.date()),
        str(end_date.date())
    )
    
    if 'error' not in weighted_results:
        print(f"  Return: {weighted_results['total_return']:>8.2%}")
        print(f"  Sharpe: {weighted_results['sharpe_ratio']:>8.2f}")
        print(f"  Max DD: {weighted_results['max_drawdown']:>8.2%}")
        print(f"  Type:   {weighted_results.get('strategy_type', 'N/A')}")
        
        if weighted_results.get('strategy_type') == 'long_short':
            print(f"  Long:   {weighted_results.get('long_exposure', 0):>8.2%}")
            print(f"  Short:  {weighted_results.get('short_exposure', 0):>8.2%}")
            print(f"  Net:    {weighted_results.get('net_exposure', 0):>8.2%}")
        
        # Show top 5 weights
        weights = weighted_results.get('weights', {})
        if weights:
            sorted_weights = sorted(weights.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
            print(f"  Top 5 weights:")
            for ticker, weight in sorted_weights:
                print(f"    {ticker}: {weight:>7.2%}")
    else:
        print(f"  ❌ {weighted_results['error']}")
        weighted_results = None
    
    # Test 3: Quiver's Metrics
    print(f"\n--- Quiver's Published Metrics ---")
    print(f"  1Y Return: {strategy_info.get('return_1y', 'N/A'):>10}")
    print(f"  CAGR:      {strategy_info.get('cagr', 'N/A'):>10} (full period since {strategy_info.get('start_date', 'N/A')})")
    print(f"  Sharpe:    {strategy_info.get('sharpe', 'N/A'):>10}")
    
    # Comparison
    print(f"\n--- Comparison Summary ---")
    
    result = {
        'strategy': strategy_name,
        'quiver_1y': strategy_info.get('return_1y', 'N/A'),
        'equal_1y': equal_results['total_return'] if equal_results else None,
        'weighted_1y': weighted_results['total_return'] if weighted_results else None,
        'equal_sharpe': equal_results['sharpe_ratio'] if equal_results else None,
        'weighted_sharpe': weighted_results['sharpe_ratio'] if weighted_results else None,
    }
    
    if equal_results and weighted_results:
        improvement = weighted_results['total_return'] - equal_results['total_return']
        sharpe_improvement = weighted_results['sharpe_ratio'] - equal_results['sharpe_ratio']
        
        print(f"  Weighted vs Equal:")
        print(f"    Return improvement: {improvement:+.2%}")
        print(f"    Sharpe improvement: {sharpe_improvement:+.2f}")
        
        if strategy_info.get('return_1y', 'N/A') != 'N/A':
            quiver_1y_val = float(strategy_info['return_1y'].replace('%', '')) / 100
            weighted_diff = weighted_results['total_return'] - quiver_1y_val
            equal_diff = equal_results['total_return'] - quiver_1y_val
            
            print(f"  vs Quiver 1Y:")
            print(f"    Equal weight diff:   {equal_diff:+.2%}")
            print(f"    Weighted diff:       {weighted_diff:+.2%}")
            print(f"    Weighted is closer by: {abs(equal_diff) - abs(weighted_diff):+.2%}")
    
    return result

def main():
    """Test key strategies with full comparison."""
    print("="*100)
    print("FINAL COMPARISON: Equal-Weight vs Weighted Replication vs Quiver")
    print("="*100)
    print(f"Testing improved strategy replication with:")
    print(f"  ✓ Transaction amount weighting")
    print(f"  ✓ Long-short 130/30 mechanics")
    print(f"  ✓ Strategy-specific configurations")
    print()
    
    # Test these strategies - covering different types
    strategies_to_test = [
        "Congress Buys",                              # Congressional weighted
        "Congress Long-Short",                        # Long-short 130/30
        "Dan Meuser",                                 # Portfolio mirror
        "Top Gov Contract Recipients",                # Value-weighted
        "Transportation and Infra. Committee (House)", # Committee weighted
        "Lobbying Spending Growth",                   # Equal-weighted with sorting
    ]
    
    results = []
    for strategy_name in strategies_to_test:
        try:
            result = test_strategy_full_comparison(strategy_name)
            if result:
                results.append(result)
            time.sleep(0.5)  # Rate limiting
        except Exception as e:
            print(f"❌ Error testing {strategy_name}: {e}")
            import traceback
            traceback.print_exc()
    
    # Final summary table
    print("\n" + "="*100)
    print("FINAL RESULTS SUMMARY")
    print("="*100)
    print(f"{'Strategy':<40} | {'Quiver 1Y':<10} | {'Equal 1Y':<10} | {'Weighted 1Y':<10} | {'Improvement'}")
    print("-"*100)
    
    for r in results:
        strat = r['strategy'][:39]
        quiver = r['quiver_1y'] if r['quiver_1y'] != 'N/A' else 'N/A'
        equal = f"{r['equal_1y']:.2%}" if r['equal_1y'] is not None else 'N/A'
        weighted = f"{r['weighted_1y']:.2%}" if r['weighted_1y'] is not None else 'N/A'
        
        if r['equal_1y'] is not None and r['weighted_1y'] is not None:
            improvement = r['weighted_1y'] - r['equal_1y']
            imp_str = f"{improvement:+.2%}"
        else:
            imp_str = 'N/A'
        
        print(f"{strat:<40} | {quiver:<10} | {equal:<10} | {weighted:<10} | {imp_str}")
    
    print("="*100)
    print("COMPLETE!")
    print("="*100)

if __name__ == '__main__':
    main()
