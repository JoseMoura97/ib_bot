import os
from quiver_engine import QuiverStrategyEngine
from dotenv import load_dotenv
import pandas as pd

load_dotenv()
QUIVER_API_KEY = os.getenv('QUIVER_API_KEY')

def replicate_copy_trading():
    if not QUIVER_API_KEY:
        print("Please set QUIVER_API_KEY in .env")
        return

    engine = QuiverStrategyEngine(QUIVER_API_KEY)
    
    # List of strategies from the user's screenshot
    strategies = [
        "Congress Buys",
        "Dan Meuser",
        "Michael Burry",
        "Lobbying Spending Growth",
        "Sector Weighted DC Insider"
    ]
    
    print(f"{'Strategy':<30} | {'Holdings':<50}")
    print("-" * 85)
    
    all_signals = {}
    for strat in strategies:
        holdings = engine.get_signals(strat)
        all_signals[strat] = holdings
        holdings_str = ", ".join(holdings) if holdings else "No recent signals"
        print(f"{strat:<30} | {holdings_str:<50}")

    # Create a combined target portfolio (Equal Weighting across strategies)
    print("\n--- Replicated Combined Portfolio ---")
    combined = []
    for h in all_signals.values():
        combined.extend(h)
    
    unique_tickers = list(set(combined))
    print(f"Total unique tickers to hold: {len(unique_tickers)}")
    print(f"Tickers: {', '.join(unique_tickers)}")

if __name__ == "__main__":
    replicate_copy_trading()
