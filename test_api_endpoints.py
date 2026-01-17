"""
Direct API endpoint tests for Quiver Quantitative strategies.

This script tests the raw API endpoints to verify data availability
and response formats for each strategy.
"""

import os
import requests
import json
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()
QUIVER_API_KEY = os.getenv('QUIVER_API_KEY')

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def test_official_strategy_endpoint(strategy_name):
    """Test the official Quiver strategies/holdings endpoint."""
    print(f"\n{BLUE}Testing Strategy: {strategy_name}{RESET}")
    print("=" * 70)
    
    # Try different URL formats
    url_formats = [
        f"https://api.quiverquant.com/beta/strategies/holdings/{strategy_name}",
        f"https://api.quiverquant.com/live/strategies/holdings/{strategy_name}",
        f"https://api.quiverquant.com/beta/strategies/holdings/{strategy_name.replace(' ', '%20')}",
        f"https://api.quiverquant.com/live/strategies/holdings/{strategy_name.replace(' ', '%20')}"
    ]
    
    headers = {
        "Authorization": f"Bearer {QUIVER_API_KEY}",
        "Accept": "application/json"
    }
    
    for url in url_formats:
        try:
            print(f"Trying URL: {url}")
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                print(f"{GREEN}✓ SUCCESS{RESET}")
                print(f"  Holdings found: {len(data)}")
                
                if data and len(data) > 0:
                    print(f"  Sample holding: {json.dumps(data[0], indent=2)}")
                    
                    # Extract tickers
                    tickers = []
                    for item in data:
                        ticker = item.get('Ticker') or item.get('Symbol') or item.get('ticker')
                        if ticker:
                            tickers.append(ticker)
                    
                    if tickers:
                        print(f"  Tickers: {', '.join(tickers[:10])}{'...' if len(tickers) > 10 else ''}")
                        print(f"  Total unique tickers: {len(set(tickers))}")
                
                return {
                    'success': True,
                    'url': url,
                    'count': len(data),
                    'data': data
                }
            
            elif response.status_code == 403:
                print(f"{YELLOW}⚠ Access Denied (403) - May require premium subscription{RESET}")
            elif response.status_code == 404:
                print(f"{YELLOW}⚠ Not Found (404){RESET}")
            else:
                print(f"{RED}✗ Failed with status code: {response.status_code}{RESET}")
                print(f"  Response: {response.text[:200]}")
        
        except requests.Timeout:
            print(f"{RED}✗ Request timed out{RESET}")
        except Exception as e:
            print(f"{RED}✗ Error: {str(e)}{RESET}")
    
    return {
        'success': False,
        'error': 'All endpoint attempts failed'
    }


def test_raw_data_endpoint(endpoint_type, params=None):
    """Test raw data endpoints (congress, insider, sec13f, lobbying)."""
    print(f"\n{BLUE}Testing Raw Data Endpoint: {endpoint_type}{RESET}")
    print("=" * 70)
    
    endpoints = {
        'congress': 'https://api.quiverquant.com/beta/live/congress',
        'insider': 'https://api.quiverquant.com/beta/live/insiders',
        'sec13f': 'https://api.quiverquant.com/beta/live/sec13f',
        'lobbying': 'https://api.quiverquant.com/beta/live/lobbying'
    }
    
    if endpoint_type not in endpoints:
        print(f"{RED}✗ Unknown endpoint type{RESET}")
        return {'success': False}
    
    url = endpoints[endpoint_type]
    if params:
        url += '?' + '&'.join([f"{k}={v}" for k, v in params.items()])
    
    headers = {
        "Authorization": f"Bearer {QUIVER_API_KEY}",
        "Accept": "application/json"
    }
    
    try:
        print(f"URL: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print(f"{GREEN}✓ SUCCESS{RESET}")
            
            if isinstance(data, list):
                print(f"  Records returned: {len(data)}")
                if data:
                    print(f"  Sample record keys: {list(data[0].keys())}")
            elif isinstance(data, dict):
                print(f"  Response keys: {list(data.keys())}")
            
            return {
                'success': True,
                'count': len(data) if isinstance(data, list) else 1,
                'data': data
            }
        
        elif response.status_code == 403:
            print(f"{YELLOW}⚠ Access Denied (403){RESET}")
        else:
            print(f"{RED}✗ Failed with status code: {response.status_code}{RESET}")
            print(f"  Response: {response.text[:200]}")
    
    except Exception as e:
        print(f"{RED}✗ Error: {str(e)}{RESET}")
    
    return {'success': False}


def run_all_strategy_tests():
    """Run tests for all 5 strategies."""
    print("\n" + "=" * 70)
    print(f"{BLUE}QUIVER QUANTITATIVE API ENDPOINT TESTS{RESET}")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API Key: {'✓ Loaded' if QUIVER_API_KEY else '✗ Missing'}")
    print("=" * 70)
    
    if not QUIVER_API_KEY:
        print(f"\n{RED}ERROR: QUIVER_API_KEY not found in .env file{RESET}")
        return
    
    strategies = [
        "Congress Buys",
        "Dan Meuser",
        "Sector Weighted DC Insider",
        "Michael Burry",
        "Lobbying Spending Growth"
    ]
    
    results = {}
    
    # Test each strategy's official endpoint
    for strategy in strategies:
        result = test_official_strategy_endpoint(strategy)
        results[strategy] = result
    
    # Also test raw data endpoints
    print(f"\n\n{BLUE}{'=' * 70}{RESET}")
    print(f"{BLUE}RAW DATA ENDPOINT TESTS{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}")
    
    raw_endpoints = [
        ('congress', None),
        ('insider', None),
        ('sec13f', {'ticker': 'Scion%20Asset%20Management'}),
        ('lobbying', None)
    ]
    
    for endpoint, params in raw_endpoints:
        test_raw_data_endpoint(endpoint, params)
    
    # Summary
    print(f"\n\n{BLUE}{'=' * 70}{RESET}")
    print(f"{BLUE}TEST SUMMARY{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}")
    
    successful = sum(1 for r in results.values() if r.get('success', False))
    failed = len(results) - successful
    
    print(f"\nTotal Strategies Tested: {len(results)}")
    print(f"{GREEN}Successful: {successful}{RESET}")
    print(f"{RED}Failed: {failed}{RESET}")
    
    print("\nDetailed Results:")
    for strategy, result in results.items():
        status = f"{GREEN}✓{RESET}" if result.get('success') else f"{RED}✗{RESET}"
        count = result.get('count', 0)
        print(f"  {status} {strategy}: {count} holdings")
    
    print("\n" + "=" * 70)
    
    return results


def test_specific_strategy(strategy_name):
    """Test a specific strategy by name."""
    print(f"\n{BLUE}Testing Specific Strategy: {strategy_name}{RESET}")
    result = test_official_strategy_endpoint(strategy_name)
    
    if result.get('success'):
        print(f"\n{GREEN}Test passed!{RESET}")
    else:
        print(f"\n{RED}Test failed!{RESET}")
    
    return result


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        # Test specific strategy from command line
        strategy = ' '.join(sys.argv[1:])
        test_specific_strategy(strategy)
    else:
        # Run all tests
        run_all_strategy_tests()
