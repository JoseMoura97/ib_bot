import quiverquant
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os
import logging
import requests

try:
    from sec_edgar import SECEdgarClient
    SEC_EDGAR_AVAILABLE = True
except Exception:
    SECEdgarClient = None  # type: ignore
    SEC_EDGAR_AVAILABLE = False

class QuiverStrategyEngine:
    # Mapping from our strategy names to Quiver API strategy names
    STRATEGY_NAME_MAP = {
        "Transportation and Infra. Committee (House)": "House Transportation and Infrastructure Committee",
        "U.S. House Long-Short": "House_LS",
        "Top Gov Contract Recipients": "TopGovernmentContractReceivers",
        "Congress Buys": "Congress Buys",
        "Lobbying Spending Growth": "Lobby QoQ Growth",
        "Top Lobbying Spenders": "Lobby Top10",
        "Sector Weighted DC Insider": "DCInsiderTrades",
        # Additional available strategies from API
        "Congress Sells": "Congress Sells",
        "Congress Long-Short": "Congress_LS",
        "Insider Purchases": "Insider Purchases",
        "Insider Purchases 500M+": "Insider Purchases Min 500M Market Cap",
        "Analyst Long": "Analyst Long",
        "WSB Top 10": "WSB_Top_10",
        "Senate Homeland Security": "Senate Homeland Security Committee",
        "House Energy Committee": "House Energy and Commerce Committee",
        "House Natural Resources": "House Natural Resources Committee",
        "WSB Top 10": "WSB_Top_10",
        "Analyst Long": "Analyst Long",
    }
    
    # Cache for strategies/holdings data
    _holdings_cache = None
    _holdings_cache_time = None
    _bulk_congress_cache = None
    _bulk_congress_cache_time = None
    _lobbying_cache = None
    _lobbying_cache_time = None
    _contracts_cache = None
    _contracts_cache_time = None
    
    def __init__(self, api_key):
        self.api_key = api_key
        self.quiver = quiverquant.quiver(api_key)
        # Optional SEC EDGAR fallback for 13F strategies
        self.sec_edgar = SECEdgarClient() if SEC_EDGAR_AVAILABLE else None
        self.strategies_meta = {
            # Core Strategies
            "Congress Buys": {
                "type": "congress",
                "filter": lambda df: df[df['Transaction'].str.lower().str.contains('purchase|buy', na=False)],
                "lookback_days": 30,
                "category": "core"
            },
            "Dan Meuser": {
                "type": "congress_bulk",  # Use bulk endpoint for politician lookup
                "name_pattern": "Meuser",  # Search pattern (matches "Daniel Meuser")
                # No filter - include all trades (purchases and sales) to track portfolio activity
                "lookback_days": 365,  # Extended lookback for bulk data
                "category": "core"
            },
            "Sector Weighted DC Insider": {
                "type": "insider",
                "filter": lambda df: df[df['Transaction'].str.lower().isin(['buy', 'purchase'])],
                "lookback_days": 30,
                "category": "core"
            },
            "Michael Burry": {
                "type": "sec13F",
                "args": ["Scion Asset Management"],
                "category": "core",
                "top_n": 20,
            },
            "Lobbying Spending Growth": {
                "type": "lobbying",
                "lookback_days": 90,
                "limit": 10,
                "category": "core"
            },
            
            # Experimental Strategies (primarily fetched via official API)
            "Transportation and Infra. Committee (House)": {
                "type": "official_api",
                "category": "experimental"
            },
            "U.S. House Long-Short": {
                "type": "official_api",
                "category": "experimental"
            },
            "Top Gov Contract Recipients": {
                "type": "official_api",
                "category": "experimental"
            },
            "Donald Beyer": {
                "type": "congress_bulk",
                "name_pattern": "Beyer",  # Matches "Donald Sternoff Beyer Jr."
                # Extended lookback - last trade was 2022
                "lookback_days": 1825,  # ~5 years
                "category": "experimental"
            },
            "Josh Gottheimer": {
                "type": "congress_bulk",
                "name_pattern": "Gottheimer",
                "lookback_days": 365,
                "category": "experimental"
            },
            "Top Lobbying Spenders": {
                "type": "lobbying",
                "lookback_days": 90,
                "limit": 10,
                "category": "experimental"
            },
            "Nancy Pelosi": {
                "type": "congress_bulk",
                "name_pattern": "Pelosi",
                # Include purchases from extended period to get meaningful portfolio
                "filter": lambda df: df[df['Transaction'].str.lower().str.contains('purchase|buy', na=False)],
                "lookback_days": 730,  # 2 years for more data
                "category": "experimental"
            },
            "Sheldon Whitehouse": {
                "type": "congress_bulk",
                "name_pattern": "Whitehouse",
                "lookback_days": 365,
                "category": "experimental"
            },
            "Howard Marks": {
                "type": "sec13F",
                "args": ["Oaktree Capital Management"],
                "category": "experimental"
            },
            "Bill Ackman": {
                "type": "sec13F",
                "args": ["Pershing Square Capital Management"],
                "category": "experimental"
            },
            "Wall Street Conviction": {
                "type": "official_api",
                "category": "experimental"
            },
            "WSB Top 10": {
                "type": "official_api",
                "category": "experimental"
            },
            "Analyst Long": {
                "type": "official_api",
                "category": "experimental"
            },
            "House Natural Resources": {
                "type": "official_api",
                "category": "experimental"
            },
            "Energy and Commerce Committee (House)": {
                "type": "official_api",
                "category": "experimental"
            },
            "Homeland Security Committee (Senate)": {
                "type": "official_api",
                "category": "experimental"
            }
        }

    def get_signals(self, strategy_name):
        # 1. Try the direct strategies endpoint first
        signals = self._fetch_official_strategy(strategy_name)
        if signals:
            logging.info(f"Successfully fetched official strategy signals for {strategy_name}")
            return self._clean_ticker_list(signals)

        # 2. Fallback to processing raw data
        if strategy_name not in self.strategies_meta:
            return []
        
        meta = self.strategies_meta[strategy_name]
        strat_type = meta['type']
        
        try:
            logging.info(f"Falling back to raw data for {strategy_name} ({strat_type})")
            df = None
            
            # Handle congress_bulk type separately (uses bulk endpoint with full history)
            if strat_type == "congress_bulk":
                return self._process_congress_bulk(strategy_name, meta)
            
            # Wrap library calls to handle internal errors
            try:
                if strat_type == "congress":
                    df = self.quiver.congress_trading()
                elif strat_type == "insider":
                    df = self.quiver.insiders()
                elif strat_type == "sec13F":
                    df = self.quiver.sec13F(*meta['args'])
                elif strat_type == "lobbying":
                    df = self.quiver.lobbying()
            except Exception as lib_e:
                logging.warning(f"Library call failed for {strategy_name}: {lib_e}")
                df = None

            if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                # Try direct requests if the library fails
                df = self._fetch_raw_via_api(strat_type, meta.get('args', []))

            # SEC EDGAR fallback specifically for 13F strategies (end-to-end: runtime + backtests)
            if (df is None or (isinstance(df, pd.DataFrame) and df.empty)) and strat_type == "sec13F" and self.sec_edgar:
                try:
                    fund_name = None
                    args = meta.get("args") or []
                    if isinstance(args, list) and args:
                        fund_name = args[0]
                    if fund_name:
                        holdings = self.sec_edgar.get_latest_holdings(str(fund_name))
                        if holdings is not None and isinstance(holdings, pd.DataFrame) and not holdings.empty:
                            top_n = int(meta.get("top_n") or 20)
                            if "Value" in holdings.columns:
                                holdings = holdings.nlargest(top_n, "Value")
                            tickers = holdings["Ticker"].dropna().tolist() if "Ticker" in holdings.columns else []
                            return self._clean_ticker_list(tickers)
                except Exception as e:
                    logging.warning(f"SEC EDGAR fallback failed for {strategy_name}: {e}")

            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                return self._process_raw_df(df, meta)
        except Exception as e:
            logging.error(f"Error processing raw signals for {strategy_name}: {e}")
            
        return []
    
    def _get_raw_data_with_metadata(self, strategy_name):
        """
        Get raw data with all metadata (amounts, dates, etc.) for strategy replication.
        Returns DataFrame with all columns intact, not just tickers.
        """
        # 1. Check if it's an official API strategy - try to get underlying data
        if strategy_name not in self.strategies_meta:
            # Try official API as fallback
            official_signals = self._fetch_official_strategy(strategy_name)
            if official_signals:
                return pd.DataFrame({'Ticker': official_signals})
            return None
        
        meta = self.strategies_meta[strategy_name]
        strat_type = meta['type']
        
        # 2. For official_api type, try to fetch underlying data
        if strat_type == "official_api":
            # Try to get underlying data based on strategy name
            df = self._fetch_underlying_data_for_official_strategy(strategy_name)
            if df is not None and not df.empty:
                return df
            # Fallback to ticker list
            official_signals = self._fetch_official_strategy(strategy_name)
            if official_signals:
                return pd.DataFrame({'Ticker': official_signals})
            return None
        
        try:
            df = None
            
            # Handle congress_bulk type
            if strat_type == "congress_bulk":
                bulk_data = self._get_bulk_congress_data()
                if bulk_data is not None and not bulk_data.empty:
                    name_pattern = meta.get('name_pattern', '')
                    if name_pattern:
                        df = bulk_data[bulk_data['Representative'].str.contains(name_pattern, case=False, na=False)].copy()
                    else:
                        df = bulk_data.copy()
                    
                    # Apply date filter
                    lookback_days = meta.get('lookback_days', 365)
                    cutoff_date = datetime.now() - timedelta(days=lookback_days)
                    if 'TransactionDate' in df.columns:
                        df = df[df['TransactionDate'] >= cutoff_date].copy()
                    
                    # Apply transaction filter if specified
                    filter_func = meta.get('filter')
                    if filter_func and callable(filter_func):
                        df = filter_func(df)
                    
                    # Parse amount ranges to get numeric values
                    if 'Range' in df.columns:
                        df['Amount'] = df['Range'].apply(self._parse_amount_range)
                    
                    return df
            
            # Handle congress type
            if strat_type == "congress":
                bulk_data = self._get_bulk_congress_data()
                if bulk_data is not None and not bulk_data.empty:
                    df = bulk_data.copy()
                    lookback_days = meta.get('lookback_days', 30)
                    cutoff_date = datetime.now() - timedelta(days=lookback_days)
                    if 'TransactionDate' in df.columns:
                        df = df[df['TransactionDate'] >= cutoff_date].copy()
                    
                    filter_func = meta.get('filter')
                    if filter_func and callable(filter_func):
                        df = filter_func(df)
                    
                    # Parse amount ranges
                    if 'Range' in df.columns:
                        df['Amount'] = df['Range'].apply(self._parse_amount_range)
                    
                    return df
            
            # Handle lobbying type
            if strat_type == "lobbying":
                df = self._fetch_lobbying_data_with_amounts()
                if df is not None and not df.empty:
                    lookback_days = meta.get('lookback_days', 90)
                    cutoff_date = datetime.now() - timedelta(days=lookback_days)
                    if 'Date' in df.columns:
                        if not pd.api.types.is_datetime64_any_dtype(df['Date']):
                            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
                        df = df[df['Date'] >= cutoff_date].copy()
                    return df
            
            # Try library calls for other types
            try:
                if strat_type == "insider":
                    df = self.quiver.insiders()
                elif strat_type == "sec13F":
                    df = self.quiver.sec13F(*meta['args'])
            except Exception as lib_e:
                logging.warning(f"Library call failed for {strategy_name}: {lib_e}")
                df = None
            
            if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                # Try direct API
                df = self._fetch_raw_via_api(strat_type, meta.get('args', []))

            # SEC EDGAR fallback for 13F raw holdings (metadata + value)
            if (df is None or (isinstance(df, pd.DataFrame) and df.empty)) and strat_type == "sec13F" and self.sec_edgar:
                try:
                    args = meta.get("args") or []
                    fund_name = args[0] if isinstance(args, list) and args else None
                    if fund_name:
                        df = self.sec_edgar.get_latest_holdings(str(fund_name))
                except Exception as e:
                    logging.warning(f"SEC EDGAR raw fallback failed for {strategy_name}: {e}")
            
            if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                # Apply filters but keep all columns
                filter_func = meta.get('filter')
                if filter_func and callable(filter_func):
                    df = filter_func(df)
                
                # Apply lookback
                lookback_days = meta.get('lookback_days')
                if lookback_days:
                    cutoff_date = datetime.now() - timedelta(days=lookback_days)
                    # Find date column
                    date_col = None
                    for col in ['TransactionDate', 'ReportDate', 'Date', 'LastUpdate']:
                        if col in df.columns:
                            date_col = col
                            break
                    
                    if date_col:
                        if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
                            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                        df = df[df[date_col] >= cutoff_date].copy()
                
                return df
        except Exception as e:
            logging.error(f"Error getting raw data for {strategy_name}: {e}")
        
        return None

    def _get_raw_data_with_metadata_at_date(
        self,
        strategy_name: str,
        as_of_date: datetime,
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        """
        Get raw strategy data as it would have been known at `as_of_date`.

        This is the critical primitive for Quiver-style replication:
        - No lookahead: filters out rows after `as_of_date`
        - Rolling window: includes only the last `lookback_days` prior to `as_of_date`

        Returns a DataFrame that still includes metadata columns (Amount/Value/etc.)
        so weighting can be computed correctly.
        """
        if not isinstance(as_of_date, datetime):
            as_of_date = pd.to_datetime(as_of_date).to_pydatetime()

        cutoff_date = as_of_date - timedelta(days=int(lookback_days))

        # Prefer full-history sources where possible (bulk congress, live feeds).
        if strategy_name not in self.strategies_meta:
            # For strategies not in our meta, try Quiver holdings time-series (supports official strategies).
            holdings_data = self._get_holdings_data()
            if holdings_data is not None:
                api_strategy_name = self.STRATEGY_NAME_MAP.get(strategy_name, strategy_name)
                snap = self._extract_holdings_weights_at_date(holdings_data, api_strategy_name, as_of_date)
                if snap is not None and not snap.empty:
                    return snap

            # Best-effort: fall back to official strategy tickers (cannot time-travel)
            official_signals = self._fetch_official_strategy(strategy_name)
            if official_signals:
                return pd.DataFrame({"Ticker": official_signals})
            return pd.DataFrame()

        meta = self.strategies_meta[strategy_name]
        strat_type = meta.get("type")

        # SEC EDGAR fallback for 13F time-travel (used by replication/backtests)
        if strat_type == "sec13F" and self.sec_edgar:
            try:
                args = meta.get("args") or []
                fund_name = args[0] if isinstance(args, list) and args else None
                if fund_name:
                    df = self.sec_edgar.get_holdings_as_of_date(str(fund_name), as_of_date=as_of_date)
                    if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
                        return df
            except Exception as e:
                logging.warning(f"SEC EDGAR time-travel fallback failed for {strategy_name}: {e}")

        # For composite/official strategies where we don't have true underlying history,
        # use Quiver holdings time-series (tickers + weights) if available.
        if (
            strat_type in {"official_api", "insider", "lobbying"}
            or "Contract" in strategy_name
        ) and strategy_name not in {"Congress Buys", "Congress Sells", "Congress Long-Short", "U.S. House Long-Short", "Transportation and Infra. Committee (House)"}:
            holdings_data = self._get_holdings_data()
            if holdings_data is not None:
                api_strategy_name = self.STRATEGY_NAME_MAP.get(strategy_name, strategy_name)
                snap = self._extract_holdings_weights_at_date(holdings_data, api_strategy_name, as_of_date)
                if snap is not None and not snap.empty:
                    return snap

        # Congress / committees / chamber-long-short: use bulk congress history
        if strat_type in {"congress", "congress_bulk", "official_api"} or (
            "Congress" in strategy_name or "House" in strategy_name or "Senate" in strategy_name or "Committee" in strategy_name
        ):
            bulk = self._get_bulk_congress_data()
            if bulk is None or bulk.empty:
                return pd.DataFrame()

            df = bulk.copy()

            # Chamber filters (House/Senate strategies)
            # Bulk endpoint commonly uses "Representatives" for House.
            if "House" in strategy_name and "Chamber" in df.columns:
                df = df[df["Chamber"].isin(["House", "Representatives", "House of Representatives"])].copy()
            elif "Senate" in strategy_name and "Chamber" in df.columns:
                df = df[df["Chamber"].isin(["Senate"])].copy()

            # Politician filter (for congress_bulk)
            name_pattern = meta.get("name_pattern")
            if name_pattern and "Representative" in df.columns:
                df = df[df["Representative"].str.contains(name_pattern, case=False, na=False)].copy()

            # Strategy-specific transaction filter
            filter_func = meta.get("filter")
            if filter_func and callable(filter_func):
                try:
                    df = filter_func(df)
                except Exception as e:
                    logging.warning(f"Date-aware filter failed for {strategy_name}: {e}")

            # Ensure TransactionDate is datetime and apply rolling window
            if "TransactionDate" in df.columns:
                if not pd.api.types.is_datetime64_any_dtype(df["TransactionDate"]):
                    df["TransactionDate"] = pd.to_datetime(df["TransactionDate"], errors="coerce")
                df = df[(df["TransactionDate"] >= cutoff_date) & (df["TransactionDate"] <= as_of_date)].copy()

            # Parse transaction amount (for weighting)
            if "Range" in df.columns and "Amount" not in df.columns:
                df["Amount"] = df["Range"].apply(self._parse_amount_range)

            return df

        # Lobbying: live feed with Date + Amount
        if strat_type == "lobbying":
            df = self._fetch_lobbying_data_with_amounts()
            if df is None or df.empty:
                return pd.DataFrame()
            if "Date" in df.columns:
                if not pd.api.types.is_datetime64_any_dtype(df["Date"]):
                    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                df = df[(df["Date"] >= cutoff_date) & (df["Date"] <= as_of_date)].copy()

            # Strategy-specific transforms for Quiver replication
            if strategy_name == "Top Lobbying Spenders":
                df2 = df.copy()
                if "Amount" in df2.columns:
                    df2["Amount"] = pd.to_numeric(df2["Amount"], errors="coerce")
                df2 = df2.dropna(subset=["Ticker", "Amount"])
                if df2.empty:
                    return pd.DataFrame()
                totals = df2.groupby("Ticker")["Amount"].sum().reset_index()
                totals = totals.rename(columns={"Amount": "lobbying_total"})
                totals["Date"] = as_of_date
                return totals

            if strategy_name == "Lobbying Spending Growth":
                df2 = df.copy()
                if "Amount" in df2.columns:
                    df2["Amount"] = pd.to_numeric(df2["Amount"], errors="coerce")
                df2 = df2.dropna(subset=["Ticker", "Amount", "Date"])
                if df2.empty:
                    return pd.DataFrame()
                df2["Quarter"] = df2["Date"].dt.to_period("Q")
                qsum = df2.groupby(["Ticker", "Quarter"])["Amount"].sum().reset_index()
                cur_q = pd.Timestamp(as_of_date).to_period("Q")
                prev_q = cur_q - 1
                cur = qsum[qsum["Quarter"] == cur_q].set_index("Ticker")["Amount"]
                prev = qsum[qsum["Quarter"] == prev_q].set_index("Ticker")["Amount"]
                merged = pd.DataFrame({"cur": cur, "prev": prev}).fillna(0.0)
                merged["lobbying_growth"] = np.where(
                    merged["prev"] > 0, (merged["cur"] - merged["prev"]) / merged["prev"], 0.0
                )
                out = merged.reset_index()[["Ticker", "lobbying_growth"]]
                out["Date"] = as_of_date
                return out

            return df

        # Contracts: live feed may include historical rows; filter by Date if present.
        if "Contract" in strategy_name:
            df = self._fetch_underlying_data_for_official_strategy(strategy_name)
            if df is None or df.empty:
                return pd.DataFrame()
            date_col = None
            for col in ["Date", "ActionDate", "TransactionDate", "LastUpdate"]:
                if col in df.columns:
                    date_col = col
                    break
            if date_col:
                if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
                    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                df = df[(df[date_col] >= cutoff_date) & (df[date_col] <= as_of_date)].copy()
            return df

        # Fallback: use existing method (note: may not be time-accurate for all sources)
        df = self._get_raw_data_with_metadata(strategy_name)
        if df is None or df.empty:
            return pd.DataFrame()

        # Apply date filtering if we can find a date column.
        date_col = self._find_col(df, ["TransactionDate", "ReportDate", "Date", "LastUpdate"])
        if date_col:
            if not pd.api.types.is_datetime64_any_dtype(df[date_col]):
                df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
            df = df[(df[date_col] >= cutoff_date) & (df[date_col] <= as_of_date)].copy()
        return df

    def get_signals_at_date(
        self,
        strategy_name: str,
        as_of_date: datetime,
        lookback_days: int = 90,
        top_n: int | None = None,
    ) -> List[str]:
        """
        Get strategy tickers as they would have existed at `as_of_date`.
        Intended for time-series backtests with rolling windows.
        """
        df = self._get_raw_data_with_metadata_at_date(
            strategy_name=strategy_name,
            as_of_date=as_of_date,
            lookback_days=lookback_days,
        )
        if df is None or df.empty:
            return []

        ticker_col = self._find_col(df, ["Ticker", "Symbol"])
        if not ticker_col:
            return []

        # If caller requests top_n, use Amount/Value if available; else take unique order.
        if top_n is None:
            tickers = df[ticker_col].dropna().astype(str).unique().tolist()
            return self._clean_ticker_list(tickers)

        sort_col = None
        for col in ["Amount", "Trade_Size_USD", "Value"]:
            if col in df.columns:
                sort_col = col
                break

        if sort_col:
            df2 = df.copy()
            df2[sort_col] = pd.to_numeric(df2[sort_col], errors="coerce")
            df2 = df2.dropna(subset=[sort_col])
            if not df2.empty:
                agg = df2.groupby(ticker_col)[sort_col].sum()
                try:
                    tickers = agg.nlargest(int(top_n)).index.tolist()
                except Exception:
                    tickers = agg.sort_values(ascending=False).head(int(top_n)).index.tolist()
                return self._clean_ticker_list([str(t) for t in tickers])

        tickers = df[ticker_col].dropna().astype(str).unique().tolist()[: int(top_n)]
        return self._clean_ticker_list(tickers)
    
    @staticmethod
    def _parse_amount_range(range_str):
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
    
    def _fetch_lobbying_data_with_amounts(self):
        """Fetch lobbying data with spending amounts."""
        # Cache (valid for 6 hours) - prevents refetch on every rebalance
        if self._lobbying_cache is not None and self._lobbying_cache_time is not None:
            cache_age = (datetime.now() - self._lobbying_cache_time).total_seconds()
            if cache_age < 21600:  # 6 hours
                return self._lobbying_cache

        url = "https://api.quiverquant.com/beta/live/lobbying"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data:
                    df = pd.DataFrame(data)
                    # Ensure we have ticker and amount columns
                    if 'Ticker' in df.columns and 'Amount' in df.columns:
                        # Normalize/parse date if present
                        if 'Date' in df.columns and not pd.api.types.is_datetime64_any_dtype(df['Date']):
                            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
                        QuiverStrategyEngine._lobbying_cache = df
                        QuiverStrategyEngine._lobbying_cache_time = datetime.now()
                        return df
            else:
                logging.warning(f"Lobbying API returned status {response.status_code}")
        except Exception as e:
            logging.error(f"Error fetching lobbying data: {e}")
        
        return None
    
    def _fetch_underlying_data_for_official_strategy(self, strategy_name):
        """
        Fetch underlying transaction data for official API strategies.
        This allows proper weighting even when using pre-computed strategies.
        """
        # Map official strategies to their underlying data sources
        if "Congress" in strategy_name or "House" in strategy_name or "Committee" in strategy_name:
            # Use bulk congress data
            bulk_data = self._get_bulk_congress_data()
            if bulk_data is not None and not bulk_data.empty:
                # Apply strategy-specific filters
                if "Buys" in strategy_name or "Committee" in strategy_name:
                    df = bulk_data[bulk_data['Transaction'].str.lower().str.contains('purchase', na=False)].copy()
                elif "Sells" in strategy_name:
                    df = bulk_data[bulk_data['Transaction'].str.lower().str.contains('sale', na=False)].copy()
                else:
                    df = bulk_data.copy()
                
                # Filter by chamber if needed
                if "House" in strategy_name and "Chamber" in df.columns:
                    df = df[df['Chamber'] == 'House'].copy()
                elif "Senate" in strategy_name and "Chamber" in df.columns:
                    df = df[df['Chamber'] == 'Senate'].copy()
                
                # Parse amounts
                if 'Range' in df.columns:
                    df['Amount'] = df['Range'].apply(self._parse_amount_range)
                
                # Apply date filter (last 30 days for most strategies)
                lookback_days = 30
                cutoff_date = datetime.now() - timedelta(days=lookback_days)
                if 'TransactionDate' in df.columns:
                    df = df[df['TransactionDate'] >= cutoff_date].copy()
                
                return df
        
        elif "Lobbying" in strategy_name:
            return self._fetch_lobbying_data_with_amounts()
        
        elif "Contract" in strategy_name:
            # Fetch contract data
            url = "https://api.quiverquant.com/beta/live/govcontracts"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json"
            }
            try:
                # Cache (valid for 6 hours) - prevents refetch on every rebalance
                if self._contracts_cache is not None and self._contracts_cache_time is not None:
                    cache_age = (datetime.now() - self._contracts_cache_time).total_seconds()
                    if cache_age < 21600:
                        return self._contracts_cache

                response = requests.get(url, headers=headers, timeout=60)
                if response.status_code == 200:
                    data = response.json()
                    if data:
                        df = pd.DataFrame(data)
                        # Try to normalize dates if present
                        for col in ["Date", "ActionDate", "TransactionDate", "LastUpdate"]:
                            if col in df.columns and not pd.api.types.is_datetime64_any_dtype(df[col]):
                                df[col] = pd.to_datetime(df[col], errors="coerce")
                        QuiverStrategyEngine._contracts_cache = df
                        QuiverStrategyEngine._contracts_cache_time = datetime.now()
                        return df
            except Exception as e:
                logging.error(f"Error fetching contract data: {e}")
        
        return None
    
    def _get_bulk_congress_data(self):
        """Fetch and cache bulk congress trading data (full history)."""
        # Check cache (valid for 10 minutes)
        if self._bulk_congress_cache is not None and self._bulk_congress_cache_time is not None:
            cache_age = (datetime.now() - self._bulk_congress_cache_time).total_seconds()
            if cache_age < 600:  # 10 minutes
                return self._bulk_congress_cache
        
        url = "https://api.quiverquant.com/beta/bulk/congresstrading"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=60)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    df = pd.DataFrame(data)
                    # Normalize column names to match expected format
                    column_map = {
                        'Name': 'Representative',
                        'Traded': 'TransactionDate',
                    }
                    df = df.rename(columns=column_map)
                    
                    # Convert date column
                    if 'TransactionDate' in df.columns:
                        df['TransactionDate'] = pd.to_datetime(df['TransactionDate'], errors='coerce')
                    
                    QuiverStrategyEngine._bulk_congress_cache = df
                    QuiverStrategyEngine._bulk_congress_cache_time = datetime.now()
                    logging.info(f"Loaded bulk congress data: {len(df)} records")
                    return df
        except Exception as e:
            logging.warning(f"Failed to fetch bulk congress data: {e}")
        
        return None
    
    def _process_congress_bulk(self, strategy_name, meta):
        """Process congress data from bulk endpoint for politician-specific strategies."""
        df = self._get_bulk_congress_data()
        
        if df is None or df.empty:
            return []
        
        # Make a copy
        df = df.copy()
        
        # Filter by politician name pattern
        name_pattern = meta.get('name_pattern', '')
        if name_pattern:
            df = df[df['Representative'].str.contains(name_pattern, case=False, na=False)]
        
        if df.empty:
            return []
        
        # Apply transaction filter if provided
        if 'filter' in meta:
            try:
                df = meta['filter'](df)
            except Exception as e:
                logging.warning(f"Filter failed for {strategy_name}: {e}")
        
        # Apply date filter
        lookback_days = meta.get('lookback_days', 365)
        if 'TransactionDate' in df.columns:
            cutoff = datetime.now() - timedelta(days=lookback_days)
            df = df[df['TransactionDate'] > cutoff]
            df = df.sort_values('TransactionDate', ascending=False)
        
        if df.empty:
            return []
        
        # Extract tickers
        ticker_col = 'Ticker' if 'Ticker' in df.columns else None
        if not ticker_col:
            return []
        
        tickers = df[ticker_col].unique().tolist()
        return self._clean_ticker_list(tickers)

    def _process_raw_df(self, df, meta):
        try:
            # Ensure df is a DataFrame
            if not isinstance(df, pd.DataFrame) or df.empty:
                return []
                
            # Create a copy to avoid SettingWithCopyWarning
            df = df.copy()
            
            # Dynamic column finding
            date_col = self._find_col(df, ['TransactionDate', 'ReportDate', 'Date', 'LastUpdate'])
            ticker_col = self._find_col(df, ['Ticker', 'Symbol'])
            
            if not ticker_col:
                return []

            # Filter if needed
            if 'filter' in meta:
                df = meta['filter'](df)
                # Re-copy after filtering
                df = df.copy()

            if date_col:
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                df = df.dropna(subset=[date_col])
                lookback = datetime.now() - timedelta(days=meta.get('lookback_days', 30))
                df = df[df[date_col] > lookback]
                df = df.sort_values(by=date_col, ascending=False)

            tickers = df[ticker_col].unique().tolist()
            return self._clean_ticker_list(tickers)
        except Exception as e:
            logging.error(f"Error in _process_raw_df: {e}")
            return []

    def _clean_ticker_list(self, tickers):
        """Clean tickers and limit to 100 to prevent backtest overload."""
        cleaned = []
        for t in tickers:
            if not isinstance(t, str): continue
            # Remove $ and handle common garbage
            t_clean = t.replace('$', '').strip().upper()
            if t_clean and len(t_clean) < 10:
                cleaned.append(t_clean)
        return list(set(cleaned))[:100]

    def _fetch_official_strategy(self, strategy_name):
        """Fetches pre-calculated strategy holdings from Quiver's API."""
        # Map our strategy name to API strategy name
        api_strategy_name = self.STRATEGY_NAME_MAP.get(strategy_name, strategy_name)
        
        # Try to get from cached holdings data first
        holdings_data = self._get_holdings_data()
        if holdings_data is not None:
            tickers = self._extract_tickers_from_holdings(holdings_data, api_strategy_name)
            if tickers:
                return tickers
        
        # Fallback: try the old per-strategy endpoint format
        formatted_names = [
            api_strategy_name,
            strategy_name,
            strategy_name.replace(" ", "%20"),
            strategy_name.replace(" ", "")
        ]
        
        for name in formatted_names:
            for path in ['live', 'beta']:
                url = f"https://api.quiverquant.com/{path}/strategies/holdings/{name}"
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json"
                }
                try:
                    response = requests.get(url, headers=headers, timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        if isinstance(data, list) and len(data) > 0:
                            tickers = [item.get('Ticker', item.get('Symbol')) for item in data if item.get('Ticker') or item.get('Symbol')]
                            return list(set(filter(None, tickers)))
                except:
                    continue
        return []
    
    def _get_holdings_data(self):
        """Fetch and cache the strategies/holdings endpoint data."""
        # Check cache (valid for 5 minutes)
        if self._holdings_cache is not None and self._holdings_cache_time is not None:
            cache_age = (datetime.now() - self._holdings_cache_time).total_seconds()
            if cache_age < 300:  # 5 minutes
                return self._holdings_cache
        
        url = "https://api.quiverquant.com/beta/strategies/holdings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    QuiverStrategyEngine._holdings_cache = data
                    QuiverStrategyEngine._holdings_cache_time = datetime.now()
                    return data
        except Exception as e:
            logging.warning(f"Failed to fetch holdings data: {e}")
        
        return None
    
    def _extract_tickers_from_holdings(self, holdings_data, strategy_name):
        """Extract tickers from the holdings data for a specific strategy."""
        try:
            # Convert to DataFrame for easier filtering
            df = pd.DataFrame(holdings_data)
            
            # Filter by strategy name
            strat_data = df[df['Strategy'] == strategy_name]
            
            if strat_data.empty:
                return []
            
            # Get the latest holdings (most recent date)
            strat_data = strat_data.sort_values('Date', ascending=False)
            latest = strat_data.iloc[0]
            
            # Parse holdings string: "AAPL:0.1,MSFT:0.1,..."
            holdings_str = latest.get('Holdings', '')
            if not holdings_str:
                return []
            
            tickers = []
            for item in holdings_str.split(','):
                if ':' in item:
                    ticker = item.split(':')[0].strip()
                    if ticker:
                        tickers.append(ticker)
            
            return tickers
            
        except Exception as e:
            logging.warning(f"Error extracting tickers for {strategy_name}: {e}")
            return []

    def _extract_holdings_weights_at_date(self, holdings_data, strategy_name: str, as_of_date: datetime) -> pd.DataFrame:
        """
        Extract tickers + weights from holdings time-series for `strategy_name`,
        using the latest holdings row with Date <= as_of_date.

        Returns DataFrame with columns: Ticker, Weight, Date.
        """
        try:
            df = pd.DataFrame(holdings_data)
            if df.empty:
                return pd.DataFrame()

            needed = {"Strategy", "Date", "Holdings"}
            if not needed.issubset(set(df.columns)):
                return pd.DataFrame()

            df = df[df["Strategy"] == strategy_name].copy()
            if df.empty:
                return pd.DataFrame()

            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"])
            df = df[df["Date"] <= as_of_date].copy()
            if df.empty:
                return pd.DataFrame()

            df = df.sort_values("Date", ascending=False)
            latest = df.iloc[0]
            holdings_str = latest.get("Holdings", "")
            if not holdings_str:
                return pd.DataFrame()

            rows = []
            for item in str(holdings_str).split(","):
                if ":" not in item:
                    continue
                t, w = item.split(":", 1)
                t = str(t).strip()
                try:
                    wv = float(str(w).strip())
                except Exception:
                    continue
                if t:
                    rows.append({"Ticker": t, "Weight": wv, "Date": latest["Date"]})

            return pd.DataFrame(rows) if rows else pd.DataFrame()
        except Exception as e:
            logging.warning(f"Error extracting holdings weights for {strategy_name}: {e}")
            return pd.DataFrame()

    def _fetch_raw_via_api(self, strat_type, args):
        """Fallback to direct API requests for raw data if the library fails."""
        endpoints = {
            "congress": "live/congress",
            "insider": "live/insiders",
            "sec13F": "live/sec13f",
            "lobbying": "live/lobbying"
        }
        
        if strat_type not in endpoints:
            return None
            
        url = f"https://api.quiverquant.com/beta/{endpoints[strat_type]}"
        if strat_type == "sec13F" and args:
            url += f"?ticker={args[0].replace(' ', '%20')}"
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if not data:
                    return None
                if isinstance(data, dict):
                    data = [data]
                try:
                    if isinstance(data, dict):
                        return pd.DataFrame([data])
                    return pd.DataFrame(data)
                except Exception as e:
                    logging.error(f"DataFrame creation failed for {strat_type}: {e}")
                    return None
            elif response.status_code == 403:
                logging.error(f"Subscription Required: Access denied for {strat_type}.")
            else:
                logging.error(f"Quiver API error {response.status_code} for {strat_type}")
        except Exception as e:
            logging.error(f"Direct API fallback failed for {strat_type}: {e}")
            
        return None

    def _find_col(self, df, possible_names):
        cols = {c.lower(): c for c in df.columns}
        for name in possible_names:
            if name.lower() in cols:
                return cols[name.lower()]
        return None
