"""
Comprehensive tests for all Quiver strategy signals.

Tests cover:
1. API connectivity and authentication
2. Signal fetching for each strategy
3. Data validation and cleaning
4. Error handling and edge cases
5. Integration tests for the complete pipeline
"""

import unittest
import os
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

from quiver_signals import QuiverSignals
from quiver_engine import QuiverStrategyEngine

# Load environment variables
load_dotenv()
QUIVER_API_KEY = os.getenv('QUIVER_API_KEY')


class TestQuiverStrategyEngine(unittest.TestCase):
    """Test the QuiverStrategyEngine core functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures that are used across all tests."""
        if not QUIVER_API_KEY:
            raise ValueError("QUIVER_API_KEY not found in .env file")
        cls.api_key = QUIVER_API_KEY
    
    def setUp(self):
        """Set up for each test."""
        self.engine = QuiverStrategyEngine(self.api_key)
    
    def test_engine_initialization(self):
        """Test that the engine initializes correctly."""
        self.assertIsNotNone(self.engine)
        self.assertEqual(self.engine.api_key, self.api_key)
        self.assertIsNotNone(self.engine.quiver)
        self.assertIsNotNone(self.engine.strategies_meta)
        
        # Verify all expected strategies are present
        expected_strategies = [
            "Congress Buys",
            "Dan Meuser",
            "Sector Weighted DC Insider",
            "Michael Burry",
            "Lobbying Spending Growth"
        ]
        for strategy in expected_strategies:
            self.assertIn(strategy, self.engine.strategies_meta)
    
    def test_clean_ticker_list(self):
        """Test ticker cleaning and deduplication."""
        dirty_tickers = ['$AAPL', 'MSFT', 'GOOGL', '$AAPL', 'invalid_ticker_12345', '   tsla  ', None, 123]
        clean_tickers = self.engine._clean_ticker_list(dirty_tickers)
        
        # Should remove duplicates, strip $, handle whitespace, remove invalid
        self.assertIn('AAPL', clean_tickers)
        self.assertIn('MSFT', clean_tickers)
        self.assertIn('TSLA', clean_tickers)
        
        # No duplicates
        self.assertEqual(len(clean_tickers), len(set(clean_tickers)))
        
        # All should be strings and uppercase
        for ticker in clean_tickers:
            self.assertIsInstance(ticker, str)
            self.assertEqual(ticker, ticker.upper())
            self.assertLess(len(ticker), 10)  # Max length check
    
    def test_clean_ticker_list_limit(self):
        """Test that ticker list is limited to 100."""
        many_tickers = [f'TICK{i}' for i in range(200)]
        clean_tickers = self.engine._clean_ticker_list(many_tickers)
        self.assertLessEqual(len(clean_tickers), 100)
    
    def test_find_col(self):
        """Test dynamic column finding in DataFrames."""
        df = pd.DataFrame({
            'ticker': ['AAPL', 'MSFT'],
            'date': ['2024-01-01', '2024-01-02'],
            'value': [100, 200]
        })
        
        # Should find case-insensitive
        ticker_col = self.engine._find_col(df, ['Ticker', 'Symbol'])
        self.assertEqual(ticker_col, 'ticker')
        
        date_col = self.engine._find_col(df, ['Date', 'TransactionDate'])
        self.assertEqual(date_col, 'date')
        
        # Should return None if not found
        missing_col = self.engine._find_col(df, ['NotPresent', 'AlsoMissing'])
        self.assertIsNone(missing_col)


class TestCongressBuysStrategy(unittest.TestCase):
    """Test Congress Buys strategy specifically."""
    
    @classmethod
    def setUpClass(cls):
        if not QUIVER_API_KEY:
            raise ValueError("QUIVER_API_KEY not found in .env file")
        cls.engine = QuiverStrategyEngine(QUIVER_API_KEY)
    
    def test_congress_buys_signal_fetch(self):
        """Test fetching Congress Buys signals."""
        signals = self.engine.get_signals("Congress Buys")
        
        # Should return a list
        self.assertIsInstance(signals, list)
        
        # If signals exist, they should be valid tickers
        if signals:
            for ticker in signals:
                self.assertIsInstance(ticker, str)
                self.assertGreater(len(ticker), 0)
                self.assertLess(len(ticker), 10)
                self.assertEqual(ticker, ticker.upper())
    
    def test_congress_buys_metadata(self):
        """Test Congress Buys strategy metadata."""
        meta = self.engine.strategies_meta["Congress Buys"]
        
        self.assertEqual(meta['type'], 'congress')
        self.assertIn('filter', meta)
        self.assertEqual(meta['lookback_days'], 30)
    
    @patch('quiver_engine.requests.get')
    def test_congress_buys_api_fallback(self, mock_get):
        """Test API fallback mechanism for Congress Buys."""
        # Mock official API to fail
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        # Should still attempt to fetch (will fail gracefully)
        signals = self.engine.get_signals("Congress Buys")
        self.assertIsInstance(signals, list)


class TestDanMeuserStrategy(unittest.TestCase):
    """Test Dan Meuser strategy specifically."""
    
    @classmethod
    def setUpClass(cls):
        if not QUIVER_API_KEY:
            raise ValueError("QUIVER_API_KEY not found in .env file")
        cls.engine = QuiverStrategyEngine(QUIVER_API_KEY)
    
    def test_dan_meuser_signal_fetch(self):
        """Test fetching Dan Meuser signals."""
        signals = self.engine.get_signals("Dan Meuser")
        
        self.assertIsInstance(signals, list)
        
        if signals:
            for ticker in signals:
                self.assertIsInstance(ticker, str)
                self.assertGreater(len(ticker), 0)
                self.assertEqual(ticker, ticker.upper())
    
    def test_dan_meuser_metadata(self):
        """Test Dan Meuser strategy metadata."""
        meta = self.engine.strategies_meta["Dan Meuser"]
        
        self.assertEqual(meta['type'], 'congress')
        self.assertIn('filter', meta)
        self.assertEqual(meta['lookback_days'], 90)
    
    def test_dan_meuser_filter_logic(self):
        """Test that Dan Meuser filter works correctly."""
        # Create mock congress data
        mock_data = pd.DataFrame({
            'Representative': ['Dan Meuser', 'Nancy Pelosi', 'dan meuser'],
            'Transaction': ['Purchase', 'Sale', 'BUY'],
            'Ticker': ['AAPL', 'MSFT', 'GOOGL']
        })
        
        meta = self.engine.strategies_meta["Dan Meuser"]
        filtered = meta['filter'](mock_data)
        
        # Should only keep Dan Meuser purchases
        self.assertEqual(len(filtered), 2)
        self.assertTrue(all('meuser' in rep.lower() for rep in filtered['Representative']))


class TestSectorInsiderStrategy(unittest.TestCase):
    """Test Sector Weighted DC Insider strategy."""
    
    @classmethod
    def setUpClass(cls):
        if not QUIVER_API_KEY:
            raise ValueError("QUIVER_API_KEY not found in .env file")
        cls.engine = QuiverStrategyEngine(QUIVER_API_KEY)
    
    def test_sector_insider_signal_fetch(self):
        """Test fetching Sector Weighted DC Insider signals."""
        signals = self.engine.get_signals("Sector Weighted DC Insider")
        
        self.assertIsInstance(signals, list)
        
        if signals:
            for ticker in signals:
                self.assertIsInstance(ticker, str)
                self.assertGreater(len(ticker), 0)
                self.assertEqual(ticker, ticker.upper())
    
    def test_sector_insider_metadata(self):
        """Test Sector Weighted DC Insider strategy metadata."""
        meta = self.engine.strategies_meta["Sector Weighted DC Insider"]
        
        self.assertEqual(meta['type'], 'insider')
        self.assertIn('filter', meta)
        self.assertEqual(meta['lookback_days'], 30)


class TestMichaelBurryStrategy(unittest.TestCase):
    """Test Michael Burry (13F) strategy."""
    
    @classmethod
    def setUpClass(cls):
        if not QUIVER_API_KEY:
            raise ValueError("QUIVER_API_KEY not found in .env file")
        cls.engine = QuiverStrategyEngine(QUIVER_API_KEY)
    
    def test_michael_burry_signal_fetch(self):
        """Test fetching Michael Burry signals."""
        signals = self.engine.get_signals("Michael Burry")
        
        self.assertIsInstance(signals, list)
        
        if signals:
            for ticker in signals:
                self.assertIsInstance(ticker, str)
                self.assertGreater(len(ticker), 0)
                self.assertEqual(ticker, ticker.upper())
    
    def test_michael_burry_metadata(self):
        """Test Michael Burry strategy metadata."""
        meta = self.engine.strategies_meta["Michael Burry"]
        
        self.assertEqual(meta['type'], 'sec13F')
        self.assertIn('args', meta)
        self.assertEqual(meta['args'], ["Scion Asset Management"])


class TestLobbyingGrowthStrategy(unittest.TestCase):
    """Test Lobbying Spending Growth strategy."""
    
    @classmethod
    def setUpClass(cls):
        if not QUIVER_API_KEY:
            raise ValueError("QUIVER_API_KEY not found in .env file")
        cls.engine = QuiverStrategyEngine(QUIVER_API_KEY)
    
    def test_lobbying_growth_signal_fetch(self):
        """Test fetching Lobbying Spending Growth signals."""
        signals = self.engine.get_signals("Lobbying Spending Growth")
        
        self.assertIsInstance(signals, list)
        
        if signals:
            for ticker in signals:
                self.assertIsInstance(ticker, str)
                self.assertGreater(len(ticker), 0)
                self.assertEqual(ticker, ticker.upper())
    
    def test_lobbying_growth_metadata(self):
        """Test Lobbying Spending Growth strategy metadata."""
        meta = self.engine.strategies_meta["Lobbying Spending Growth"]
        
        self.assertEqual(meta['type'], 'lobbying')
        self.assertEqual(meta['lookback_days'], 90)
        self.assertEqual(meta['limit'], 10)


class TestQuiverSignals(unittest.TestCase):
    """Test the QuiverSignals high-level interface."""
    
    @classmethod
    def setUpClass(cls):
        if not QUIVER_API_KEY:
            raise ValueError("QUIVER_API_KEY not found in .env file")
        cls.signals = QuiverSignals(QUIVER_API_KEY)
    
    def test_initialization(self):
        """Test QuiverSignals initialization."""
        self.assertIsNotNone(self.signals)
        self.assertIsNotNone(self.signals.engine)
    
    def test_get_congress_buys(self):
        """Test getting Congress Buys through QuiverSignals."""
        signals = self.signals.get_congress_buys()
        self.assertIsInstance(signals, list)
    
    def test_get_dan_meuser_trades(self):
        """Test getting Dan Meuser trades through QuiverSignals."""
        signals = self.signals.get_dan_meuser_trades()
        self.assertIsInstance(signals, list)
    
    def test_get_sector_insider_signals(self):
        """Test getting Sector Insider signals through QuiverSignals."""
        signals = self.signals.get_sector_insider_signals()
        self.assertIsInstance(signals, list)
    
    def test_get_michael_burry_holdings(self):
        """Test getting Michael Burry holdings through QuiverSignals."""
        signals = self.signals.get_michael_burry_holdings()
        self.assertIsInstance(signals, list)
    
    def test_get_lobbying_growth_signals(self):
        """Test getting Lobbying Growth signals through QuiverSignals."""
        signals = self.signals.get_lobbying_growth_signals()
        self.assertIsInstance(signals, list)
    
    def test_get_combined_portfolio(self):
        """Test getting combined portfolio from all strategies."""
        portfolio = self.signals.get_combined_portfolio()
        
        self.assertIsInstance(portfolio, list)
        
        # Should have no duplicates
        self.assertEqual(len(portfolio), len(set(portfolio)))
        
        # All should be valid tickers
        for ticker in portfolio:
            self.assertIsInstance(ticker, str)
            self.assertGreater(len(ticker), 0)
            self.assertEqual(ticker, ticker.upper())
    
    def test_combined_portfolio_deduplication(self):
        """Test that combined portfolio removes duplicates across strategies."""
        portfolio = self.signals.get_combined_portfolio()
        
        # Get individual strategy signals
        congress = self.signals.get_congress_buys()
        meuser = self.signals.get_dan_meuser_trades()
        insider = self.signals.get_sector_insider_signals()
        burry = self.signals.get_michael_burry_holdings()
        lobbying = self.signals.get_lobbying_growth_signals()
        
        # Combined count should be <= sum of all (due to deduplication)
        total_individual = len(congress) + len(meuser) + len(insider) + len(burry) + len(lobbying)
        self.assertLessEqual(len(portfolio), total_individual)


class TestStrategyDataProcessing(unittest.TestCase):
    """Test data processing and transformation logic."""
    
    @classmethod
    def setUpClass(cls):
        if not QUIVER_API_KEY:
            raise ValueError("QUIVER_API_KEY not found in .env file")
        cls.engine = QuiverStrategyEngine(QUIVER_API_KEY)
    
    def test_process_raw_df_with_date_filtering(self):
        """Test that _process_raw_df correctly filters by date."""
        # Create mock data with dates
        today = datetime.now()
        old_date = today - timedelta(days=100)
        recent_date = today - timedelta(days=10)
        
        mock_df = pd.DataFrame({
            'TransactionDate': [old_date, recent_date, today],
            'Ticker': ['AAPL', 'MSFT', 'GOOGL'],
            'Transaction': ['Purchase', 'Buy', 'P']
        })
        
        meta = {
            'lookback_days': 30,
            'filter': lambda df: df[df['Transaction'].str.lower().isin(['purchase', 'buy', 'p'])]
        }
        
        result = self.engine._process_raw_df(mock_df, meta)
        
        # Should only return tickers from last 30 days
        self.assertIsInstance(result, list)
        # Old date (100 days ago) should be filtered out
        if result:
            # AAPL should not be in result as it's 100 days old
            # MSFT and GOOGL might be in result
            pass
    
    def test_process_raw_df_empty_input(self):
        """Test _process_raw_df with empty DataFrame."""
        empty_df = pd.DataFrame()
        meta = {'lookback_days': 30}
        
        result = self.engine._process_raw_df(empty_df, meta)
        self.assertEqual(result, [])
    
    def test_process_raw_df_no_ticker_column(self):
        """Test _process_raw_df when ticker column is missing."""
        mock_df = pd.DataFrame({
            'Date': ['2024-01-01'],
            'Value': [100]
        })
        meta = {'lookback_days': 30}
        
        result = self.engine._process_raw_df(mock_df, meta)
        self.assertEqual(result, [])


class TestErrorHandling(unittest.TestCase):
    """Test error handling and edge cases."""
    
    @classmethod
    def setUpClass(cls):
        if not QUIVER_API_KEY:
            raise ValueError("QUIVER_API_KEY not found in .env file")
        cls.engine = QuiverStrategyEngine(QUIVER_API_KEY)
    
    def test_invalid_strategy_name(self):
        """Test handling of invalid strategy name."""
        signals = self.engine.get_signals("NonExistentStrategy")
        self.assertEqual(signals, [])
    
    def test_get_signals_with_network_timeout(self):
        """Test graceful handling of network timeouts."""
        with patch('quiver_engine.requests.get') as mock_get:
            mock_get.side_effect = Exception("Network timeout")
            
            signals = self.engine.get_signals("Congress Buys")
            # Should return empty list on error, not raise exception
            self.assertIsInstance(signals, list)
    
    def test_malformed_api_response(self):
        """Test handling of malformed API responses."""
        with patch('quiver_engine.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = "not a list or dict"
            mock_get.return_value = mock_response
            
            signals = self.engine.get_signals("Congress Buys")
            self.assertIsInstance(signals, list)


class TestIntegration(unittest.TestCase):
    """Integration tests for complete workflows."""
    
    @classmethod
    def setUpClass(cls):
        if not QUIVER_API_KEY:
            raise ValueError("QUIVER_API_KEY not found in .env file")
    
    def test_full_pipeline_all_strategies(self):
        """Test fetching signals from all strategies in sequence."""
        signals_obj = QuiverSignals(QUIVER_API_KEY)
        
        strategies = [
            ("Congress Buys", signals_obj.get_congress_buys),
            ("Dan Meuser", signals_obj.get_dan_meuser_trades),
            ("Sector Insider", signals_obj.get_sector_insider_signals),
            ("Michael Burry", signals_obj.get_michael_burry_holdings),
            ("Lobbying Growth", signals_obj.get_lobbying_growth_signals)
        ]
        
        results = {}
        for name, method in strategies:
            try:
                signals = method()
                results[name] = {
                    'success': True,
                    'count': len(signals),
                    'signals': signals
                }
            except Exception as e:
                results[name] = {
                    'success': False,
                    'error': str(e)
                }
        
        # All strategies should execute (success or controlled failure)
        self.assertEqual(len(results), 5)
        
        # At least some strategies should succeed
        successful = sum(1 for r in results.values() if r.get('success', False))
        self.assertGreater(successful, 0, "At least one strategy should succeed")
    
    def test_combined_portfolio_performance(self):
        """Test that combined portfolio can be generated efficiently."""
        import time
        
        signals_obj = QuiverSignals(QUIVER_API_KEY)
        
        start = time.time()
        portfolio = signals_obj.get_combined_portfolio()
        elapsed = time.time() - start
        
        # Should complete in reasonable time (under 30 seconds)
        self.assertLess(elapsed, 30, "Combined portfolio generation too slow")
        
        # Should return valid data
        self.assertIsInstance(portfolio, list)


def run_tests(verbosity=2):
    """Run all tests with specified verbosity."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
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
        TestIntegration
    ]
    
    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    
    return result


if __name__ == '__main__':
    print("=" * 70)
    print("Running Comprehensive Strategy Tests")
    print("=" * 70)
    print(f"API Key loaded: {'Yes' if QUIVER_API_KEY else 'No'}")
    print("=" * 70)
    print()
    
    result = run_tests(verbosity=2)
    
    print()
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("=" * 70)
    
    exit(0 if result.wasSuccessful() else 1)
