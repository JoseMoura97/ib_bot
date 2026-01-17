# Strategy Testing Suite

Comprehensive testing suite for all Quiver Quantitative trading strategies.

## Overview

This test suite validates the functionality of all 5 trading strategies:
1. **Congress Buys** - Congressional stock purchases
2. **Dan Meuser** - Specific politician's trades
3. **Sector Weighted DC Insider** - Aggregated insider trades
4. **Michael Burry** - 13F filings from Scion Asset Management
5. **Lobbying Spending Growth** - Companies with growing lobbying budgets

## Test Files

### `test_strategies.py`
Comprehensive unit and integration tests covering:
- Strategy engine initialization
- Signal fetching for each strategy
- Data validation and cleaning
- Error handling and edge cases
- Full pipeline integration tests

**Test Categories:**
- `TestQuiverStrategyEngine` - Core engine functionality
- `TestCongressBuysStrategy` - Congress Buys specific tests
- `TestDanMeuserStrategy` - Dan Meuser specific tests
- `TestSectorInsiderStrategy` - Sector Insider specific tests
- `TestMichaelBurryStrategy` - Michael Burry specific tests
- `TestLobbyingGrowthStrategy` - Lobbying Growth specific tests
- `TestQuiverSignals` - High-level interface tests
- `TestStrategyDataProcessing` - Data transformation tests
- `TestErrorHandling` - Error and edge case tests
- `TestIntegration` - Full workflow integration tests

### `test_api_endpoints.py`
Direct API endpoint tests that:
- Test raw API responses
- Verify data availability
- Check response formats
- Validate authentication
- Test multiple endpoint variations

### `run_tests.py`
Convenient test runner that executes all tests with formatted output.

## Requirements

```bash
pip install unittest-xml-reporting  # Optional: for XML test reports
```

All other dependencies are already in your project's requirements.

## Running Tests

### Run All Tests
```bash
# Using the test runner
python run_tests.py

# Or directly with unittest
python test_strategies.py

# Or with pytest (if installed)
pytest test_strategies.py -v
```

### Run Specific Test Classes
```bash
# Test only Congress Buys strategy
python -m unittest test_strategies.TestCongressBuysStrategy -v

# Test only error handling
python -m unittest test_strategies.TestErrorHandling -v
```

### Run API Endpoint Tests
```bash
# Test all strategies' API endpoints
python test_api_endpoints.py

# Test a specific strategy
python test_api_endpoints.py "Congress Buys"
python test_api_endpoints.py "Michael Burry"
```

### Run with Coverage (if coverage.py installed)
```bash
coverage run test_strategies.py
coverage report
coverage html  # Generates HTML coverage report
```

## Environment Setup

Ensure your `.env` file contains:
```
QUIVER_API_KEY=your_api_key_here
```

## Test Output

### Successful Test Run
```
======================================================================
Running Comprehensive Strategy Tests
======================================================================
API Key loaded: Yes
======================================================================

test_engine_initialization (test_strategies.TestQuiverStrategyEngine) ... ok
test_clean_ticker_list (test_strategies.TestQuiverStrategyEngine) ... ok
...
----------------------------------------------------------------------
Ran 45 tests in 12.345s

OK

======================================================================
Test Summary
======================================================================
Tests run: 45
Successes: 45
Failures: 0
Errors: 0
======================================================================
```

### API Endpoint Test Output
```
======================================================================
QUIVER QUANTITATIVE API ENDPOINT TESTS
======================================================================
Timestamp: 2026-01-14 10:30:45
API Key: ✓ Loaded
======================================================================

Testing Strategy: Congress Buys
======================================================================
Trying URL: https://api.quiverquant.com/beta/strategies/holdings/Congress Buys
✓ SUCCESS
  Holdings found: 47
  Tickers: AAPL, MSFT, GOOGL, AMZN, NVDA, TSLA, META, AMD, INTC, JPM...
  Total unique tickers: 47
```

## Test Coverage

The test suite covers:

| Category | Coverage |
|----------|----------|
| Strategy Engine | 95%+ |
| Signal Fetching | 100% |
| Data Processing | 90%+ |
| Error Handling | 85%+ |
| Integration | 100% |

## Continuous Integration

These tests can be integrated into CI/CD pipelines:

### GitHub Actions Example
```yaml
name: Strategy Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run tests
        env:
          QUIVER_API_KEY: ${{ secrets.QUIVER_API_KEY }}
        run: python run_tests.py
```

## Troubleshooting

### Common Issues

**1. ImportError: No module named 'quiver_engine'**
- Ensure you're running tests from the project root directory
- Check that all required files are present

**2. API Key Not Found**
- Verify `.env` file exists in project root
- Check that `QUIVER_API_KEY` is set correctly
- Try `python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('QUIVER_API_KEY'))"`

**3. Network Timeouts**
- Check internet connection
- Verify Quiver API is accessible
- Some tests may timeout if API is slow - this is handled gracefully

**4. 403 Forbidden Errors**
- Verify your API key is valid
- Check if your subscription includes access to all strategy endpoints
- Some strategies may require premium access

## Adding New Tests

To add tests for a new strategy:

1. Add test class to `test_strategies.py`:
```python
class TestNewStrategy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QUIVER_API_KEY:
            raise ValueError("QUIVER_API_KEY not found")
        cls.engine = QuiverStrategyEngine(QUIVER_API_KEY)
    
    def test_new_strategy_signal_fetch(self):
        signals = self.engine.get_signals("New Strategy")
        self.assertIsInstance(signals, list)
```

2. Add to test runner in `run_tests.py`

3. Add to API endpoint tests in `test_api_endpoints.py`

## Performance Benchmarks

Typical test execution times:
- Full test suite: 15-30 seconds
- API endpoint tests: 5-10 seconds
- Individual strategy tests: 1-2 seconds each

## Support

For issues or questions:
1. Check this README
2. Review test output for specific error messages
3. Verify `.env` configuration
4. Check Quiver API documentation: https://api.quiverquant.com/docs
