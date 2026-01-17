#!/usr/bin/env python
"""Debug politician filtering with bulk data."""

from dotenv import load_dotenv
import os
import pandas as pd
from datetime import datetime, timedelta
load_dotenv()
from quiver_engine import QuiverStrategyEngine

api_key = os.getenv('QUIVER_API_KEY')
engine = QuiverStrategyEngine(api_key)

# Get bulk data
df = engine._get_bulk_congress_data()
print(f'Total bulk records: {len(df)}')

date_col = 'TransactionDate'
print(f'Date range: {df[date_col].min()} to {df[date_col].max()}')
print()

# Check each politician
politicians = ['Meuser', 'Beyer', 'Pelosi']
cutoff = datetime.now() - timedelta(days=365)
print(f'Cutoff date (365 days ago): {cutoff}')
print()

for pol in politicians:
    matches = df[df['Representative'].str.contains(pol, case=False, na=False)]
    print(f'{pol}:')
    print(f'  Total trades: {len(matches)}')
    
    if len(matches) > 0:
        # Check date filtering
        recent = matches[matches[date_col] > cutoff]
        print(f'  Trades in last 365 days: {len(recent)}')
        
        # Check purchase filtering
        purchases = matches[matches['Transaction'].str.lower().str.contains('purchase|buy', na=False)]
        print(f'  Purchase trades (all time): {len(purchases)}')
        
        recent_purchases = purchases[purchases[date_col] > cutoff]
        print(f'  Purchase trades (last 365 days): {len(recent_purchases)}')
        
        if len(recent) > 0:
            latest = recent.sort_values(date_col, ascending=False).head(5)
            print('  Recent trades:')
            for _, row in latest.iterrows():
                tx_date = row[date_col]
                if pd.notna(tx_date):
                    print(f"    {tx_date.date()} - {row['Ticker']} - {row['Transaction']}")
    print()
