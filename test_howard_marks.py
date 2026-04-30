"""Test fetching Howard Marks (Oaktree) 13F data via SEC Edgar."""
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from sec_edgar import SECEdgarClient

fetcher = SECEdgarClient()

print("Testing Oaktree Capital Management (Howard Marks)...")

# Get latest holdings
holdings = fetcher.get_latest_holdings("Oaktree Capital Management")
if holdings is not None and not holdings.empty:
    print(f"Holdings found: {len(holdings)} positions")
    print(f"Top tickers: {holdings['ticker'].head(10).tolist() if 'ticker' in holdings.columns else holdings.index[:10].tolist()}")
    print(f"Columns: {holdings.columns.tolist()}")
else:
    print("No holdings data found")

# Also test getting history
print("\nTesting holdings history...")
history = fetcher.get_holdings_history("Oaktree Capital Management", num_quarters=4)
if history is not None and not history.empty:
    print(f"History found: {len(history)} rows")
    print(f"Unique tickers: {history['ticker'].nunique() if 'ticker' in history.columns else 'N/A'}")
else:
    print("No history found")
