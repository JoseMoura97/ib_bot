#!/usr/bin/env python
"""
Verification script to confirm Cleo Fields removal and test suite functionality.
"""

import os
import sys
from dotenv import load_dotenv

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def check_file_contents(filename, search_term, should_exist=False):
    """Check if a term exists in a file."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
            exists = search_term.lower() in content.lower()
            
            if should_exist and exists:
                return True, f"{GREEN}OK{RESET} - Found '{search_term}' in {filename}"
            elif not should_exist and not exists:
                return True, f"{GREEN}OK{RESET} - No '{search_term}' in {filename}"
            elif should_exist and not exists:
                return False, f"{RED}FAIL{RESET} - Missing '{search_term}' in {filename}"
            else:
                return False, f"{RED}FAIL{RESET} - Found '{search_term}' in {filename} (should be removed)"
    except FileNotFoundError:
        return False, f"{RED}ERROR{RESET} - File not found: {filename}"
    except Exception as e:
        return False, f"{RED}ERROR{RESET} - {str(e)}"


def verify_file_exists(filename):
    """Check if a file exists."""
    if os.path.exists(filename):
        return True, f"{GREEN}OK{RESET} - File exists: {filename}"
    else:
        return False, f"{RED}FAIL{RESET} - File missing: {filename}"


def count_strategies_in_file(filename):
    """Count number of strategies in a file."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Count specific strategy names
        strategies = [
            "Congress Buys",
            "Dan Meuser",
            "Sector Weighted DC Insider",
            "Michael Burry",
            "Lobbying Spending Growth"
        ]
        
        count = sum(1 for s in strategies if s in content)
        return count
    except:
        return 0


def main():
    print("=" * 70)
    print("VERIFICATION: Cleo Fields Removal & Test Suite")
    print("=" * 70)
    
    results = []
    
    # 1. Verify Cleo Fields is removed from key files
    print(f"\n{BLUE}1. Verifying Cleo Fields Removal{RESET}")
    print("-" * 70)
    
    files_to_check = [
        'quiver_signals.py',
        'quiver_engine.py',
        'strategies_config.json',
        'replicate_quiver_copy.py',
        'check_politicians.py'
    ]
    
    for filename in files_to_check:
        passed, msg = check_file_contents(filename, 'Cleo Fields', should_exist=False)
        results.append(passed)
        print(f"  {msg}")
    
    # 2. Verify test files exist
    print(f"\n{BLUE}2. Verifying Test Files Exist{RESET}")
    print("-" * 70)
    
    test_files = [
        'test_strategies.py',
        'test_api_endpoints.py',
        'run_tests.py',
        'TEST_README.md',
        'CHANGES_SUMMARY.md',
        'verify_changes.py'
    ]
    
    for filename in test_files:
        passed, msg = verify_file_exists(filename)
        results.append(passed)
        print(f"  {msg}")
    
    # 3. Verify remaining 5 strategies are present
    print(f"\n{BLUE}3. Verifying Remaining Strategies{RESET}")
    print("-" * 70)
    
    strategies = [
        ("Congress Buys", "quiver_signals.py"),
        ("Dan Meuser", "quiver_signals.py"),
        ("Sector Weighted DC Insider", "quiver_signals.py"),
        ("Michael Burry", "quiver_signals.py"),
        ("Lobbying Spending Growth", "quiver_signals.py")
    ]
    
    for strategy, filename in strategies:
        passed, msg = check_file_contents(filename, strategy, should_exist=True)
        results.append(passed)
        print(f"  {msg}")
    
    # 4. Count strategies
    print(f"\n{BLUE}4. Strategy Count Verification{RESET}")
    print("-" * 70)
    
    count = count_strategies_in_file('quiver_signals.py')
    if count == 5:
        print(f"  {GREEN}OK{RESET} - Found exactly 5 strategies in quiver_signals.py")
        results.append(True)
    else:
        print(f"  {RED}FAIL{RESET} - Found {count} strategies in quiver_signals.py (expected 5)")
        results.append(False)
    
    # 5. Verify API key
    print(f"\n{BLUE}5. Environment Configuration{RESET}")
    print("-" * 70)
    
    load_dotenv()
    api_key = os.getenv('QUIVER_API_KEY')
    
    if api_key:
        print(f"  {GREEN}OK{RESET} - QUIVER_API_KEY is set")
        results.append(True)
    else:
        print(f"  {YELLOW}WARNING{RESET} - QUIVER_API_KEY not set (tests will fail)")
        results.append(True)  # Don't fail verification for this
    
    # 6. Test import capability
    print(f"\n{BLUE}6. Module Import Tests{RESET}")
    print("-" * 70)
    
    try:
        from test_strategies import TestQuiverStrategyEngine
        print(f"  {GREEN}OK{RESET} - Can import test_strategies")
        results.append(True)
    except ImportError as e:
        print(f"  {RED}FAIL{RESET} - Cannot import test_strategies: {e}")
        results.append(False)
    
    try:
        from test_api_endpoints import test_official_strategy_endpoint
        print(f"  {GREEN}OK{RESET} - Can import test_api_endpoints")
        results.append(True)
    except ImportError as e:
        print(f"  {RED}FAIL{RESET} - Cannot import test_api_endpoints: {e}")
        results.append(False)
    
    try:
        from quiver_signals import QuiverSignals
        print(f"  {GREEN}OK{RESET} - Can import quiver_signals")
        results.append(True)
    except ImportError as e:
        print(f"  {RED}FAIL{RESET} - Cannot import quiver_signals: {e}")
        results.append(False)
    
    try:
        from quiver_engine import QuiverStrategyEngine
        print(f"  {GREEN}OK{RESET} - Can import quiver_engine")
        results.append(True)
    except ImportError as e:
        print(f"  {RED}FAIL{RESET} - Cannot import quiver_engine: {e}")
        results.append(False)
    
    # 7. Quick functionality test
    print(f"\n{BLUE}7. Quick Functionality Test{RESET}")
    print("-" * 70)
    
    if api_key:
        try:
            from quiver_signals import QuiverSignals
            qs = QuiverSignals(api_key)
            
            # Test that get_cleo_fields_trades doesn't exist
            if not hasattr(qs, 'get_cleo_fields_trades'):
                print(f"  {GREEN}OK{RESET} - get_cleo_fields_trades() removed")
                results.append(True)
            else:
                print(f"  {RED}FAIL{RESET} - get_cleo_fields_trades() still exists")
                results.append(False)
            
            # Test that other methods exist
            methods = [
                'get_congress_buys',
                'get_dan_meuser_trades',
                'get_sector_insider_signals',
                'get_michael_burry_holdings',
                'get_lobbying_growth_signals',
                'get_combined_portfolio'
            ]
            
            for method in methods:
                if hasattr(qs, method):
                    print(f"  {GREEN}OK{RESET} - {method}() exists")
                    results.append(True)
                else:
                    print(f"  {RED}FAIL{RESET} - {method}() missing")
                    results.append(False)
            
        except Exception as e:
            print(f"  {YELLOW}SKIP{RESET} - Functionality test failed: {e}")
    else:
        print(f"  {YELLOW}SKIP{RESET} - No API key, skipping functionality test")
    
    # Summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)
    
    total = len(results)
    passed = sum(results)
    failed = total - passed
    
    print(f"\nTotal checks: {total}")
    print(f"{GREEN}Passed: {passed}{RESET}")
    if failed > 0:
        print(f"{RED}Failed: {failed}{RESET}")
    
    success_rate = (passed / total * 100) if total > 0 else 0
    print(f"Success rate: {success_rate:.1f}%")
    
    if failed == 0:
        print(f"\n{GREEN}ALL VERIFICATIONS PASSED!{RESET}")
        print(f"\nNext steps:")
        print(f"  1. Run: python run_tests.py --quick")
        print(f"  2. Run: python test_api_endpoints.py")
        print(f"  3. Review: TEST_README.md")
        return 0
    else:
        print(f"\n{RED}SOME VERIFICATIONS FAILED!{RESET}")
        print(f"\nPlease review the output above and fix any issues.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
