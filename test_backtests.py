#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Backtest Engine Test Script
Tests the backtest engine with all available strategies.
"""

import sys
import os

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ASCII symbols for Windows compatibility
CHECK = '[OK]'
FAIL = '[FAIL]'
WARN = '[WARN]'
INFO = '[INFO]'

def print_header(text):
    print("\n" + "=" * 70)
    print(text.center(70))
    print("=" * 70)

def print_section(text):
    print(f"\n--- {text} ---")

def test_backtest_engine_availability():
    """Test if the backtest engine is available."""
    print_section("Testing Backtest Engine Availability")
    
    try:
        from backtest_engine import BacktestEngine
        
        if not BacktestEngine.is_available():
            print(f"{WARN} BacktestEngine available but yfinance not installed")
            return False
        
        print(f"{CHECK} BacktestEngine imported successfully")
        print(f"{CHECK} yfinance is available")
        return True
    except ImportError as e:
        print(f"{FAIL} Failed to import BacktestEngine: {e}")
        return False

def test_backtest_basic():
    """Test basic backtest with simple tickers."""
    print_section("Testing Basic Backtest (AAPL, MSFT, GOOGL)")
    
    from backtest_engine import BacktestEngine
    
    engine = BacktestEngine(initial_capital=100000)
    tickers = ['AAPL', 'MSFT', 'GOOGL']
    
    # Use 6 month period for faster testing
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)
    
    results = engine.run_equal_weight_backtest(
        tickers,
        str(start_date.date()),
        str(end_date.date()),
        'monthly'
    )
    
    if 'error' in results:
        print(f"{FAIL} Backtest failed: {results['error']}")
        return False
    
    print(f"{CHECK} Backtest completed successfully")
    print(f"  Tickers: {len(results['tickers'])}")
    print(f"  Period: {results['start_date']} to {results['end_date']}")
    print(f"  Total Return: {results['total_return']:.2%}")
    print(f"  CAGR: {results['cagr']:.2%}")
    print(f"  Sharpe Ratio: {results['sharpe_ratio']:.2f}")
    print(f"  Max Drawdown: {results['max_drawdown']:.2%}")
    return True

def test_benchmark_comparison():
    """Test benchmark comparison functionality."""
    print_section("Testing Benchmark Comparison")
    
    from backtest_engine import BacktestEngine
    
    engine = BacktestEngine(initial_capital=100000)
    tickers = ['AAPL', 'MSFT']
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)
    
    # Run backtest first
    results = engine.run_equal_weight_backtest(
        tickers,
        str(start_date.date()),
        str(end_date.date())
    )
    
    if 'error' in results:
        print(f"{FAIL} Initial backtest failed: {results['error']}")
        return False
    
    # Compare to benchmark
    bench_results = engine.compare_to_benchmark('SPY')
    
    if 'error' in bench_results:
        print(f"{FAIL} Benchmark comparison failed: {bench_results['error']}")
        return False
    
    print(f"{CHECK} Benchmark comparison completed")
    print(f"  Benchmark: {bench_results['benchmark']}")
    print(f"  Alpha: {bench_results['alpha']:.2%}")
    print(f"  Beta: {bench_results['beta']:.2f}")
    print(f"  Outperformance: {bench_results['outperformance']:.2%}")
    return True

def test_weighted_backtest():
    """Test weighted multi-strategy backtest."""
    print_section("Testing Weighted Backtest")
    
    from backtest_engine import BacktestEngine
    
    engine = BacktestEngine(initial_capital=100000)
    
    strategy_tickers = {
        'Strategy A': ['AAPL', 'MSFT'],
        'Strategy B': ['GOOGL', 'AMZN'],
    }
    
    strategy_weights = {
        'Strategy A': 60,
        'Strategy B': 40,
    }
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)
    
    results = engine.run_weighted_backtest(
        strategy_tickers,
        strategy_weights,
        str(start_date.date()),
        str(end_date.date())
    )
    
    if 'error' in results:
        print(f"{FAIL} Weighted backtest failed: {results['error']}")
        return False
    
    print(f"{CHECK} Weighted backtest completed")
    print(f"  Tickers: {len(results['tickers'])}")
    print(f"  Total Return: {results['total_return']:.2%}")
    print(f"  CAGR: {results['cagr']:.2%}")
    return True

def fetch_all_strategy_signals():
    """Fetch signals for all strategies with rate limit handling."""
    print_section("Fetching All Strategy Signals (with rate limit handling)")
    
    api_key = os.getenv('QUIVER_API_KEY')
    if not api_key:
        print(f"{WARN} QUIVER_API_KEY not set, skipping strategy signal tests")
        return None
    
    import time
    from quiver_signals import QuiverSignals
    
    qs = QuiverSignals(api_key)
    all_strategies = QuiverSignals.get_all_strategies()
    
    signal_cache = {}
    
    for strat_name in all_strategies.keys():
        try:
            signals = qs.engine.get_signals(strat_name)
            signal_cache[strat_name] = signals if signals else []
            
            status = CHECK if signals else WARN
            count = len(signals) if signals else 0
            sample = signals[:3] if signals else []
            print(f"  {status} {strat_name}: {count} tickers {sample}")
            
            # Rate limit protection - wait between API calls
            time.sleep(0.5)
            
        except Exception as e:
            signal_cache[strat_name] = []
            print(f"  {FAIL} {strat_name}: {e}")
            time.sleep(1)  # Longer wait after error
    
    return signal_cache

def test_strategy_backtests(signal_cache=None):
    """Test backtesting each strategy individually using cached signals."""
    print_section("Testing Individual Strategy Backtests")
    
    api_key = os.getenv('QUIVER_API_KEY')
    if not api_key:
        print(f"{WARN} QUIVER_API_KEY not set, skipping strategy backtest tests")
        return None
    
    from quiver_signals import QuiverSignals
    from backtest_engine import BacktestEngine
    
    # If no cache provided, fetch signals
    if signal_cache is None:
        signal_cache = fetch_all_strategy_signals()
        if signal_cache is None:
            return None
    
    all_strategies = QuiverSignals.get_all_strategies()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)  # 6 months for speed
    
    results = {}
    
    for strat_name, strat_info in all_strategies.items():
        print(f"\n{INFO} Testing: {strat_name} ({strat_info.get('category', 'unknown')})")
        
        try:
            # Use cached signals instead of fetching again
            signals = signal_cache.get(strat_name, [])
            
            if not signals:
                print(f"  {WARN} No signals in cache, skipping backtest")
                results[strat_name] = {'success': False, 'reason': 'No signals'}
                continue
            
            print(f"  Got {len(signals)} tickers: {signals[:5]}{'...' if len(signals) > 5 else ''}")
            
            # Limit tickers to prevent timeout
            test_tickers = signals[:20]
            
            # Run backtest
            engine = BacktestEngine(initial_capital=100000)
            bt_results = engine.run_equal_weight_backtest(
                test_tickers,
                str(start_date.date()),
                str(end_date.date())
            )
            
            if 'error' in bt_results:
                print(f"  {FAIL} Backtest error: {bt_results['error']}")
                results[strat_name] = {'success': False, 'reason': bt_results['error']}
                continue
            
            print(f"  {CHECK} Backtest successful")
            print(f"    Valid tickers: {len(bt_results['tickers'])}")
            print(f"    Total Return: {bt_results['total_return']:.2%}")
            print(f"    Sharpe: {bt_results['sharpe_ratio']:.2f}")
            
            results[strat_name] = {
                'success': True,
                'tickers_requested': len(test_tickers),
                'tickers_valid': len(bt_results['tickers']),
                'total_return': bt_results['total_return'],
                'cagr': bt_results['cagr'],
                'sharpe': bt_results['sharpe_ratio'],
                'max_drawdown': bt_results['max_drawdown']
            }
            
        except Exception as e:
            print(f"  {FAIL} Exception: {e}")
            results[strat_name] = {'success': False, 'reason': str(e)}
    
    return results

def test_edge_cases():
    """Test backtest engine handles edge cases properly."""
    print_section("Testing Edge Cases")
    
    from backtest_engine import BacktestEngine
    
    all_passed = True
    
    # Test 1: Empty ticker list
    print("  Testing empty ticker list...")
    engine = BacktestEngine()
    result = engine.run_equal_weight_backtest([], "2025-01-01", "2025-06-01")
    if 'error' in result:
        print(f"    {CHECK} Empty list handled: {result['error'][:50]}")
    else:
        print(f"    {WARN} Empty list should return error")
        all_passed = False
    
    # Test 2: Invalid tickers
    print("  Testing invalid tickers...")
    result = engine.run_equal_weight_backtest(['INVALID123', 'NOTREAL456'], "2025-01-01", "2025-06-01")
    if 'error' in result:
        print(f"    {CHECK} Invalid tickers handled: {result['error'][:50]}")
    else:
        print(f"    {WARN} Invalid tickers should return error")
        all_passed = False
    
    # Test 3: Single ticker
    print("  Testing single ticker...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    result = engine.run_equal_weight_backtest(['AAPL'], str(start_date.date()), str(end_date.date()))
    if 'error' not in result:
        print(f"    {CHECK} Single ticker works: Return={result['total_return']:.1%}")
    else:
        print(f"    {FAIL} Single ticker failed: {result['error']}")
        all_passed = False
    
    # Test 4: Ticker with $ prefix (should be cleaned)
    print("  Testing ticker cleaning ($AAPL -> AAPL)...")
    result = engine.run_equal_weight_backtest(['$AAPL', '$MSFT'], str(start_date.date()), str(end_date.date()))
    if 'error' not in result and len(result['tickers']) == 2:
        print(f"    {CHECK} Ticker cleaning works: {result['tickers']}")
    else:
        print(f"    {FAIL} Ticker cleaning issue")
        all_passed = False
    
    return all_passed

def print_summary(results, signal_cache=None):
    """Print test summary."""
    print_header("BACKTEST TEST SUMMARY")
    
    if results is None:
        print("No strategy tests were run (API key missing)")
        return
    
    successful = sum(1 for r in results.values() if r.get('success', False))
    no_signals = sum(1 for r in results.values() if r.get('reason') == 'No signals')
    backtest_errors = sum(1 for r in results.values() 
                         if not r.get('success') and r.get('reason') != 'No signals')
    
    print(f"\nTotal Strategies Tested: {len(results)}")
    print(f"  {CHECK} Successful Backtests: {successful}")
    print(f"  {WARN} No Signal Data (API/Subscription): {no_signals}")
    print(f"  {FAIL} Backtest Errors: {backtest_errors}")
    
    if successful > 0:
        print("\nSuccessful Strategy Metrics:")
        print("-" * 70)
        print(f"{'Strategy':<40} {'Return':<10} {'Sharpe':<10} {'Tickers'}")
        print("-" * 70)
        
        for name, data in results.items():
            if data.get('success'):
                ret = f"{data['total_return']:.1%}"
                sharpe = f"{data['sharpe']:.2f}"
                tickers = f"{data['tickers_valid']}/{data['tickers_requested']}"
                print(f"{name:<40} {ret:<10} {sharpe:<10} {tickers}")
    
    if no_signals > 0:
        print(f"\n{WARN} Strategies with No Signal Data:")
        print("  (These require Quiver API access or politicians haven't traded recently)")
        for name, data in results.items():
            if data.get('reason') == 'No signals':
                print(f"    - {name}")
    
    if backtest_errors > 0:
        print(f"\n{FAIL} Backtest Errors (need investigation):")
        for name, data in results.items():
            if not data.get('success') and data.get('reason') != 'No signals':
                print(f"    - {name}: {data.get('reason', 'Unknown')}")

def main():
    print_header("BACKTEST ENGINE TEST SUITE")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    all_passed = True
    
    # Test 1: Engine availability
    if not test_backtest_engine_availability():
        print(f"\n{FAIL} BacktestEngine not available. Install yfinance:")
        print("  pip install yfinance")
        return 1
    
    # Test 2: Basic backtest
    if not test_backtest_basic():
        print(f"\n{FAIL} Basic backtest failed")
        all_passed = False
    
    # Test 3: Benchmark comparison
    if not test_benchmark_comparison():
        print(f"\n{FAIL} Benchmark comparison failed")
        all_passed = False
    
    # Test 4: Weighted backtest
    if not test_weighted_backtest():
        print(f"\n{FAIL} Weighted backtest failed")
        all_passed = False
    
    # Test 5: Edge cases
    if not test_edge_cases():
        print(f"\n{FAIL} Some edge case tests failed")
        all_passed = False
    
    # Test 6: Fetch all strategy signals (with caching)
    signal_cache = fetch_all_strategy_signals()
    
    # Test 7: Strategy backtests (using cached signals)
    backtest_results = test_strategy_backtests(signal_cache)
    
    # Print summary
    print_summary(backtest_results, signal_cache)
    
    print_header("TEST COMPLETE")
    
    if all_passed:
        print(f"{CHECK} All core tests passed!")
    else:
        print(f"{FAIL} Some tests failed - review output above")
    
    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())
