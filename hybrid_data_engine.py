"""
Hybrid Data Engine - Intelligently switches between Quiver and SEC EDGAR
Provides seamless fallback from premium Quiver API to free SEC EDGAR
"""

import pandas as pd
import logging
from typing import Optional, List, Dict
from datetime import datetime, timedelta

try:
    from sec_edgar import SECEdgarClient
    SEC_EDGAR_AVAILABLE = True
except ImportError:
    SEC_EDGAR_AVAILABLE = False
    logging.warning("SEC EDGAR client not available")

from quiver_engine import QuiverStrategyEngine


class HybridDataEngine:
    """
    Smart data engine that automatically selects best source:
    1. Try Quiver API first (fast, clean data)
    2. Fall back to SEC EDGAR if Quiver unavailable (free 13F data)
    3. Cache results for efficiency
    """
    
    def __init__(self, quiver_api_key: str):
        self.quiver = QuiverStrategyEngine(quiver_api_key)
        self.sec_edgar = SECEdgarClient() if SEC_EDGAR_AVAILABLE else None
        self._cache = {}
        
        # Map strategy names to fund names for SEC EDGAR
        self.strategy_to_fund_map = {
            "Michael Burry": "Scion Asset Management",
            "Bill Ackman": "Pershing Square Capital Management",
            "Howard Marks": "Oaktree Capital Management",
            "Bill Gates": "Bill & Melinda Gates Foundation Trust"
        }
    
    def get_13f_holdings(self, strategy_name: str, use_fallback: bool = True) -> List[str]:
        """
        Get 13F holdings for a hedge fund strategy.
        Tries Quiver first, falls back to SEC EDGAR if needed.
        
        Args:
            strategy_name: Name of the strategy (e.g., "Michael Burry")
            use_fallback: If True, try SEC EDGAR if Quiver fails
            
        Returns:
            List of ticker symbols
        """
        # Check cache
        cache_key = f"13f_{strategy_name}"
        if cache_key in self._cache:
            cache_time, cached_data = self._cache[cache_key]
            # Cache valid for 24 hours
            if (datetime.now() - cache_time).total_seconds() < 86400:
                logging.info(f"Using cached 13F data for {strategy_name}")
                return cached_data
        
        # Try Quiver first
        try:
            logging.info(f"Attempting to fetch {strategy_name} from Quiver API...")
            tickers = self.quiver.get_signals(strategy_name)
            if tickers:
                logging.info(f"✓ Successfully got {len(tickers)} tickers from Quiver")
                self._cache[cache_key] = (datetime.now(), tickers)
                return tickers
            else:
                logging.warning(f"Quiver returned empty data for {strategy_name}")
        except Exception as e:
            logging.warning(f"Quiver API failed for {strategy_name}: {e}")
        
        # Fall back to SEC EDGAR
        if use_fallback and self.sec_edgar and strategy_name in self.strategy_to_fund_map:
            logging.info(f"Falling back to SEC EDGAR for {strategy_name}...")
            try:
                fund_name = self.strategy_to_fund_map[strategy_name]
                tickers = self._get_13f_from_edgar(fund_name)
                if tickers:
                    logging.info(f"✓ Successfully got {len(tickers)} tickers from SEC EDGAR")
                    self._cache[cache_key] = (datetime.now(), tickers)
                    return tickers
                else:
                    logging.warning(f"SEC EDGAR returned no tickers for {fund_name}")
            except Exception as e:
                logging.error(f"SEC EDGAR failed for {strategy_name}: {e}")
        
        logging.error(f"All data sources failed for {strategy_name}")
        return []
    
    def _get_13f_from_edgar(self, fund_name: str, top_n: int = 20) -> List[str]:
        """Get top holdings from SEC EDGAR 13F filings."""
        try:
            holdings_df = self.sec_edgar.get_latest_holdings(fund_name)
            
            if holdings_df.empty:
                logging.warning(f"No holdings found for {fund_name}")
                return []
            
            # Sort by value and get top holdings
            if 'Value' in holdings_df.columns:
                top_holdings = holdings_df.nlargest(top_n, 'Value')
                
                # Try to extract tickers
                tickers = []
                
                # Method 1: Use Ticker column if available
                if 'Ticker' in top_holdings.columns:
                    tickers.extend(top_holdings['Ticker'].dropna().tolist())
                
                # Method 2: Extract from company names if we don't have enough tickers
                if len(tickers) < 5 and 'Name' in top_holdings.columns:
                    tickers.extend(self._extract_tickers_from_names(top_holdings['Name'].tolist()))
                
                # Clean up tickers
                tickers = [t.upper().strip() for t in tickers if t]
                tickers = list(set(tickers))  # Remove duplicates
                
                return tickers[:top_n]
        
        except Exception as e:
            logging.error(f"Error getting EDGAR data for {fund_name}: {e}")
        
        return []
    
    def _extract_tickers_from_names(self, names: List[str]) -> List[str]:
        """Extract ticker symbols from company names using mapping."""
        # Extended company name to ticker mapping
        name_to_ticker = {
            'APPLE': 'AAPL',
            'MICROSOFT': 'MSFT',
            'AMAZON': 'AMZN',
            'ALPHABET': 'GOOGL',
            'GOOGLE': 'GOOGL',
            'META': 'META',
            'FACEBOOK': 'META',
            'TESLA': 'TSLA',
            'NVIDIA': 'NVDA',
            'BERKSHIRE HATHAWAY': 'BRK.B',
            'JPMORGAN': 'JPM',
            'JOHNSON': 'JNJ',
            'VISA': 'V',
            'PROCTER': 'PG',
            'UNITEDHEALTH': 'UNH',
            'HOME DEPOT': 'HD',
            'MASTERCARD': 'MA',
            'PFIZER': 'PFE',
            'COCA-COLA': 'KO',
            'INTEL': 'INTC',
            'CISCO': 'CSCO',
            'NETFLIX': 'NFLX',
            'DISNEY': 'DIS',
            'ORACLE': 'ORCL',
            'SALESFORCE': 'CRM',
            'QUALCOMM': 'QCOM',
            'BROADCOM': 'AVGO',
            'ADOBE': 'ADBE',
            'PAYPAL': 'PYPL',
            'COMCAST': 'CMCSA',
            'AT&T': 'T',
            'VERIZON': 'VZ',
            'WALMART': 'WMT',
            'EXXON': 'XOM',
            'CHEVRON': 'CVX',
            'ABBOTT': 'ABT',
            'MERCK': 'MRK',
            'THERMO': 'TMO',
            'COSTCO': 'COST'
        }
        
        tickers = []
        for name in names:
            name_upper = name.upper()
            for key, ticker in name_to_ticker.items():
                if key in name_upper:
                    tickers.append(ticker)
                    break
        
        return tickers
    
    def get_signals(self, strategy_name: str) -> List[str]:
        """
        Get signals for any strategy.
        Automatically routes 13F strategies to hybrid 13F fetcher.
        Routes other strategies to Quiver.
        """
        # Check if this is a 13F strategy
        if strategy_name in self.strategy_to_fund_map:
            return self.get_13f_holdings(strategy_name, use_fallback=True)
        
        # For all other strategies, use Quiver
        try:
            return self.quiver.get_signals(strategy_name)
        except Exception as e:
            logging.error(f"Error getting signals for {strategy_name}: {e}")
            return []
    
    def get_raw_data_with_metadata(self, strategy_name: str) -> Optional[pd.DataFrame]:
        """Get raw data with metadata, using best available source."""
        # For 13F strategies, try to get detailed holdings
        if strategy_name in self.strategy_to_fund_map:
            fund_name = self.strategy_to_fund_map[strategy_name]
            
            # Try Quiver first
            try:
                raw_df = self.quiver._get_raw_data_with_metadata(strategy_name)
                if raw_df is not None and not raw_df.empty:
                    return raw_df
            except:
                pass
            
            # Fall back to SEC EDGAR
            if self.sec_edgar:
                try:
                    holdings = self.sec_edgar.get_latest_holdings(fund_name)
                    if not holdings.empty:
                        return holdings
                except:
                    pass
        
        # For other strategies, use Quiver
        return self.quiver._get_raw_data_with_metadata(strategy_name)
    
    def get_data_source_status(self, strategy_name: str) -> Dict[str, bool]:
        """Check which data sources are available for a strategy."""
        status = {
            'quiver_available': False,
            'sec_edgar_available': False,
            'currently_using': None
        }
        
        # Check Quiver
        try:
            tickers = self.quiver.get_signals(strategy_name)
            if tickers:
                status['quiver_available'] = True
                status['currently_using'] = 'quiver'
        except:
            pass
        
        # Check SEC EDGAR for 13F strategies
        if strategy_name in self.strategy_to_fund_map and self.sec_edgar:
            try:
                fund_name = self.strategy_to_fund_map[strategy_name]
                tickers = self._get_13f_from_edgar(fund_name)
                if tickers:
                    status['sec_edgar_available'] = True
                    if not status['currently_using']:
                        status['currently_using'] = 'sec_edgar'
            except:
                pass
        
        return status
    
    def clear_cache(self):
        """Clear the data cache."""
        self._cache.clear()
        logging.info("Data cache cleared")


# Convenience function
def create_hybrid_engine(quiver_api_key: str) -> HybridDataEngine:
    """Create a hybrid data engine instance."""
    return HybridDataEngine(quiver_api_key)
