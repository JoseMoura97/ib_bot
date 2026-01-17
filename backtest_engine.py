"""
Backtesting Engine
Simulates strategies over historical data with performance metrics and charts.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import warnings
import re
import os
import time
import random
import logging
warnings.filterwarnings('ignore')

# Try to import yfinance, make it optional
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    yf = None

try:
    # Optional Interactive Brokers price source
    from ib_insync import IB, Stock, util  # type: ignore
    IB_AVAILABLE = True
except Exception:
    IB_AVAILABLE = False
    IB = None  # type: ignore
    Stock = None  # type: ignore
    util = None  # type: ignore


# Global cache for historical data to avoid repeated downloads
_historical_data_cache = {}
_yf_ticker_cache: Dict[str, pd.DataFrame] = {}

class BacktestEngine:
    def __init__(self, initial_capital: float = 100000, price_source: str = "yfinance"):
        self.initial_capital = initial_capital
        self.results = None
        self.trades = []
        self.equity_curve = []
        self.price_source = (price_source or "yfinance").lower().strip()

        # IB connection is created lazily
        self._ib: Optional["IB"] = None
        self._ib_connected: bool = False
        self._ib_host = os.getenv("IB_HOST", "127.0.0.1")
        self._ib_port = int(os.getenv("IB_PORT", "4001"))
        self._ib_client_id = int(os.getenv("IB_CLIENT_ID", str(random.randint(10, 1000))))
        self._ib_use_rth = os.getenv("IB_USE_RTH", "1").strip() not in {"0", "false", "False"}
        self._ib_pace_sleep_s = float(os.getenv("IB_PACE_SLEEP_S", "0.25"))
        self._ib_disabled_until_ts: float = 0.0

        self._ib_cache_dir = os.path.join(os.path.dirname(__file__), ".cache", "ib_prices")
        os.makedirs(self._ib_cache_dir, exist_ok=True)
        self._ib_contract_cache: Dict[str, "Stock"] = {}

        self._yf_cache_dir = os.path.join(os.path.dirname(__file__), ".cache", "yf_prices")
        os.makedirs(self._yf_cache_dir, exist_ok=True)
        
    def _clean_tickers(self, tickers: List[str]) -> List[str]:
        """Clean ticker strings: remove $, convert to upper, handle special characters."""
        cleaned = []
        for t in tickers:
            if not isinstance(t, str):
                continue
            # Remove $ prefix and any whitespace
            t_clean = t.replace('$', '').strip().upper()
            # Remove any trailing dots/subclasses if present (e.g. BRK.A -> BRK-A for yfinance)
            t_clean = t_clean.replace('.', '-')
            # Only keep tickers that look valid (alphanumeric and dashes)
            if re.match(r'^[A-Z0-9\-]+$', t_clean):
                cleaned.append(t_clean)
        return list(set(cleaned))

    def _normalize_symbol_for_ib(self, symbol: str) -> str:
        """
        IB symbol normalization.
        - IB often uses space for class shares (e.g. BRK B, BF B).
        - Our pipeline frequently normalizes '.' -> '-' for yfinance.
        """
        s = str(symbol).strip().upper().replace("$", "")
        # BRK-B -> BRK B
        if re.match(r"^[A-Z]{1,5}-[A-Z]$", s):
            s = s.replace("-", " ")
        return s

    def _extract_series(self, df: pd.DataFrame, col_name: str, ticker: str = None) -> pd.Series:
        """Robustly extract a column from a yfinance DataFrame (handles MultiIndex)."""
        if df.empty:
            return pd.Series()
            
        # Case 1: MultiIndex (Ticker, Column) or (Column, Ticker)
        if isinstance(df.columns, pd.MultiIndex):
            # Try (Ticker, Column) - common with group_by='ticker'
            if ticker and ticker in df.columns.levels[0] and col_name in df.columns.levels[1]:
                return df[ticker][col_name]
            # Try (Column, Ticker) - common default
            if col_name in df.columns.levels[0]:
                if ticker and ticker in df.columns.levels[1]:
                    return df[col_name][ticker]
                else:
                    return df[col_name].iloc[:, 0] # Return first ticker if not specified
            # Flattened MultiIndex (uncommon but possible)
            col_list = [str(c) for c in df.columns]
            for i, c in enumerate(col_list):
                if col_name.lower() in c.lower() and (not ticker or ticker.lower() in c.lower()):
                    return df.iloc[:, i]
        
        # Case 2: Standard Index
        if col_name in df.columns:
            return df[col_name]
            
        # Case 3: Fuzzy match column
        for c in df.columns:
            if col_name.lower() in str(c).lower():
                return df[c]
                
        return pd.Series()

    def _ib_connect(self) -> bool:
        if not IB_AVAILABLE:
            return False
        # Cooldown after failures to avoid log spam + slow loops
        if self._ib_disabled_until_ts and time.time() < self._ib_disabled_until_ts:
            return False
        if self._ib is not None and self._ib_connected and getattr(self._ib, "isConnected", lambda: False)():
            return True

        try:
            # Reduce ib_insync noise (we handle fallback logic ourselves)
            logging.getLogger("ib_insync").setLevel(logging.CRITICAL)
            logging.getLogger("ib_insync.client").setLevel(logging.CRITICAL)
            logging.getLogger("ib_insync.wrapper").setLevel(logging.CRITICAL)

            self._ib = IB()
            # Use a random clientId unless explicitly pinned to avoid clashes
            client_id = self._ib_client_id if os.getenv("IB_CLIENT_ID") else random.randint(10, 1000)
            self._ib.connect(self._ib_host, self._ib_port, clientId=client_id, readonly=True, timeout=10)
            self._ib_connected = bool(self._ib.isConnected())
            return self._ib_connected
        except Exception:
            # Disable IB attempts for 60 seconds after a connection failure
            self._ib_disabled_until_ts = time.time() + 60.0
            self._ib_connected = False
            self._ib = None
            return False

    def _ib_disconnect(self):
        try:
            if self._ib is not None and getattr(self._ib, "isConnected", lambda: False)():
                self._ib.disconnect()
        except Exception:
            pass
        self._ib_connected = False
        self._ib = None

    def _ib_cache_path(self, ticker: str) -> str:
        safe = re.sub(r"[^A-Z0-9_\- ]", "_", str(ticker).upper())
        safe = safe.replace(" ", "_")
        return os.path.join(self._ib_cache_dir, f"{safe}.pkl")

    def _load_ib_cache(self, ticker: str) -> Optional[pd.DataFrame]:
        try:
            path = self._ib_cache_path(ticker)
            if os.path.exists(path):
                df = pd.read_pickle(path)
                if isinstance(df, pd.DataFrame) and not df.empty:
                    if not isinstance(df.index, pd.DatetimeIndex):
                        df.index = pd.to_datetime(df.index, errors="coerce")
                    df = df.sort_index()
                    return df
        except Exception:
            return None
        return None

    def _save_ib_cache(self, ticker: str, df: pd.DataFrame):
        try:
            path = self._ib_cache_path(ticker)
            df.sort_index().to_pickle(path)
        except Exception:
            pass

    def _yf_cache_path(self, ticker: str) -> str:
        safe = re.sub(r"[^A-Z0-9_\- ]", "_", str(ticker).upper())
        safe = safe.replace(" ", "_")
        return os.path.join(self._yf_cache_dir, f"{safe}.pkl")

    def _load_yf_cache(self, ticker: str) -> Optional[pd.DataFrame]:
        try:
            if ticker in _yf_ticker_cache and isinstance(_yf_ticker_cache[ticker], pd.DataFrame):
                df = _yf_ticker_cache[ticker]
                if not df.empty:
                    return df
            path = self._yf_cache_path(ticker)
            if os.path.exists(path):
                df = pd.read_pickle(path)
                if isinstance(df, pd.DataFrame) and not df.empty:
                    if not isinstance(df.index, pd.DatetimeIndex):
                        df.index = pd.to_datetime(df.index, errors="coerce")
                    df = df.sort_index()
                    _yf_ticker_cache[ticker] = df
                    return df
        except Exception:
            return None
        return None

    def _save_yf_cache(self, ticker: str, df: pd.DataFrame):
        try:
            path = self._yf_cache_path(ticker)
            df = df.sort_index()
            df.to_pickle(path)
            _yf_ticker_cache[ticker] = df
        except Exception:
            pass

    def _fetch_yf_ticker_history(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch daily OHLCV for a single ticker from yfinance, with disk+memory cache.
        Cache is stored per-ticker and merged across requests so segment-level slicing is fast.
        """
        if not YFINANCE_AVAILABLE:
            return pd.DataFrame()

        start = pd.to_datetime(start_date).to_pydatetime()
        end = pd.to_datetime(end_date).to_pydatetime()
        if end <= start:
            return pd.DataFrame()

        cached = self._load_yf_cache(ticker)
        if cached is not None and not cached.empty:
            cmin = cached.index.min().to_pydatetime()
            cmax = cached.index.max().to_pydatetime()
            if cmin <= start and cmax >= end - timedelta(days=1):
                return cached.loc[(cached.index >= start) & (cached.index <= end)].copy()

        # Download requested window (yfinance is inclusive-exclusive-ish; we tolerate overlap).
        # Add small retry/backoff for intermittent Yahoo rate limits.
        df = None
        for attempt in range(3):
            try:
                df = yf.download(ticker, start=start_date, end=end_date, progress=False, threads=False)
                break
            except Exception as e:
                msg = str(e)
                if "RateLimit" in msg or "Too Many Requests" in msg:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, errors="coerce")
        df = df.sort_index()

        merged = df
        if cached is not None and not cached.empty:
            merged = pd.concat([cached, df]).sort_index()
            merged = merged[~merged.index.duplicated(keep="last")]

        self._save_yf_cache(ticker, merged)
        return merged.loc[(merged.index >= start) & (merged.index <= end)].copy()

    def _bars_to_df(self, bars) -> pd.DataFrame:
        if bars is None:
            return pd.DataFrame()
        try:
            df = util.df(bars) if util is not None else pd.DataFrame(bars)
        except Exception:
            df = pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame()

        # ib_insync returns columns like: date, open, high, low, close, volume, average, barCount
        col_map = {
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
        df = df.rename(columns=col_map)
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"])
            df = df.set_index("Date")
        df = df.sort_index()

        keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        return df[keep].copy() if keep else df.copy()

    def _fetch_ib_ticker_history(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch daily OHLCV for a single ticker from IB, with simple disk cache.
        Returns a DataFrame indexed by Date with columns: Open, High, Low, Close, Volume.
        """
        start = pd.to_datetime(start_date).to_pydatetime()
        end = pd.to_datetime(end_date).to_pydatetime()
        if end <= start:
            return pd.DataFrame()

        cached = self._load_ib_cache(ticker)
        if cached is not None and not cached.empty:
            # If cache covers range, slice and return
            if cached.index.min().to_pydatetime() <= start and cached.index.max().to_pydatetime() >= end - timedelta(days=1):
                return cached.loc[(cached.index >= start) & (cached.index <= end)].copy()

        if not self._ib_connect() or self._ib is None:
            return pd.DataFrame()

        ib_symbol = self._normalize_symbol_for_ib(ticker)
        try:
            contract = self._ib_contract_cache.get(ib_symbol)
            if contract is None:
                contract = Stock(ib_symbol, "SMART", "USD")
                self._ib.qualifyContracts(contract)
                self._ib_contract_cache[ib_symbol] = contract
        except Exception:
            return pd.DataFrame()

        # Quick probe: if IB cannot provide even a short tail window, don't waste time.
        try:
            probe = self._ib.reqHistoricalData(
                contract,
                endDateTime=end,
                durationStr="30 D",
                barSizeSetting="1 day",
                whatToShow="TRADES",
                useRTH=self._ib_use_rth,
                formatDate=1,
                keepUpToDate=False,
            )
            probe_df = self._bars_to_df(probe)
            if probe_df.empty:
                return pd.DataFrame()
        except Exception:
            return pd.DataFrame()

        # Pull in chunks to respect pacing (work backwards from end).
        # Use larger duration strings when possible to reduce API calls.
        out_parts = []
        cur_end = end
        safety = 0
        while cur_end > start and safety < 200:
            safety += 1
            remaining_days = max(1, int((cur_end - start).days))
            # Use up to 10 years per request for daily bars to reduce call count.
            if remaining_days >= 365:
                years = int(min(10, max(1, (remaining_days + 364) // 365)))
                duration_str = f"{years} Y"
            else:
                duration_str = f"{remaining_days} D"
            try:
                bars = self._ib.reqHistoricalData(
                    contract,
                    endDateTime=cur_end,
                    durationStr=duration_str,
                    barSizeSetting="1 day",
                    whatToShow="TRADES",
                    useRTH=self._ib_use_rth,
                    formatDate=1,
                    keepUpToDate=False,
                )
            except Exception:
                break

            df_chunk = self._bars_to_df(bars)
            if df_chunk.empty:
                break

            out_parts.append(df_chunk)
            earliest = df_chunk.index.min().to_pydatetime()
            # Step back one day to avoid duplicates
            cur_end = earliest - timedelta(days=1)
            time.sleep(self._ib_pace_sleep_s)

        if not out_parts:
            return pd.DataFrame()

        df_all = pd.concat(out_parts).sort_index()
        # De-dup index if overlaps occurred
        df_all = df_all[~df_all.index.duplicated(keep="last")]

        # Merge with cache
        if cached is not None and not cached.empty:
            merged = pd.concat([cached, df_all]).sort_index()
            merged = merged[~merged.index.duplicated(keep="last")]
            cached = merged
        else:
            cached = df_all

        self._save_ib_cache(ticker, cached)
        return cached.loc[(cached.index >= start) & (cached.index <= end)].copy()

    def fetch_historical_data(self, tickers: List[str], start_date: str, end_date: str, progress_callback=None) -> Dict[str, pd.DataFrame]:
        """
        Fetch historical OHLCV data for a list of tickers.

        price_source:
          - 'yfinance': Yahoo via yfinance
          - 'ib': Interactive Brokers (reqHistoricalData)
          - 'auto': try IB first, fallback to yfinance
        """
        if not tickers:
            return {}
        
        # Clean tickers first
        tickers = self._clean_tickers(tickers)
        if not tickers:
            return {}

        src = self.price_source
        if src not in {"yfinance", "ib", "auto"}:
            src = "yfinance"

        ib_data: Dict[str, pd.DataFrame] = {}
        if src in {"ib", "auto"} and IB_AVAILABLE:
            # In auto mode, if IB isn't reachable right now, skip IB entirely.
            if self._ib_connect():
                for i, ticker in enumerate(tickers):
                    if progress_callback:
                        progress_callback(i / max(1, len(tickers)), f"IB historical: {ticker} ({i+1}/{len(tickers)})")
                    df = self._fetch_ib_ticker_history(ticker, start_date, end_date)
                    if df is not None and not df.empty and "Close" in df.columns and len(df) > 1:
                        ib_data[ticker] = df
                if progress_callback:
                    progress_callback(1.0, "IB data fetch complete.")

            if src == "ib":
                return ib_data

        # yfinance path
        if not YFINANCE_AVAILABLE:
            return ib_data if ib_data else {}

        data = {}
        # Fetch yfinance data with batching to reduce request count/rate limits.
        yf_targets = [t for t in tickers if t not in ib_data]
        if yf_targets:
            # Reduce yfinance logging noise (errors are still visible in stderr)
            logging.getLogger("yfinance").setLevel(logging.ERROR)

        if len(yf_targets) > 10:
            batch_size = 30
            batches = [yf_targets[i:i + batch_size] for i in range(0, len(yf_targets), batch_size)]
            for bi, batch in enumerate(batches):
                if progress_callback:
                    progress_callback(bi / max(1, len(batches)), f"Yahoo batch {bi+1}/{len(batches)} ({len(batch)} tickers)")
                try:
                    ticker_string = " ".join(batch)
                    batch_df = yf.download(ticker_string, start=start_date, end=end_date, progress=False, group_by="ticker", threads=False)
                except Exception:
                    batch_df = pd.DataFrame()

                if batch_df is None or batch_df.empty:
                    # Fallback to per-ticker if batch call failed
                    for t in batch:
                        df = self._fetch_yf_ticker_history(t, start_date, end_date)
                        if df is not None and not df.empty and "Close" in df.columns and len(df) > 1:
                            data[t] = df
                    continue

                for t in batch:
                    try:
                        if len(batch) == 1:
                            df_t = batch_df
                        elif isinstance(batch_df.columns, pd.MultiIndex) and t in batch_df.columns.get_level_values(0):
                            df_t = batch_df[t]
                        else:
                            continue
                        df_t = df_t.dropna(how="all")
                        if df_t is not None and not df_t.empty and len(df_t) > 1:
                            # Persist into per-ticker cache for future slicing
                            cached = self._load_yf_cache(t)
                            merged = df_t
                            if cached is not None and not cached.empty:
                                merged = pd.concat([cached, df_t]).sort_index()
                                merged = merged[~merged.index.duplicated(keep="last")]
                            self._save_yf_cache(t, merged)
                            data[t] = merged.loc[(merged.index >= pd.to_datetime(start_date)) & (merged.index <= pd.to_datetime(end_date))].copy()
                    except Exception:
                        continue
        else:
            # Per-ticker path (uses per-ticker disk cache)
            for i, ticker in enumerate(yf_targets):
                if progress_callback:
                    progress_callback(i / max(1, len(yf_targets)), f"Yahoo historical: {ticker} ({i+1}/{len(yf_targets)})")
                df = self._fetch_yf_ticker_history(ticker, start_date, end_date)
                if df is not None and not df.empty and "Close" in df.columns and len(df) > 1:
                    data[ticker] = df
        
        if progress_callback:
            progress_callback(1.0, "Data download complete.")
            
        # If we're in auto mode and IB returned some data, merge (IB wins).
        if src == "auto" and ib_data:
            data.update(ib_data)
        return data
    
    @staticmethod
    def is_available():
        """Check if backtesting is available (yfinance installed)."""
        return YFINANCE_AVAILABLE
    
    def run_equal_weight_backtest(
        self, 
        tickers: List[str], 
        start_date: str, 
        end_date: str,
        rebalance_frequency: str = 'monthly',
        progress_callback=None
    ) -> Dict:
        """Run an equal-weight portfolio backtest."""
        print(f"Fetching data for {len(tickers)} tickers...")
        data = self.fetch_historical_data(tickers, start_date, end_date, progress_callback)
        
        if not data:
            return {'error': 'No valid data could be retrieved for the given tickers.'}
        
        valid_tickers = list(data.keys())
        
        # Build price DataFrame using the robust extractor
        # Use first ticker to get the index dates
        sample_df = data[valid_tickers[0]]
        prices = pd.DataFrame(index=sample_df.index)
        
        for ticker in valid_tickers:
            close_series = self._extract_series(data[ticker], 'Close', ticker)
            if not close_series.empty:
                prices[ticker] = close_series
        
        prices = prices.ffill().dropna(how='all')
        if prices.empty:
            return {'error': 'Data alignment failed. No usable price data.'}

        # Align all dates to the intersection of available data
        prices = prices.dropna() # Only keep dates where ALL tickers have data
        if len(prices) < 2:
            return {'error': 'Insufficient overlapping data between these tickers.'}
            
        returns = prices.pct_change().dropna()
        
        # Simulate portfolio
        n_assets = len(prices.columns)
        weights = np.array([1.0 / n_assets] * n_assets)
        
        portfolio_values = [self.initial_capital]
        portfolio_returns = []
        current_value = self.initial_capital
        
        for i, date in enumerate(returns.index):
            daily_returns = returns.loc[date].values
            portfolio_return = np.dot(weights, daily_returns)
            portfolio_returns.append(portfolio_return)
            current_value = current_value * (1 + portfolio_return)
            portfolio_values.append(current_value)
        
        # Create equity curve DataFrame
        equity_dates = [returns.index[0] - timedelta(days=1)] + list(returns.index)
        self.equity_curve = pd.DataFrame({
            'date': equity_dates,
            'portfolio_value': portfolio_values
        }).set_index('date')
        
        # Calculate metrics
        total_return = (portfolio_values[-1] / self.initial_capital) - 1
        portfolio_returns = np.array(portfolio_returns)
        n_years = len(portfolio_returns) / 252
        cagr = (portfolio_values[-1] / self.initial_capital) ** (1 / n_years) - 1 if n_years > 0 else 0
        volatility = np.std(portfolio_returns) * np.sqrt(252)
        sharpe_ratio = (cagr - 0.02) / volatility if volatility > 0 else 0
        
        # Maximum drawdown
        equity = np.array(portfolio_values)
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak
        max_drawdown = np.min(drawdown)
        
        win_rate = np.sum(portfolio_returns > 0) / len(portfolio_returns) if len(portfolio_returns) > 0 else 0
        
        negative_returns = portfolio_returns[portfolio_returns < 0]
        downside_std = np.std(negative_returns) * np.sqrt(252) if len(negative_returns) > 0 else 0
        sortino_ratio = (cagr - 0.02) / downside_std if downside_std > 0 else 0
        
        self.results = {
            'tickers': list(prices.columns),
            'start_date': str(prices.index[0].date()),
            'end_date': str(prices.index[-1].date()),
            'initial_capital': self.initial_capital,
            'final_value': portfolio_values[-1],
            'total_return': total_return,
            'cagr': cagr,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'n_days': len(portfolio_returns),
            'equity_curve': self.equity_curve,
            'drawdown_series': pd.Series(drawdown, index=equity_dates),
            'returns_series': pd.Series(portfolio_returns, index=returns.index)
        }
        
        return self.results
    
    def run_weighted_backtest(
        self,
        strategy_tickers: Dict[str, List[str]],
        strategy_weights: Dict[str, float],
        start_date: str,
        end_date: str,
        rebalance_frequency: str = 'monthly',
        progress_callback=None
    ) -> Dict:
        """Run a weighted multi-strategy backtest."""
        all_tickers = []
        ticker_weights = {}
        
        for strat_name, tickers in strategy_tickers.items():
            strat_weight = strategy_weights.get(strat_name, 0) / 100.0
            if strat_weight <= 0 or not tickers:
                continue
            
            clean_strat_tickers = self._clean_tickers(tickers)
            if not clean_strat_tickers: continue

            per_ticker_weight = strat_weight / len(clean_strat_tickers)
            
            for ticker in clean_strat_tickers:
                if ticker not in ticker_weights:
                    ticker_weights[ticker] = 0
                    all_tickers.append(ticker)
                ticker_weights[ticker] += per_ticker_weight
        
        if not all_tickers:
            return {'error': 'No valid tickers to backtest.'}
        
        print(f"Fetching data for {len(all_tickers)} unique tickers...")
        data = self.fetch_historical_data(all_tickers, start_date, end_date, progress_callback)
        
        if not data:
            return {'error': 'No valid data available.'}
        
        valid_tickers = [t for t in all_tickers if t in data]
        
        # Build price matrix using extractor
        sample_df = next(iter(data.values()))
        prices = pd.DataFrame(index=sample_df.index)
        for ticker in valid_tickers:
            close_series = self._extract_series(data[ticker], 'Close', ticker)
            if not close_series.empty:
                prices[ticker] = close_series
        
        prices = prices.ffill().dropna()
        if prices.empty:
            return {'error': 'Data alignment failed.'}

        returns = prices.pct_change().dropna()
        
        # Recalculate weights for valid tickers only
        total_weight = sum(ticker_weights.get(t, 0) for t in prices.columns)
        weights = np.array([ticker_weights[t] / total_weight for t in prices.columns])
        
        # Simulate
        portfolio_values = [self.initial_capital]
        portfolio_returns = []
        current_value = self.initial_capital
        
        for date in returns.index:
            daily_returns = returns.loc[date].values
            portfolio_return = np.dot(weights, daily_returns)
            portfolio_returns.append(portfolio_return)
            current_value *= (1 + portfolio_return)
            portfolio_values.append(current_value)
        
        equity_dates = [returns.index[0] - timedelta(days=1)] + list(returns.index)
        self.equity_curve = pd.DataFrame({
            'date': equity_dates,
            'portfolio_value': portfolio_values
        }).set_index('date')
        
        # Metrics
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
        
        negative_returns = portfolio_returns[portfolio_returns < 0]
        downside_std = np.std(negative_returns) * np.sqrt(252) if len(negative_returns) > 0 else 0
        sortino_ratio = (cagr - 0.02) / downside_std if downside_std > 0 else 0
        
        self.results = {
            'tickers': list(prices.columns),
            'weights': dict(zip(prices.columns, weights)),
            'start_date': str(prices.index[0].date()),
            'end_date': str(prices.index[-1].date()),
            'initial_capital': self.initial_capital,
            'final_value': portfolio_values[-1],
            'total_return': total_return,
            'cagr': cagr,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'n_days': len(portfolio_returns),
            'equity_curve': self.equity_curve,
            'drawdown_series': pd.Series(drawdown, index=equity_dates),
            'returns_series': pd.Series(portfolio_returns, index=returns.index)
        }
        
        return self.results
    
    def compare_to_benchmark(self, benchmark: str = 'SPY') -> Dict:
        """Compare backtest results to a benchmark."""
        if self.results is None:
            return {'error': 'Run a backtest first'}
        
        start = self.results['start_date']
        end = self.results['end_date']
        
        bench_data = self.fetch_historical_data([benchmark], start, end)
        if benchmark not in bench_data:
            return {'error': f'Could not fetch {benchmark} data'}
        
        bench_df = bench_data[benchmark]
        bench_prices = self._extract_series(bench_df, 'Close', benchmark)
        
        if bench_prices.empty:
            return {'error': f'No Close price data for {benchmark}'}
            
        bench_returns = bench_prices.pct_change().dropna()
        
        bench_total = (bench_prices.iloc[-1] / bench_prices.iloc[0]) - 1
        n_years = len(bench_returns) / 252
        bench_cagr = (bench_prices.iloc[-1] / bench_prices.iloc[0]) ** (1 / n_years) - 1 if n_years > 0 else 0
        bench_vol = bench_returns.std() * np.sqrt(252)
        bench_sharpe = (bench_cagr - 0.02) / bench_vol if bench_vol > 0 else 0
        
        bench_values = bench_prices.values
        bench_peak = np.maximum.accumulate(bench_values)
        bench_dd = (bench_values - bench_peak) / bench_peak
        bench_max_dd = np.min(bench_dd)
        
        portfolio_returns = self.results['returns_series']
        common_dates = portfolio_returns.index.intersection(bench_returns.index)
        if len(common_dates) < 2:
            return {'error': 'No overlapping dates with benchmark'}
            
        port_ret = portfolio_returns.loc[common_dates].values
        bench_ret = bench_returns.loc[common_dates].values
        
        covariance = np.cov(port_ret, bench_ret)[0, 1]
        bench_variance = np.var(bench_ret)
        beta = covariance / bench_variance if bench_variance > 0 else 0
        alpha = self.results['cagr'] - (0.02 + beta * (bench_cagr - 0.02))
        
        tracking_error = np.std(port_ret - bench_ret) * np.sqrt(252)
        info_ratio = (self.results['cagr'] - bench_cagr) / tracking_error if tracking_error > 0 else 0
        
        return {
            'benchmark': benchmark,
            'benchmark_total_return': bench_total,
            'benchmark_cagr': bench_cagr,
            'benchmark_volatility': bench_vol,
            'benchmark_sharpe': bench_sharpe,
            'benchmark_max_drawdown': bench_max_dd,
            'alpha': alpha,
            'beta': beta,
            'information_ratio': info_ratio,
            'outperformance': self.results['total_return'] - bench_total,
            'benchmark_equity': bench_prices
        }
