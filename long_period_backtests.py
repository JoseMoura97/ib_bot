#!/usr/bin/env python
"""
Long-Period Backtests - Test strategies over extended time periods
Compares 1-year, 3-year, and 5-year performance vs Quiver's full-period CAGR
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
from backtest_engine import BacktestEngine
from quiver_signals import QuiverSignals

load_dotenv()

def run_multi_period_backtest(strategy_name: str, tickers: list, quiver_cagr: str):
    """Run backtest for multiple time periods."""
    
    if not tickers:
        print(f"  ⚠ No tickers available")
        return None
    
    end_date = datetime.now()
    
    # Test periods
    periods = {
        '1 Year': 365,
        '2 Years': 730,
        '3 Years': 1095,
        '5 Years': 1825
    }
    
    results = {}
    engine = BacktestEngine(initial_capital=100000)
    
    print(f"\n{'='*80}")
    print(f"Strategy: {strategy_name}")
    print(f"Quiver CAGR (full period): {quiver_cagr}")
    print(f"Tickers: {len(tickers)} ({'limited to 30' if len(tickers) > 30 else 'all'})")
    print(f"{'='*80}")
    
    # Limit tickers for performance
    test_tickers = tickers[:30]
    
    for period_name, days in periods.items():
        start_date = end_date - timedelta(days=days)
        
        print(f"\n--- {period_name} Backtest ---")
        print(f"Period: {start_date.date()} to {end_date.date()}")
        
        try:
            bt_results = engine.run_equal_weight_backtest(
                test_tickers,
                str(start_date.date()),
                str(end_date.date())
            )
            
            if 'error' in bt_results:
                print(f"  ✗ Error: {bt_results['error']}")
                results[period_name] = None
            else:
                print(f"  ✓ Success!")
                print(f"    Total Return: {bt_results['total_return']:>8.2%}")
                print(f"    CAGR:         {bt_results['cagr']:>8.2%}")
                print(f"    Sharpe:       {bt_results['sharpe_ratio']:>8.2f}")
                print(f"    Max DD:       {bt_results['max_drawdown']:>8.2%}")
                print(f"    Win Rate:     {bt_results['win_rate']:>8.1%}")
                
                results[period_name] = {
                    'total_return': bt_results['total_return'],
                    'cagr': bt_results['cagr'],
                    'sharpe': bt_results['sharpe_ratio'],
                    'max_dd': bt_results['max_drawdown'],
                    'win_rate': bt_results['win_rate']
                }
        except Exception as e:
            print(f"  ✗ Exception: {e}")
            results[period_name] = None
    
    # Compare to Quiver CAGR
    if quiver_cagr != 'N/A':
        try:
            quiver_cagr_val = float(quiver_cagr.replace('%', '')) / 100
            
            print(f"\n--- Comparison to Quiver CAGR ({quiver_cagr}) ---")
            for period_name, result in results.items():
                if result:
                    diff = result['cagr'] - quiver_cagr_val
                    status = "✓" if diff > 0 else "✗"
                    print(f"  {period_name:<10}: {result['cagr']:>7.2%}  ({status} {diff:+.2%})")
        except:
            pass
    
    return results

def main():
    """Run long-period backtests for working strategies."""
    print("="*80)
    print("LONG-PERIOD BACKTEST ANALYSIS")
    print("Testing 1Y, 2Y, 3Y, and 5Y periods for all working strategies")
    print("="*80)
    
    api_key = os.getenv('QUIVER_API_KEY')
    if not api_key:
        print("ERROR: QUIVER_API_KEY not set")
        return
    
    qs = QuiverSignals(api_key)
    all_strategies = QuiverSignals.get_all_strategies()
    
    # Fetch signals once
    print("\nFetching signals for all strategies...")
    signal_cache = {}
    for strat_name in all_strategies.keys():
        try:
            signals = qs.engine.get_signals(strat_name)
            signal_cache[strat_name] = signals if signals else []
            time.sleep(0.3)  # Rate limiting
        except Exception as e:
            signal_cache[strat_name] = []
    
    # Select strategies to test (working ones)
    strategies_to_test = [
        "Congress Buys",
        "Dan Meuser",
        "Nancy Pelosi",
        "Sector Weighted DC Insider",
        "Lobbying Spending Growth",
        "Top Gov Contract Recipients",
        "Top Lobbying Spenders",
        "Donald Beyer",
        "Josh Gottheimer",
        "Sheldon Whitehouse"
    ]
    
    all_results = {}
    
    for strategy_name in strategies_to_test:
        tickers = signal_cache.get(strategy_name, [])
        if not tickers:
            print(f"\n⚠ Skipping {strategy_name} - no signals")
            continue
        
        strategy_info = all_strategies.get(strategy_name, {})
        quiver_cagr = strategy_info.get('cagr', 'N/A')
        
        try:
            results = run_multi_period_backtest(strategy_name, tickers, quiver_cagr)
            all_results[strategy_name] = results
        except Exception as e:
            print(f"\n✗ Error testing {strategy_name}: {e}")
        
        time.sleep(1)  # Rate limiting between strategies
    
    # Summary table
    print("\n" + "="*80)
    print("SUMMARY: CAGR Comparison Across Time Periods")
    print("="*80)
    print(f"{'Strategy':<35} | {'Quiver':<8} | {'1Y':<8} | {'2Y':<8} | {'3Y':<8} | {'5Y':<8}")
    print("-"*80)
    
    for strategy_name, results in all_results.items():
        if not results:
            continue
        
        strategy_info = all_strategies.get(strategy_name, {})
        quiver_cagr = strategy_info.get('cagr', 'N/A')
        
        row = f"{strategy_name[:34]:<35} | {quiver_cagr:<8} |"
        
        for period in ['1 Year', '2 Years', '3 Years', '5 Years']:
            if results.get(period):
                cagr = results[period]['cagr']
                row += f" {cagr:>7.2%} |"
            else:
                row += f" {'N/A':>7} |"
        
        print(row)
    
    # Best performers
    print("\n" + "="*80)
    print("BEST PERFORMERS (3-Year CAGR)")
    print("="*80)
    
    three_year_results = []
    for strategy_name, results in all_results.items():
        if results and results.get('3 Years'):
            three_year_results.append((
                strategy_name,
                results['3 Years']['cagr'],
                results['3 Years']['sharpe']
            ))
    
    three_year_results.sort(key=lambda x: x[1], reverse=True)
    
    print(f"{'Rank':<6} {'Strategy':<35} {'CAGR':<10} {'Sharpe'}")
    print("-"*60)
    for i, (name, cagr, sharpe) in enumerate(three_year_results[:10], 1):
        print(f"{i:<6} {name[:34]:<35} {cagr:>8.2%}   {sharpe:>6.2f}")
    
    print("\n" + "="*80)
    print("COMPLETE!")
    print("="*80)

if __name__ == '__main__':
    main()
