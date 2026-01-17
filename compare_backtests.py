#!/usr/bin/env python
"""
Compare our backtest engine results vs Quiver's published metrics.
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

def main():
    from quiver_signals import QuiverSignals
    from backtest_engine import BacktestEngine
    
    api_key = os.getenv('QUIVER_API_KEY')
    if not api_key:
        print("ERROR: QUIVER_API_KEY not set")
        return
    
    qs = QuiverSignals(api_key)
    all_strategies = QuiverSignals.get_all_strategies()
    
    # Use 1 year period to compare with Quiver's return_1y
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    print("=" * 100)
    print("BACKTEST COMPARISON: Our Engine vs Quiver Metrics")
    print("=" * 100)
    print(f"Period: {start_date.date()} to {end_date.date()} (1 year)")
    print()
    
    # Fetch signals for all strategies first
    print("Fetching signals for all strategies...")
    signal_cache = {}
    for strat_name in all_strategies.keys():
        try:
            signals = qs.engine.get_signals(strat_name)
            signal_cache[strat_name] = signals if signals else []
            time.sleep(0.3)
        except Exception as e:
            signal_cache[strat_name] = []
    
    print()
    print("-" * 100)
    print(f"{'Strategy':<40} | {'Quiver 1Y':<10} | {'Our 1Y':<10} | {'Quiver CAGR':<11} | {'Quiver Sharpe':<12} | {'Our Sharpe':<10} | {'Status'}")
    print("-" * 100)
    
    comparison_results = []
    
    for strat_name, strat_info in all_strategies.items():
        quiver_1y = strat_info.get('return_1y', 'N/A')
        quiver_cagr = strat_info.get('cagr', 'N/A')
        quiver_sharpe = strat_info.get('sharpe', 'N/A')
        
        signals = signal_cache.get(strat_name, [])
        
        if not signals:
            print(f"{strat_name:<40} | {quiver_1y:<10} | {'N/A':<10} | {quiver_cagr:<11} | {str(quiver_sharpe):<12} | {'N/A':<10} | No signals")
            comparison_results.append({
                'strategy': strat_name,
                'quiver_1y': quiver_1y,
                'our_1y': None,
                'quiver_cagr': quiver_cagr,
                'quiver_sharpe': quiver_sharpe,
                'our_sharpe': None,
                'status': 'No signals'
            })
            continue
        
        # Run our backtest
        engine = BacktestEngine(initial_capital=100000)
        # Use up to 30 tickers for performance
        test_tickers = signals[:30]
        
        results = engine.run_equal_weight_backtest(
            test_tickers,
            str(start_date.date()),
            str(end_date.date())
        )
        
        if 'error' in results:
            print(f"{strat_name:<40} | {quiver_1y:<10} | {'ERROR':<10} | {quiver_cagr:<11} | {str(quiver_sharpe):<12} | {'N/A':<10} | {results['error'][:20]}")
            comparison_results.append({
                'strategy': strat_name,
                'quiver_1y': quiver_1y,
                'our_1y': None,
                'quiver_cagr': quiver_cagr,
                'quiver_sharpe': quiver_sharpe,
                'our_sharpe': None,
                'status': 'Error'
            })
            continue
        
        our_1y = f"{results['total_return']:.2%}"
        our_sharpe = f"{results['sharpe_ratio']:.2f}"
        
        # Determine status
        status = "OK"
        if quiver_1y != 'N/A':
            try:
                quiver_1y_val = float(quiver_1y.replace('%', '')) / 100
                diff = abs(results['total_return'] - quiver_1y_val)
                if diff > 0.20:  # More than 20% difference
                    status = "Different period/tickers"
                elif diff > 0.10:
                    status = "Similar"
                else:
                    status = "Close match"
            except:
                status = "Can't compare"
        
        print(f"{strat_name:<40} | {quiver_1y:<10} | {our_1y:<10} | {quiver_cagr:<11} | {str(quiver_sharpe):<12} | {our_sharpe:<10} | {status}")
        
        comparison_results.append({
            'strategy': strat_name,
            'quiver_1y': quiver_1y,
            'our_1y': results['total_return'],
            'quiver_cagr': quiver_cagr,
            'quiver_sharpe': quiver_sharpe,
            'our_sharpe': results['sharpe_ratio'],
            'status': status
        })
    
    print("-" * 100)
    print()
    
    # Summary
    working = sum(1 for r in comparison_results if r['our_1y'] is not None)
    no_signals = sum(1 for r in comparison_results if r['status'] == 'No signals')
    errors = sum(1 for r in comparison_results if r['status'] == 'Error')
    
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Total strategies: {len(comparison_results)}")
    print(f"  Working backtests: {working}")
    print(f"  No signal data: {no_signals}")
    print(f"  Errors: {errors}")
    print()
    
    print("NOTE: Differences between Quiver and our backtests are expected because:")
    print("  1. Quiver uses full historical period from start_date (some since 2009)")
    print("  2. We only backtest the last 1 year")
    print("  3. Quiver may use different weighting schemes (not equal-weight)")
    print("  4. Quiver rebalances according to strategy rules, we use static weights")
    print("  5. Quiver includes transaction costs and timing, we use simplified model")
    print("  6. We may not have the exact same tickers (API provides current holdings)")
    print()
    
    # Show detailed comparison for working strategies
    if working > 0:
        print("=" * 100)
        print("DETAILED COMPARISON (Working Strategies)")
        print("=" * 100)
        print()
        
        for r in comparison_results:
            if r['our_1y'] is not None:
                strat = r['strategy']
                info = all_strategies.get(strat, {})
                
                print(f"Strategy: {strat}")
                print(f"  Subcategory: {info.get('subcategory', 'N/A')}")
                print(f"  Quiver Start Date: {info.get('start_date', 'N/A')}")
                print(f"  Quiver 1Y Return: {r['quiver_1y']}")
                print(f"  Our 1Y Return:    {r['our_1y']:.2%}")
                print(f"  Quiver CAGR:      {r['quiver_cagr']}")
                print(f"  Quiver Sharpe:    {r['quiver_sharpe']}")
                print(f"  Our Sharpe:       {r['our_sharpe']:.2f}")
                print(f"  Quiver Win Rate:  {info.get('win_rate', 'N/A')}")
                print(f"  Quiver Max DD:    {info.get('max_drawdown', 'N/A')}")
                print()

if __name__ == '__main__':
    main()
