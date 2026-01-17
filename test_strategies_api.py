import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
QUIVER_API_KEY = os.getenv('QUIVER_API_KEY')

def test_strategy_endpoint(strategy_name):
    print(f"\n--- Testing Strategy: {strategy_name} ---")
    url = f"https://api.quiverquant.com/beta/strategies/holdings/{strategy_name}"
    headers = {
        "Authorization": f"Bearer {QUIVER_API_KEY}",
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            print(f"Success! Found {len(data)} holdings.")
            if data:
                print("First holding snippet:", data[0])
            return data
        else:
            print(f"Failed with status code: {response.status_code}")
            print("Response:", response.text)
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    if not QUIVER_API_KEY:
        print("Error: QUIVER_API_KEY not found in .env")
    else:
        # Test a few known strategy names from the screenshot
        strategies_to_test = [
            "Congress%20Buys",
            "Dan%20Meuser",
            "Michael%20Burry",
            "Lobbying%20Spending%20Growth",
            "Sector%20Weighted%20DC%20Insider"
        ]
        
        for strat in strategies_to_test:
            test_strategy_endpoint(strat)
