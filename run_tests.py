#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Convenient test runner for the strategy testing suite.

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py --unit             # Run only unit tests
    python run_tests.py --integration      # Run only integration tests
    python run_tests.py --api              # Run API endpoint tests
    python run_tests.py --quick            # Run quick smoke tests
    python run_tests.py --verbose          # Verbose output
"""

import sys
import os
import argparse
import unittest
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    # Set console to UTF-8 mode
    import locale
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python < 3.7
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
BOLD = '\033[1m'
RESET = '\033[0m'

# Use ASCII checkmarks/crosses for Windows compatibility
CHECK = '✓' if sys.platform != 'win32' else '√'
CROSS = '✗' if sys.platform != 'win32' else 'X'
WARNING = '⚠' if sys.platform != 'win32' else '!'


def print_header(text):
    """Print a formatted header."""
    print(f"\n{BLUE}{BOLD}{'=' * 70}{RESET}")
    print(f"{BLUE}{BOLD}{text.center(70)}{RESET}")
    print(f"{BLUE}{BOLD}{'=' * 70}{RESET}\n")


def print_section(text):
    """Print a formatted section."""
    print(f"\n{YELLOW}{text}{RESET}")
    print(f"{YELLOW}{'-' * len(text)}{RESET}")


def check_environment():
    """Check if environment is properly configured."""
    from dotenv import load_dotenv
    load_dotenv()
    
    issues = []
    warnings = []
    
    # Check API key
    api_key = os.getenv('QUIVER_API_KEY')
    if not api_key:
        issues.append("QUIVER_API_KEY not found in .env file")
    elif len(api_key) < 10:
        warnings.append("QUIVER_API_KEY looks suspiciously short")
    
    # Check required files
    required_files = [
        'quiver_signals.py',
        'quiver_engine.py',
        'test_strategies.py',
        'test_api_endpoints.py'
    ]
    
    for file in required_files:
        if not os.path.exists(file):
            issues.append(f"Required file not found: {file}")
    
    return issues, warnings


def run_unit_tests(verbosity=2):
    """Run unit tests only."""
    print_section("Running Unit Tests")
    
    from test_strategies import (
        TestQuiverStrategyEngine,
        TestCongressBuysStrategy,
        TestDanMeuserStrategy,
        TestSectorInsiderStrategy,
        TestMichaelBurryStrategy,
        TestLobbyingGrowthStrategy,
        TestQuiverSignals,
        TestStrategyDataProcessing,
        TestErrorHandling
    )
    from test_metrics_offline import TestMetricsUtils, TestHtmlRenderer
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    test_classes = [
        TestQuiverStrategyEngine,
        TestCongressBuysStrategy,
        TestDanMeuserStrategy,
        TestSectorInsiderStrategy,
        TestMichaelBurryStrategy,
        TestLobbyingGrowthStrategy,
        TestQuiverSignals,
        TestStrategyDataProcessing,
        TestErrorHandling,
        TestMetricsUtils,
        TestHtmlRenderer,
    ]
    
    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))
    
    runner = unittest.TextTestRunner(verbosity=verbosity)
    return runner.run(suite)


def run_integration_tests(verbosity=2):
    """Run integration tests only."""
    print_section("Running Integration Tests")
    
    from test_strategies import TestIntegration
    
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestIntegration)
    
    runner = unittest.TextTestRunner(verbosity=verbosity)
    return runner.run(suite)


def run_all_tests(verbosity=2):
    """Run all tests."""
    print_section("Running All Tests")
    
    from test_strategies import run_tests
    return run_tests(verbosity=verbosity)


def run_api_tests():
    """Run API endpoint tests."""
    print_section("Running API Endpoint Tests")
    
    from test_api_endpoints import run_all_strategy_tests
    return run_all_strategy_tests()


def run_quick_tests(verbosity=1):
    """Run quick smoke tests."""
    print_section("Running Quick Smoke Tests")
    
    from test_strategies import (
        TestQuiverStrategyEngine,
        TestQuiverSignals
    )
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Only run a few key tests
    suite.addTest(TestQuiverStrategyEngine('test_engine_initialization'))
    suite.addTest(TestQuiverStrategyEngine('test_clean_ticker_list'))
    suite.addTest(TestQuiverSignals('test_initialization'))
    suite.addTest(TestQuiverSignals('test_get_combined_portfolio'))
    
    runner = unittest.TextTestRunner(verbosity=verbosity)
    return runner.run(suite)


def print_summary(result, test_type="Tests"):
    """Print test summary."""
    print_section("Test Summary")
    
    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    successes = total - failures - errors
    
    print(f"  {test_type} run: {total}")
    print(f"  {GREEN}{CHECK} Successes: {successes}{RESET}")
    
    if failures > 0:
        print(f"  {YELLOW}{WARNING} Failures: {failures}{RESET}")
    
    if errors > 0:
        print(f"  {RED}{CROSS} Errors: {errors}{RESET}")
    
    success_rate = (successes / total * 100) if total > 0 else 0
    print(f"  Success rate: {success_rate:.1f}%")
    
    if result.wasSuccessful():
        print(f"\n{GREEN}{BOLD}All tests passed! {CHECK}{RESET}")
    else:
        print(f"\n{RED}{BOLD}Some tests failed! {CROSS}{RESET}")
    
    return result.wasSuccessful()


def main():
    parser = argparse.ArgumentParser(
        description='Run strategy tests',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_tests.py                 # Run all tests
  python run_tests.py --unit          # Run only unit tests
  python run_tests.py --integration   # Run only integration tests
  python run_tests.py --api           # Run API endpoint tests
  python run_tests.py --quick         # Run quick smoke tests
  python run_tests.py --verbose       # Verbose output
        """
    )
    
    parser.add_argument('--unit', action='store_true',
                      help='Run only unit tests')
    parser.add_argument('--integration', action='store_true',
                      help='Run only integration tests')
    parser.add_argument('--api', action='store_true',
                      help='Run API endpoint tests')
    parser.add_argument('--quick', action='store_true',
                      help='Run quick smoke tests')
    parser.add_argument('--verbose', '-v', action='store_true',
                      help='Verbose output')
    parser.add_argument('--quiet', '-q', action='store_true',
                      help='Quiet output')
    
    args = parser.parse_args()
    
    # Determine verbosity
    if args.quiet:
        verbosity = 0
    elif args.verbose:
        verbosity = 2
    else:
        verbosity = 1
    
    # Print header
    print_header("STRATEGY TESTING SUITE")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check environment
    print_section("Environment Check")
    issues, warnings = check_environment()
    
    if warnings:
        for warning in warnings:
            print(f"{YELLOW}{WARNING} Warning: {warning}{RESET}")
    
    if issues:
        print(f"\n{RED}Environment issues detected:{RESET}")
        for issue in issues:
            print(f"  {RED}{CROSS} {issue}{RESET}")
        print(f"\n{RED}Please fix these issues before running tests.{RESET}")
        return 1
    else:
        print(f"{GREEN}{CHECK} Environment configured correctly{RESET}")
    
    # Run tests based on arguments
    all_passed = True
    
    if args.quick:
        result = run_quick_tests(verbosity)
        all_passed = print_summary(result, "Quick tests")
    
    elif args.unit:
        result = run_unit_tests(verbosity)
        all_passed = print_summary(result, "Unit tests")
    
    elif args.integration:
        result = run_integration_tests(verbosity)
        all_passed = print_summary(result, "Integration tests")
    
    elif args.api:
        run_api_tests()
        # API tests have their own summary
        all_passed = True
    
    else:
        # Run all tests
        result = run_all_tests(verbosity)
        all_passed = print_summary(result, "Tests")
    
    print("\n" + "=" * 70 + "\n")
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
