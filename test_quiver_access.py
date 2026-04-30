"""
Test Quiver API Access and Tier Level
Run this script to check your API key and what data you have access to.
"""
import os
import requests
import sys

def test_quiver_access():
    api_key = os.getenv('QUIVER_API_KEY', '').strip()
    
    print("=" * 70)
    print("QUIVER API ACCESS TEST")
    print("=" * 70)
    print()
    
    if not api_key:
        print("[!] QUIVER_API_KEY environment variable is NOT set")
        print()
        print("To set it:")
        print("  Windows (PowerShell): $env:QUIVER_API_KEY = 'your_api_key'")
        print("  Windows (CMD):        set QUIVER_API_KEY=your_api_key")
        print("  Linux/Mac:            export QUIVER_API_KEY=your_api_key")
        print()
        print("Or add to your .env file: QUIVER_API_KEY=your_api_key")
        return False
    
    print(f"[OK] API Key found: {api_key[:8]}...{api_key[-4:]}")
    print()
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }
    
    # Test endpoints by tier
    tier1_endpoints = [
        ("Bulk Congress Trading", "https://api.quiverquant.com/beta/bulk/congresstrading"),
        ("Live Congress Trading", "https://api.quiverquant.com/beta/live/congresstrading"),
        ("Live Lobbying", "https://api.quiverquant.com/beta/live/lobbying"),
        ("Gov Contracts", "https://api.quiverquant.com/beta/live/govcontracts"),
        ("Historical House Trading", "https://api.quiverquant.com/beta/historical/housetrading"),
    ]
    
    tier2_endpoints = [
        ("Live Insider Trading", "https://api.quiverquant.com/beta/live/insiders"),
        ("Live SEC 13F", "https://api.quiverquant.com/beta/live/sec13f"),
        ("Live ETF Holdings", "https://api.quiverquant.com/beta/live/etfholdings"),
        ("Bulk Political Beta", "https://api.quiverquant.com/beta/bulk/politicalbeta"),
    ]
    
    strategies_endpoint = ("Strategy Holdings", "https://api.quiverquant.com/beta/strategies/holdings")
    
    tier1_access = []
    tier2_access = []
    
    print("Testing Tier 1 endpoints...")
    print("-" * 50)
    for name, url in tier1_endpoints:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                count = len(data) if isinstance(data, list) else "OK"
                print(f"  [OK] {name}: {count} records")
                tier1_access.append(name)
            elif resp.status_code == 403:
                print(f"  [X]  {name}: Access denied (not in your tier)")
            elif resp.status_code == 401:
                print(f"  [X]  {name}: Invalid API key")
            else:
                print(f"  [?]  {name}: HTTP {resp.status_code}")
        except Exception as e:
            print(f"  [!]  {name}: Error - {str(e)[:40]}")
    
    print()
    print("Testing Tier 2 endpoints...")
    print("-" * 50)
    for name, url in tier2_endpoints:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                count = len(data) if isinstance(data, list) else "OK"
                print(f"  [OK] {name}: {count} records")
                tier2_access.append(name)
            elif resp.status_code == 403:
                print(f"  [X]  {name}: Access denied (Tier 2 required)")
            elif resp.status_code == 401:
                print(f"  [X]  {name}: Invalid API key")
            else:
                print(f"  [?]  {name}: HTTP {resp.status_code}")
        except Exception as e:
            print(f"  [!]  {name}: Error - {str(e)[:40]}")
    
    print()
    print("Testing Strategy Holdings endpoint...")
    print("-" * 50)
    try:
        name, url = strategies_endpoint
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                # Count unique strategies
                strategies = set()
                for item in data:
                    if 'Strategy' in item:
                        strategies.add(item['Strategy'])
                print(f"  [OK] {name}: {len(strategies)} unique strategies available")
            else:
                print(f"  [OK] {name}: Access granted")
        elif resp.status_code == 403:
            print(f"  [X]  {name}: Access denied")
        else:
            print(f"  [?]  {name}: HTTP {resp.status_code}")
    except Exception as e:
        print(f"  [!]  {name}: Error - {str(e)[:40]}")
    
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    if len(tier1_access) >= 3:
        print("[OK] TIER 1 ACCESS: Yes")
    elif len(tier1_access) > 0:
        print("[?]  TIER 1 ACCESS: Partial")
    else:
        print("[X]  TIER 1 ACCESS: No")
    
    if len(tier2_access) >= 2:
        print("[OK] TIER 2 ACCESS: Yes")
    elif len(tier2_access) > 0:
        print("[?]  TIER 2 ACCESS: Partial")
    else:
        print("[X]  TIER 2 ACCESS: No")
    
    print()
    
    if len(tier1_access) >= 3 and len(tier2_access) >= 2:
        print("You have TRADER tier ($75/mo) - Full access to all strategies!")
    elif len(tier1_access) >= 3:
        print("You have HOBBYIST tier ($10/mo) - Access to congressional/lobbying strategies")
    elif len(tier1_access) > 0 or len(tier2_access) > 0:
        print("You have partial access - check your subscription status")
    else:
        print("No API access detected - verify your API key is correct")
    
    print()
    print("=" * 70)
    
    return len(tier1_access) > 0


if __name__ == "__main__":
    success = test_quiver_access()
    sys.exit(0 if success else 1)
