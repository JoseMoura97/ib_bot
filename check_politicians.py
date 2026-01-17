import os
import quiverquant
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
QUIVER_API_KEY = os.getenv('QUIVER_API_KEY')

def check_politician_strategies():
    quiver = quiverquant.quiver(QUIVER_API_KEY)
    print("Fetching congress trading data...")
    df = quiver.congress_trading()
    
    if df is None or df.empty:
        print("No data found.")
        return

    # Look for politicians from the screenshot
    target_politicians = ["Dan Meuser", "Tim Moore", "Rob Bresnahan"]
    
    # Check column names
    print("Columns:", df.columns.tolist())
    
    # Find the representative/politician column
    rep_col = None
    for col in df.columns:
        if col.lower() in ['representative', 'politician', 'name', 'person']:
            rep_col = col
            break
            
    if not rep_col:
        print("Could not find representative column.")
        return

    for poly in target_politicians:
        matches = df[df[rep_col].str.contains(poly, case=False, na=False)]
        if not matches.empty:
            print(f"\nFound {len(matches)} trades for {poly}")
            print(matches[['Ticker', 'Transaction', 'Date']].head(5))
        else:
            print(f"\nNo trades found for {poly}")

if __name__ == "__main__":
    check_politician_strategies()
