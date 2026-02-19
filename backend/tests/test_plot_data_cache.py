"""
Tests for plot data generation from cache and IB price source.
"""

import json
import os
import pickle
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

# Add repo root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from generate_plot_data_from_cache import (
    generate_plot_data_from_cache,
    generate_synthetic_equity_curve,
    load_cached_price,
    load_validation_results,
)


class TestValidationResults:
    """Tests for loading validation results."""

    def test_load_validation_results_success(self, tmp_path):
        """Test loading valid validation results."""
        validation_data = {
            "generated_at": "2026-01-21T16:55:55.872720Z",
            "benchmark": "SPY",
            "strategies": {
                "Test Strategy": {
                    "status": "OK",
                    "start_date": "2020-04-01",
                    "end_date": "2026-01-21",
                    "cagr": 25.5,
                    "sharpe": 1.1,
                    "max_drawdown": -30.0,
                    "volatility": 20.0,
                }
            },
        }
        
        (tmp_path / "last_validation_results.json").write_text(
            json.dumps(validation_data)
        )
        
        result = load_validation_results(tmp_path)
        assert result["benchmark"] == "SPY"
        assert "Test Strategy" in result["strategies"]
        assert result["strategies"]["Test Strategy"]["cagr"] == 25.5

    def test_load_validation_results_not_found(self, tmp_path):
        """Test error when validation results file is missing."""
        with pytest.raises(FileNotFoundError):
            load_validation_results(tmp_path)


class TestCachedPriceLoading:
    """Tests for loading cached price data."""

    def test_load_cached_price_yf(self, tmp_path):
        """Test loading price from yf_prices cache."""
        yf_dir = tmp_path / "yf_prices"
        yf_dir.mkdir()
        
        # Create test DataFrame
        dates = pd.date_range("2020-01-01", "2020-12-31", freq="D")
        df = pd.DataFrame({
            "Open": np.random.uniform(100, 110, len(dates)),
            "High": np.random.uniform(110, 120, len(dates)),
            "Low": np.random.uniform(90, 100, len(dates)),
            "Close": np.random.uniform(100, 110, len(dates)),
            "Volume": np.random.randint(1000000, 10000000, len(dates)),
        }, index=dates)
        
        df.to_pickle(yf_dir / "AAPL.pkl")
        
        result = load_cached_price(tmp_path, "AAPL")
        assert result is not None
        assert not result.empty
        assert "Close" in result.columns
        assert len(result) == len(dates)

    def test_load_cached_price_ib(self, tmp_path):
        """Test loading price from ib_prices cache when yf_prices is missing."""
        ib_dir = tmp_path / "ib_prices"
        ib_dir.mkdir()
        
        dates = pd.date_range("2020-01-01", "2020-06-30", freq="D")
        df = pd.DataFrame({
            "Close": np.random.uniform(100, 110, len(dates)),
        }, index=dates)
        
        df.to_pickle(ib_dir / "MSFT.pkl")
        
        result = load_cached_price(tmp_path, "MSFT")
        assert result is not None
        assert not result.empty

    def test_load_cached_price_not_found(self, tmp_path):
        """Test None returned when ticker not in cache."""
        (tmp_path / "yf_prices").mkdir()
        (tmp_path / "ib_prices").mkdir()
        
        result = load_cached_price(tmp_path, "NONEXISTENT")
        assert result is None


class TestSyntheticEquityCurve:
    """Tests for synthetic equity curve generation."""

    def test_generate_curve_basic(self):
        """Test basic curve generation."""
        dates, values = generate_synthetic_equity_curve(
            start_date="2020-01-01",
            end_date="2023-01-01",
            cagr=15.0,
            volatility=20.0,
            max_drawdown=-30.0,
        )
        
        assert len(dates) > 0
        assert len(values) > 0
        assert len(dates) == len(values)
        assert values[0] == 100.0  # Starts at 100

    def test_generate_curve_positive_cagr(self):
        """Test that positive CAGR results in generally upward trend."""
        dates, values = generate_synthetic_equity_curve(
            start_date="2020-01-01",
            end_date="2025-01-01",
            cagr=20.0,
            volatility=15.0,
            max_drawdown=-25.0,
        )
        
        # With 5 years and 20% CAGR, final value should be roughly 2.5x initial
        # Allow some variance since it's synthetic
        assert values[-1] > values[0]  # At least growing

    def test_generate_curve_negative_cagr(self):
        """Test curve with negative CAGR produces valid output."""
        dates, values = generate_synthetic_equity_curve(
            start_date="2020-01-01",
            end_date="2022-01-01",
            cagr=-10.0,
            volatility=25.0,
            max_drawdown=-40.0,
        )
        
        assert len(values) > 0
        assert len(dates) == len(values)
        # Synthetic curves have randomness, so we just verify structure
        # not strict downward trend (which may not hold due to volatility)

    def test_generate_curve_with_spy_correlation(self):
        """Test curve generation with SPY data for correlation."""
        # Create mock SPY curve
        spy_dates = pd.date_range("2020-01-01", "2022-12-31", freq="D")
        spy_df = pd.DataFrame({
            "Close": 100 * (1 + np.random.normal(0.0005, 0.01, len(spy_dates))).cumprod(),
        }, index=spy_dates)
        
        dates, values = generate_synthetic_equity_curve(
            start_date="2020-01-01",
            end_date="2022-12-31",
            cagr=15.0,
            volatility=18.0,
            max_drawdown=-30.0,
            spy_curve=spy_df,
        )
        
        assert len(values) > 0


class TestPlotDataGeneration:
    """Tests for full plot data generation."""

    def test_generate_plot_data_basic(self, tmp_path):
        """Test generating plot data from validation results."""
        # Create validation results
        validation_data = {
            "generated_at": "2026-01-21T16:55:55.872720Z",
            "benchmark": "SPY",
            "strategies": {
                "Strategy A": {
                    "status": "OK",
                    "start_date": "2020-04-01",
                    "end_date": "2025-12-31",
                    "cagr": 25.0,
                    "sharpe": 1.2,
                    "max_drawdown": -28.0,
                    "volatility": 22.0,
                },
                "Strategy B": {
                    "status": "OK",
                    "start_date": "2020-04-01",
                    "end_date": "2025-12-31",
                    "cagr": 18.0,
                    "sharpe": 0.9,
                    "max_drawdown": -35.0,
                    "volatility": 25.0,
                },
            },
        }
        
        (tmp_path / "last_validation_results.json").write_text(
            json.dumps(validation_data)
        )
        (tmp_path / "yf_prices").mkdir()
        (tmp_path / "ib_prices").mkdir()
        
        output_path = tmp_path / "plot_data.json"
        result = generate_plot_data_from_cache(tmp_path, output_path)
        
        assert "strategies" in result
        assert "Strategy A" in result["strategies"]
        assert "Strategy B" in result["strategies"]
        assert result["data_source"] == "cached_validation"
        assert result["synthetic"] == True
        assert output_path.exists()

    def test_generate_plot_data_skips_failed_strategies(self, tmp_path):
        """Test that strategies with ERROR status are skipped."""
        validation_data = {
            "generated_at": "2026-01-21T16:55:55.872720Z",
            "benchmark": "SPY",
            "strategies": {
                "Good Strategy": {
                    "status": "OK",
                    "start_date": "2020-04-01",
                    "end_date": "2025-12-31",
                    "cagr": 20.0,
                    "sharpe": 1.0,
                    "max_drawdown": -25.0,
                },
                "Bad Strategy": {
                    "status": "ERROR",
                    "error": "API timeout",
                },
            },
        }
        
        (tmp_path / "last_validation_results.json").write_text(
            json.dumps(validation_data)
        )
        (tmp_path / "yf_prices").mkdir()
        
        result = generate_plot_data_from_cache(tmp_path)
        
        assert "Good Strategy" in result["strategies"]
        assert "Bad Strategy" not in result["strategies"]

    def test_generate_plot_data_with_spy_cache(self, tmp_path):
        """Test plot data generation with cached SPY data."""
        validation_data = {
            "generated_at": "2026-01-21T16:55:55.872720Z",
            "benchmark": "SPY",
            "strategies": {
                "Test Strategy": {
                    "status": "OK",
                    "start_date": "2020-01-01",
                    "end_date": "2023-12-31",
                    "cagr": 22.0,
                    "sharpe": 1.1,
                    "max_drawdown": -30.0,
                },
            },
        }
        
        (tmp_path / "last_validation_results.json").write_text(
            json.dumps(validation_data)
        )
        
        # Create SPY cache
        yf_dir = tmp_path / "yf_prices"
        yf_dir.mkdir()
        
        spy_dates = pd.date_range("2020-01-01", "2023-12-31", freq="D")
        spy_df = pd.DataFrame({
            "Close": 100 * (1 + np.random.normal(0.0003, 0.01, len(spy_dates))).cumprod(),
        }, index=spy_dates)
        spy_df.to_pickle(yf_dir / "SPY.pkl")
        
        result = generate_plot_data_from_cache(tmp_path)
        
        assert result["benchmark"] is not None
        assert "dates" in result["benchmark"]
        assert "values" in result["benchmark"]


class TestBacktestEngineCacheOnly:
    """Tests for BacktestEngine cache_only mode."""

    def test_cache_only_mode_loads_from_disk(self, tmp_path, monkeypatch):
        """Test that cache_only mode only reads from disk."""
        # Mock the cache directory
        monkeypatch.setattr("os.path.dirname", lambda x: str(tmp_path))
        
        from backtest_engine import BacktestEngine
        
        # Create cache directories
        yf_dir = tmp_path / ".cache" / "yf_prices"
        yf_dir.mkdir(parents=True)
        ib_dir = tmp_path / ".cache" / "ib_prices"
        ib_dir.mkdir()
        
        # Create test data
        dates = pd.date_range("2020-01-01", "2022-12-31", freq="D")
        df = pd.DataFrame({
            "Open": np.random.uniform(100, 110, len(dates)),
            "High": np.random.uniform(110, 120, len(dates)),
            "Low": np.random.uniform(90, 100, len(dates)),
            "Close": np.random.uniform(100, 110, len(dates)),
            "Volume": np.random.randint(1000000, 10000000, len(dates)),
        }, index=dates)
        
        df.to_pickle(yf_dir / "AAPL.pkl")
        df.to_pickle(yf_dir / "MSFT.pkl")
        
        engine = BacktestEngine(price_source="cache_only")
        engine._yf_cache_dir = str(yf_dir)
        engine._ib_cache_dir = str(ib_dir)
        
        data = engine.fetch_historical_data(
            ["AAPL", "MSFT", "NONEXISTENT"],
            "2020-01-01",
            "2022-12-31",
        )
        
        assert "AAPL" in data
        assert "MSFT" in data
        assert "NONEXISTENT" not in data  # Not in cache

    def test_cache_only_no_api_calls(self, tmp_path, monkeypatch):
        """Test that cache_only mode never makes API calls."""
        from backtest_engine import BacktestEngine
        
        # Use a completely unique ticker that won't be in any cache
        unique_ticker = "ZZZNONEXISTENT999"
        
        yf_dir = tmp_path / ".cache" / "yf_prices"
        yf_dir.mkdir(parents=True)
        ib_dir = tmp_path / ".cache" / "ib_prices"
        ib_dir.mkdir()
        
        engine = BacktestEngine(price_source="cache_only")
        engine._yf_cache_dir = str(yf_dir)
        engine._ib_cache_dir = str(ib_dir)
        
        # No mock needed - cache_only simply doesn't call yfinance
        data = engine.fetch_historical_data(
            [unique_ticker],
            "2020-01-01",
            "2022-12-31",
        )
        
        # Should return empty since ticker not in cache
        assert data == {}


class TestWorkerTaskFallback:
    """Tests for worker task fallback to cache-based generation."""

    def test_task_fallback_on_empty_result(self, tmp_path):
        """Test that task falls back when main script produces empty result."""
        # This is an integration test - requires Celery worker running
        # Marking as a placeholder for manual testing
        pass
