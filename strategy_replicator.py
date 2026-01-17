"""
Strategy Replicator - Implements Quiver's strategy methodologies locally
Handles weighted portfolios, rebalancing, long-short, and strategy-specific logic
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

from quiver_strategy_rules import QuiverStrategyRules

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    yf = None


class StrategyReplicator:
    """Replicates Quiver's strategy methodologies with proper weighting and rebalancing."""
    
    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.results = None
        
    @staticmethod
    def get_strategy_config(strategy_name: str) -> Dict:
        """Get configuration for a specific strategy."""
        rules = QuiverStrategyRules.get_strategy_rules(strategy_name) or {}
        
        # Congressional Group Strategies
        if strategy_name == "Congress Buys":
            return {
                'type': 'congressional_weighted',
                'top_n': 10,
                'weight_by': 'purchase_size',
                'rebalance': 'weekly',
                'filter': 'purchase',
                'lookback_days': rules.get("lookback_days", 120),
            }
        
        if strategy_name == "Congress Long-Short":
            return {
                'type': 'long_short',
                'long_weight': 1.30,
                'short_weight': 0.30,
                # Congress-level long/short tends to be size-weighted in Quiver outputs.
                'weight_by': 'transaction_size',
                'rebalance': 'weekly',
                'lookback_days': rules.get("lookback_days", 120),
                # Use broader baskets to reduce concentration/drawdown.
                'top_longs': 20,
                'top_shorts': 20
            }
        
        if strategy_name == "U.S. House Long-Short":
            return {
                'type': 'long_short',
                'long_weight': 1.30,
                'short_weight': 0.30,
                'weight_by': 'count',
                'rebalance': 'weekly',
                'filter_chamber': 'house',
                'lookback_days': rules.get("lookback_days", 120),
                'top_longs': 10,
                'top_shorts': 10
            }
        
        if strategy_name == "Congress Sells":
            return {
                'type': 'congressional_weighted',
                'top_n': 10,
                'weight_by': 'sale_size',
                'rebalance': 'weekly',
                'filter': 'sale',
                'lookback_days': rules.get("lookback_days", 120),
            }
        
        # Congressional Committee Strategies
        if "Committee" in strategy_name:
            return {
                'type': 'congressional_weighted',
                'weight_by': 'purchase_size',
                'rebalance': 'weekly',
                'filter': 'purchase',
                'lookback_days': rules.get("lookback_days", 120),
                'top_n': 10
            }
        
        # Congressional Individual Strategies
        if strategy_name in ["Nancy Pelosi", "Dan Meuser", "Josh Gottheimer", "Donald Beyer", "Sheldon Whitehouse"]:
            return {
                'type': 'portfolio_mirror',
                'rebalance': 'on_trade',  # Rebalance when new trades filed
                'use_reported_amounts': True,
                'lookback_days': 365
            }
        
        # Lobbying Strategies
        if strategy_name == "Lobbying Spending Growth":
            return {
                'type': 'equal_weighted',
                'top_n': 10,
                'rebalance': 'monthly',
                'sort_by': 'lobbying_growth',
                'lookback_days': 90
            }
        
        if strategy_name == "Top Lobbying Spenders":
            return {
                'type': 'equal_weighted',
                'top_n': 10,
                'rebalance': 'monthly',
                'sort_by': 'lobbying_total',
                'lookback_days': 90
            }
        
        # Government Contracts
        if strategy_name == "Top Gov Contract Recipients":
            return {
                'type': 'value_weighted',
                'top_n': 20,
                'weight_by': 'contract_value',
                'use_ema': True,  # Exponential moving average
                'rebalance': 'monthly',
                'lookback_days': 90
            }
        
        # Sector Weighted
        if strategy_name == "Sector Weighted DC Insider":
            return {
                'type': 'sector_weighted',
                'benchmark': 'SPY',  # Match S&P 500 sector allocation
                'rebalance': 'monthly',
                'data_sources': ['congress', 'lobbying', 'contracts'],
                'lookback_days': 90
            }
        
        # Insider Purchases
        if strategy_name == "Insider Purchases":
            return {
                'type': 'equal_weighted',
                'top_n': 10,
                'rebalance': 'weekly',
                'sort_by': 'insider_score',
                'lookback_days': 90
            }
        
        # Analyst Buys
        if strategy_name == "Analyst Buys":
            return {
                'type': 'equal_weighted',
                'top_n': 10,
                'rebalance': 'monthly',
                'sort_by': 'analyst_score',
                'lookback_days': 90
            }
        
        # Hedge Fund Managers (13F)
        if strategy_name in ["Michael Burry", "Bill Ackman", "Howard Marks"]:
            return {
                'type': 'portfolio_mirror',
                'rebalance': 'quarterly',
                'use_13f_weights': True,
                'lookback_days': 120
            }
        
        # Default: equal weighted monthly
        return {
            'type': 'equal_weighted',
            'rebalance': 'monthly'
        }
    
    def apply_strategy_weights(self, 
                              raw_data: pd.DataFrame, 
                              strategy_name: str,
                              config: Dict) -> Dict[str, float]:
        """
        Apply strategy-specific weighting logic to raw data.
        
        Args:
            raw_data: DataFrame with columns like Ticker, Amount, TransactionDate, etc.
            strategy_name: Name of the strategy
            config: Strategy configuration dict
            
        Returns:
            Dictionary mapping ticker to weight (weights sum to 1.0)
        """
        
        # If upstream provides explicit weights (e.g. strategies/holdings time-series),
        # respect them regardless of strategy type.
        if raw_data is not None and not raw_data.empty and 'Ticker' in raw_data.columns and 'Weight' in raw_data.columns:
            dfw = raw_data[['Ticker', 'Weight']].copy()
            dfw['Weight'] = pd.to_numeric(dfw['Weight'], errors='coerce')
            dfw = dfw.dropna(subset=['Weight'])
            if not dfw.empty:
                w = dfw.groupby('Ticker')['Weight'].sum()
                total = float(w.sum())
                if total > 0:
                    return (w / total).to_dict()

        strategy_type = config.get('type', 'equal_weighted')
        
        if strategy_type == 'equal_weighted':
            return self._equal_weight(raw_data, config)
        
        elif strategy_type == 'congressional_weighted':
            return self._congressional_weighted(raw_data, config)
        
        elif strategy_type == 'value_weighted':
            return self._value_weighted(raw_data, config)
        
        elif strategy_type == 'portfolio_mirror':
            return self._portfolio_mirror(raw_data, config)
        
        elif strategy_type == 'long_short':
            return self._long_short_weights(raw_data, config)
        
        elif strategy_type == 'sector_weighted':
            return self._sector_weighted(raw_data, config)
        
        else:
            # Fallback to equal weight
            return self._equal_weight(raw_data, config)

    def apply_strategy_weights_at_date(
        self,
        raw_data: pd.DataFrame,
        strategy_name: str,
        as_of_date: datetime,
        lookback_days: Optional[int] = None,
    ) -> Dict[str, float]:
        """
        Apply strategy-specific weighting using only information available up to `as_of_date`
        (and optionally limited to a rolling window of `lookback_days`).

        This prevents lookahead bias and matches Quiver-style rolling-window construction.
        """
        if raw_data is None or raw_data.empty:
            return {}

        if not isinstance(as_of_date, datetime):
            as_of_date = pd.to_datetime(as_of_date).to_pydatetime()

        # Strategy defaults (used unless caller overrides)
        config = self.get_strategy_config(strategy_name)
        if lookback_days is None:
            lookback_days = config.get("lookback_days")
        if lookback_days is None:
            # Sensible defaults by strategy family
            if "Congress" in strategy_name or "House" in strategy_name or "Senate" in strategy_name or "Committee" in strategy_name:
                lookback_days = 90
            elif "Lobbying" in strategy_name or "Contract" in strategy_name:
                lookback_days = 90
            else:
                lookback_days = 365

        cutoff_date = as_of_date - timedelta(days=int(lookback_days))

        df = raw_data.copy()

        # Find the best available date column.
        date_col = None
        for col in ["TransactionDate", "ReportDate", "Date", "LastUpdate"]:
            if col in df.columns:
                date_col = col
                break

        if date_col:
            if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
                df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
            df = df[(df[date_col] >= cutoff_date) & (df[date_col] <= as_of_date)].copy()

        if df.empty:
            return {}

        return self.apply_strategy_weights(df, strategy_name, config)
    
    def _equal_weight(self, data: pd.DataFrame, config: Dict) -> Dict[str, float]:
        """Equal weight across all tickers."""
        if data.empty:
            return {}
        
        tickers = data['Ticker'].unique().tolist()
        top_n = config.get('top_n', len(tickers))
        
        if top_n < len(tickers):
            # If we need to select top N, use sort criteria
            sort_by = config.get('sort_by', None)
            if sort_by and sort_by in data.columns:
                data_sorted = data.sort_values(sort_by, ascending=False)
                tickers = data_sorted['Ticker'].unique()[:top_n].tolist()
            else:
                tickers = tickers[:top_n]
        
        weight = 1.0 / len(tickers)
        return {ticker: weight for ticker in tickers}
    
    def _congressional_weighted(self, data: pd.DataFrame, config: Dict) -> Dict[str, float]:
        """
        Weight by transaction size for congressional trades.
        Used for: Congress Buys, Committee strategies
        """
        if data.empty or 'Ticker' not in data.columns:
            return {}
        
        weight_by = config.get('weight_by', 'purchase_size')
        
        # Aggregate by ticker
        if 'Amount' in data.columns:
            # Ensure Amount is numeric
            data_copy = data.copy()
            data_copy['Amount'] = pd.to_numeric(data_copy['Amount'], errors='coerce')
            data_copy = data_copy.dropna(subset=['Amount'])
            if not data_copy.empty:
                ticker_weights = data_copy.groupby('Ticker')['Amount'].sum()
            else:
                # Fallback to counting
                ticker_weights = data.groupby('Ticker').size()
        elif 'Trade_Size_USD' in data.columns:
            # Some endpoints use Trade_Size_USD
            data_copy = data.copy()
            data_copy['Trade_Size_USD'] = pd.to_numeric(data_copy['Trade_Size_USD'], errors='coerce')
            data_copy = data_copy.dropna(subset=['Trade_Size_USD'])
            if not data_copy.empty:
                ticker_weights = data_copy.groupby('Ticker')['Trade_Size_USD'].sum()
            else:
                ticker_weights = data.groupby('Ticker').size()
        elif 'Range' in data.columns:
            # Parse range strings like "$1,001 - $15,000"
            data_copy = data.copy()
            data_copy['amount_estimate'] = data_copy['Range'].apply(self._parse_amount_range)
            ticker_weights = data_copy.groupby('Ticker')['amount_estimate'].sum()
        else:
            # Fallback: count number of transactions (weighted by frequency)
            ticker_weights = data.groupby('Ticker').size()
        
        # Convert to numeric if needed
        try:
            ticker_weights = pd.to_numeric(ticker_weights, errors='coerce')
            ticker_weights = ticker_weights.dropna()
        except:
            pass
        
        # Remove zero or negative weights
        ticker_weights = ticker_weights[ticker_weights > 0]
        
        if ticker_weights.empty:
            return {}
        
        # Select top N if specified
        top_n = config.get('top_n', len(ticker_weights))
        try:
            ticker_weights = ticker_weights.nlargest(top_n)
        except:
            # If nlargest fails, just take the first N
            ticker_weights = ticker_weights.head(top_n)
        
        # Normalize to sum to 1.0
        total = ticker_weights.sum()
        if total > 0 and not pd.isna(total):
            weights = (ticker_weights / total).to_dict()
        else:
            # Fallback to equal weight
            weights = {t: 1.0/len(ticker_weights) for t in ticker_weights.index}
        
        return weights
    
    def _value_weighted(self, data: pd.DataFrame, config: Dict) -> Dict[str, float]:
        """
        Weight by value (e.g., contract value, lobbying spending).
        Used for: Top Gov Contract Recipients, Lobbying strategies
        """
        if data.empty or 'Ticker' not in data.columns:
            return {}
        
        weight_column = config.get('weight_by', 'Value')
        
        # Check for value column and ensure numeric
        data_copy = data.copy()
        
        if 'Value' in data_copy.columns:
            data_copy['Value'] = pd.to_numeric(data_copy['Value'], errors='coerce')
            data_copy = data_copy.dropna(subset=['Value'])
            if not data_copy.empty:
                ticker_values = data_copy.groupby('Ticker')['Value'].sum()
            else:
                return self._equal_weight(data, config)
        elif 'Amount' in data_copy.columns:
            data_copy['Amount'] = pd.to_numeric(data_copy['Amount'], errors='coerce')
            data_copy = data_copy.dropna(subset=['Amount'])
            if not data_copy.empty:
                ticker_values = data_copy.groupby('Ticker')['Amount'].sum()
            else:
                return self._equal_weight(data, config)
        else:
            # Fallback to equal weight
            return self._equal_weight(data, config)
        
        # Convert to numeric if needed
        try:
            ticker_values = pd.to_numeric(ticker_values, errors='coerce')
            ticker_values = ticker_values.dropna()
        except:
            pass
        
        # Apply EMA if specified
        if config.get('use_ema', False):
            # Simple decay: recent values weighted more
            if 'Date' in data_copy.columns or 'LastUpdate' in data_copy.columns:
                date_col = 'Date' if 'Date' in data_copy.columns else 'LastUpdate'
                data_copy = data_copy.sort_values(date_col)
                # Apply exponential decay (half-life of 90 days)
                max_date = data_copy[date_col].max()
                data_copy['days_ago'] = (max_date - data_copy[date_col]).dt.days
                data_copy['weight_factor'] = np.exp(-data_copy['days_ago'] / 90)
                value_col = 'Value' if 'Value' in data_copy.columns else 'Amount'
                data_copy['weighted_value'] = pd.to_numeric(data_copy[value_col], errors='coerce') * data_copy['weight_factor']
                ticker_values = data_copy.groupby('Ticker')['weighted_value'].sum()
        
        # Remove invalid values
        ticker_values = ticker_values[ticker_values > 0]
        
        if ticker_values.empty:
            return self._equal_weight(data, config)
        
        # Select top N
        top_n = config.get('top_n', len(ticker_values))
        try:
            ticker_values = ticker_values.nlargest(top_n)
        except:
            # If nlargest fails, just take first N
            ticker_values = ticker_values.head(top_n)
        
        # Normalize
        total = ticker_values.sum()
        if total > 0 and not pd.isna(total):
            weights = (ticker_values / total).to_dict()
        else:
            weights = {t: 1.0/len(ticker_values) for t in ticker_values.index}
        
        return weights
    
    def _portfolio_mirror(self, data: pd.DataFrame, config: Dict) -> Dict[str, float]:
        """
        Mirror a portfolio (politician or hedge fund).
        Uses reported position sizes.
        """
        if data.empty or 'Ticker' not in data.columns:
            return {}
        
        # For 13F filings, use reported values
        if config.get('use_13f_weights', False) and 'Value' in data.columns:
            ticker_values = data.groupby('Ticker')['Value'].sum()
            total = ticker_values.sum()
            if total > 0:
                return (ticker_values / total).to_dict()
        
        # For congressional trades, estimate position sizes
        if 'Amount' in data.columns:
            ticker_amounts = data.groupby('Ticker')['Amount'].sum()
            total = ticker_amounts.sum()
            if total > 0:
                return (ticker_amounts / total).to_dict()
        
        # If we have Range information
        if 'Range' in data.columns:
            data['amount_estimate'] = data['Range'].apply(self._parse_amount_range)
            ticker_amounts = data.groupby('Ticker')['amount_estimate'].sum()
            total = ticker_amounts.sum()
            if total > 0:
                return (ticker_amounts / total).to_dict()
        
        # Fallback: equal weight
        tickers = data['Ticker'].unique()
        return {t: 1.0/len(tickers) for t in tickers}
    
    def _long_short_weights(self, data: pd.DataFrame, config: Dict) -> Dict[str, float]:
        """
        Create long-short portfolio (130/30 strategy).
        Returns weights that can be negative (shorts).
        """
        if data.empty or 'Ticker' not in data.columns:
            return {}
        
        long_weight = config.get('long_weight', 1.30)
        short_weight = config.get('short_weight', 0.30)
        top_longs = int(config.get('top_longs', 10))
        top_shorts = int(config.get('top_shorts', 10))
        
        # Separate buys and sells
        if 'Transaction' in data.columns:
            buys = data[data['Transaction'].str.lower().str.contains('purchase|buy', na=False)].copy()
            sells = data[data['Transaction'].str.lower().str.contains('sale|sell', na=False)].copy()
        else:
            # If no transaction column, assume all are buys
            buys = data.copy()
            sells = pd.DataFrame()
        
        weights = {}
        
        weight_by = str(config.get("weight_by", "transaction_size")).lower()

        # Long positions (buys) - weighted by transaction size or trade frequency
        if not buys.empty:
            if weight_by in {"transaction_size", "amount", "usd"} and 'Amount' in buys.columns:
                buys['Amount'] = pd.to_numeric(buys['Amount'], errors='coerce')
                buys = buys.dropna(subset=['Amount'])
                if not buys.empty:
                    buy_weights = buys.groupby('Ticker')['Amount'].sum()
                else:
                    buy_weights = buys['Ticker'].value_counts()
            elif weight_by in {"transaction_size", "amount", "usd"} and 'Trade_Size_USD' in buys.columns:
                buys['Trade_Size_USD'] = pd.to_numeric(buys['Trade_Size_USD'], errors='coerce')
                buys = buys.dropna(subset=['Trade_Size_USD'])
                if not buys.empty:
                    buy_weights = buys.groupby('Ticker')['Trade_Size_USD'].sum()
                else:
                    buy_weights = buys['Ticker'].value_counts()
            else:
                buy_weights = buys['Ticker'].value_counts()
            
            # Ensure numeric
            try:
                buy_weights = pd.to_numeric(buy_weights, errors='coerce')
                buy_weights = buy_weights.dropna()
                buy_weights = buy_weights[buy_weights > 0]
            except:
                pass
            
            if not buy_weights.empty:
                # Select top buys
                try:
                    top_buys = buy_weights.nlargest(top_longs)
                except:
                    top_buys = buy_weights.head(top_longs)
                
                total_buys = top_buys.sum()
                
                if total_buys > 0 and not pd.isna(total_buys):
                    for ticker, amount in top_buys.items():
                        weights[ticker] = (amount / total_buys) * long_weight
        
        # Short positions (sells) - negative weights, weighted by transaction size or trade frequency
        if not sells.empty:
            if weight_by in {"transaction_size", "amount", "usd"} and 'Amount' in sells.columns:
                sells['Amount'] = pd.to_numeric(sells['Amount'], errors='coerce')
                sells = sells.dropna(subset=['Amount'])
                if not sells.empty:
                    sell_weights = sells.groupby('Ticker')['Amount'].sum()
                else:
                    sell_weights = sells['Ticker'].value_counts()
            elif weight_by in {"transaction_size", "amount", "usd"} and 'Trade_Size_USD' in sells.columns:
                sells['Trade_Size_USD'] = pd.to_numeric(sells['Trade_Size_USD'], errors='coerce')
                sells = sells.dropna(subset=['Trade_Size_USD'])
                if not sells.empty:
                    sell_weights = sells.groupby('Ticker')['Trade_Size_USD'].sum()
                else:
                    sell_weights = sells['Ticker'].value_counts()
            else:
                sell_weights = sells['Ticker'].value_counts()
            
            # Ensure numeric
            try:
                sell_weights = pd.to_numeric(sell_weights, errors='coerce')
                sell_weights = sell_weights.dropna()
                sell_weights = sell_weights[sell_weights > 0]
            except:
                pass
            
            if not sell_weights.empty:
                # Select top sells
                try:
                    top_sells = sell_weights.nlargest(top_shorts)
                except:
                    top_sells = sell_weights.head(top_shorts)
                
                total_sells = top_sells.sum()
                
                if total_sells > 0 and not pd.isna(total_sells):
                    for ticker, amount in top_sells.items():
                        # Negative weight for shorts (we profit when price goes down)
                        weights[ticker] = weights.get(ticker, 0) - (amount / total_sells) * short_weight
        
        return weights
    
    def _sector_weighted(self, data: pd.DataFrame, config: Dict) -> Dict[str, float]:
        """
        Sector-weighted to match benchmark (e.g., S&P 500).
        This is complex and would require sector data - simplified version here.
        """
        # This would require fetching sector allocations from benchmark
        # For now, use equal weight as approximation
        return self._equal_weight(data, config)
    
    @staticmethod
    def _parse_amount_range(range_str: str) -> float:
        """Parse congressional trade amount range and return midpoint."""
        if pd.isna(range_str):
            return 0
        
        try:
            # Remove $ and commas
            range_str = str(range_str).replace('$', '').replace(',', '')
            
            # Split on '-' or 'to'
            if '-' in range_str:
                parts = range_str.split('-')
            elif 'to' in range_str.lower():
                parts = range_str.lower().split('to')
            else:
                # Single value
                return float(range_str.strip())
            
            # Get min and max
            min_val = float(parts[0].strip())
            max_val = float(parts[1].strip())
            
            # Return midpoint
            return (min_val + max_val) / 2
        except:
            # Default estimate for unknown ranges
            return 15000  # Typical small trade
    
    def run_strategy_backtest(self,
                             strategy_name: str,
                             raw_signal_data: pd.DataFrame,
                             start_date: str,
                             end_date: str,
                             progress_callback=None) -> Dict:
        """
        Run a backtest for a specific strategy with proper weighting.
        
        Args:
            strategy_name: Name of the strategy to backtest
            raw_signal_data: Raw data from Quiver API with metadata
            start_date: Start date for backtest
            end_date: End date for backtest
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dictionary with backtest results
        """
        
        # Get strategy configuration
        config = self.get_strategy_config(strategy_name)
        
        # Apply strategy-specific weighting
        weights = self.apply_strategy_weights(raw_signal_data, strategy_name, config)
        
        if not weights:
            return {'error': 'No valid weights could be calculated from signal data'}
        
        # Get tickers and their weights
        tickers = list(weights.keys())
        ticker_weights = np.array([weights[t] for t in tickers])
        
        # Fetch historical data
        from backtest_engine import BacktestEngine
        engine = BacktestEngine(initial_capital=self.initial_capital)
        data = engine.fetch_historical_data(tickers, start_date, end_date, progress_callback)
        
        if not data:
            return {'error': 'No historical data available'}
        
        # Filter to valid tickers
        valid_tickers = [t for t in tickers if t in data]
        if not valid_tickers:
            return {'error': 'No valid tickers with historical data'}
        
        # Adjust weights for valid tickers only
        valid_weights = np.array([weights[t] for t in valid_tickers])
        
        # Handle long-short: separate positive and negative weights
        has_shorts = np.any(valid_weights < 0)
        
        if has_shorts:
            return self._run_long_short_backtest(valid_tickers, valid_weights, data, start_date, end_date)
        else:
            # Normalize positive weights to sum to 1.0
            total_weight = valid_weights.sum()
            if total_weight > 0:
                valid_weights = valid_weights / total_weight
            
            return self._run_long_only_backtest(valid_tickers, valid_weights, data, start_date, end_date)
    
    def _run_long_only_backtest(self, tickers: List[str], weights: np.ndarray, 
                               data: Dict, start_date: str, end_date: str) -> Dict:
        """Run backtest for long-only portfolio with custom weights."""
        
        from backtest_engine import BacktestEngine
        engine = BacktestEngine(initial_capital=self.initial_capital)
        
        # Build price DataFrame
        sample_df = data[tickers[0]]
        prices = pd.DataFrame(index=sample_df.index)
        
        for ticker in tickers:
            close_series = engine._extract_series(data[ticker], 'Close', ticker)
            if not close_series.empty:
                prices[ticker] = close_series
        
        prices = prices.ffill().dropna()
        if prices.empty or len(prices) < 2:
            return {'error': 'Insufficient price data'}
        
        returns = prices.pct_change().dropna()
        
        # Ensure weights align with price columns
        ticker_to_weight = {t: w for t, w in zip(tickers, weights)}
        ordered_weights = np.array([ticker_to_weight.get(t, 0) for t in prices.columns])
        
        # Simulate portfolio
        portfolio_values = [self.initial_capital]
        portfolio_returns = []
        current_value = self.initial_capital
        
        for date in returns.index:
            daily_returns = returns.loc[date].values
            portfolio_return = np.dot(ordered_weights, daily_returns)
            portfolio_returns.append(portfolio_return)
            current_value *= (1 + portfolio_return)
            portfolio_values.append(current_value)
        
        # Calculate metrics
        portfolio_returns = np.array(portfolio_returns)
        n_years = len(portfolio_returns) / 252
        
        total_return = (portfolio_values[-1] / self.initial_capital) - 1
        cagr = (portfolio_values[-1] / self.initial_capital) ** (1 / n_years) - 1 if n_years > 0 else 0
        volatility = np.std(portfolio_returns) * np.sqrt(252)
        sharpe_ratio = (cagr - 0.02) / volatility if volatility > 0 else 0
        
        equity = np.array(portfolio_values)
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak
        max_drawdown = np.min(drawdown)
        
        win_rate = np.sum(portfolio_returns > 0) / len(portfolio_returns) if len(portfolio_returns) > 0 else 0
        
        return {
            'tickers': list(prices.columns),
            'weights': {t: w for t, w in zip(prices.columns, ordered_weights)},
            'start_date': str(prices.index[0].date()),
            'end_date': str(prices.index[-1].date()),
            'initial_capital': self.initial_capital,
            'final_value': portfolio_values[-1],
            'total_return': total_return,
            'cagr': cagr,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'n_days': len(portfolio_returns),
            'strategy_type': 'weighted_long_only'
        }
    
    def _run_long_short_backtest(self, tickers: List[str], weights: np.ndarray,
                                data: Dict, start_date: str, end_date: str) -> Dict:
        """Run backtest for long-short portfolio (130/30 strategy)."""
        
        from backtest_engine import BacktestEngine
        engine = BacktestEngine(initial_capital=self.initial_capital)
        
        # Build price DataFrame
        sample_df = data[tickers[0]]
        prices = pd.DataFrame(index=sample_df.index)
        
        for ticker in tickers:
            close_series = engine._extract_series(data[ticker], 'Close', ticker)
            if not close_series.empty:
                prices[ticker] = close_series
        
        prices = prices.ffill().dropna()
        if prices.empty or len(prices) < 2:
            return {'error': 'Insufficient price data'}
        
        returns = prices.pct_change().dropna()
        
        # Align weights with price columns
        ticker_to_weight = {t: w for t, w in zip(tickers, weights)}
        ordered_weights = np.array([ticker_to_weight.get(t, 0) for t in prices.columns])
        
        # Separate long and short weights
        long_mask = ordered_weights > 0
        short_mask = ordered_weights < 0
        
        # Simulate portfolio with long-short
        portfolio_values = [self.initial_capital]
        portfolio_returns = []
        current_value = self.initial_capital
        
        for date in returns.index:
            daily_returns = returns.loc[date].values
            # Long-short return: positive weights gain from up moves, negative weights gain from down moves
            portfolio_return = np.dot(ordered_weights, daily_returns)
            portfolio_returns.append(portfolio_return)
            current_value *= (1 + portfolio_return)
            portfolio_values.append(current_value)
        
        # Calculate metrics
        portfolio_returns = np.array(portfolio_returns)
        n_years = len(portfolio_returns) / 252
        
        total_return = (portfolio_values[-1] / self.initial_capital) - 1
        cagr = (portfolio_values[-1] / self.initial_capital) ** (1 / n_years) - 1 if n_years > 0 else 0
        volatility = np.std(portfolio_returns) * np.sqrt(252)
        sharpe_ratio = (cagr - 0.02) / volatility if volatility > 0 else 0
        
        equity = np.array(portfolio_values)
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak
        max_drawdown = np.min(drawdown)
        
        win_rate = np.sum(portfolio_returns > 0) / len(portfolio_returns) if len(portfolio_returns) > 0 else 0
        
        long_exposure = ordered_weights[long_mask].sum()
        short_exposure = abs(ordered_weights[short_mask].sum())
        net_exposure = long_exposure - short_exposure
        gross_exposure = long_exposure + short_exposure
        
        return {
            'tickers': list(prices.columns),
            'weights': {t: w for t, w in zip(prices.columns, ordered_weights)},
            'start_date': str(prices.index[0].date()),
            'end_date': str(prices.index[-1].date()),
            'initial_capital': self.initial_capital,
            'final_value': portfolio_values[-1],
            'total_return': total_return,
            'cagr': cagr,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'n_days': len(portfolio_returns),
            'strategy_type': 'long_short',
            'long_exposure': long_exposure,
            'short_exposure': short_exposure,
            'net_exposure': net_exposure,
            'gross_exposure': gross_exposure
        }
