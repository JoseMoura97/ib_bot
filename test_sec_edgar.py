#!/usr/bin/env python
"""
Test SEC EDGAR Integration
Verifies that we can fetch 13F data from SEC's free API
"""

import sys
import os

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

from sec_edgar import SECEdgarClient
from hybrid_data_engine import HybridDataEngine
from dotenv import load_dotenv

load_dotenv()

def test_sec_edgar_client():
    """Test SEC EDGAR client directly."""
    print("="*80)
    print("Testing SEC EDGAR Client")
    print("="*80)
    
    client = SECEdgarClient()
    
    # Test funds
    test_funds = [
        "Scion Asset Management",
        "Pershing Square Capital Management",
        "Oaktree Capital Management"
    ]
    
    for fund_name in test_funds:
        print(f"\n--- Testing: {fund_name} ---")
        
        # Get CIK
        cik = client.get_cik_by_name(fund_name)
        print(f"CIK: {cik}")
        
        if cik:
            # Get recent filings
            filings = client.get_13f_filings(cik, limit=2)
            print(f"Recent filings: {len(filings)}")
            
            if filings:
                print(f"Latest filing date: {filings[0].get('filed_date', 'N/A')}")
                
                # Try to get holdings
                print("Attempting to fetch holdings...")
                holdings = client.get_latest_holdings(fund_name)
                
                if not holdings.empty:
                    print(f"✓ Found {len(holdings)} holdings")
                    print(f"  Columns: {list(holdings.columns)}")
                    
                    # Show top 5
                    if 'Value' in holdings.columns:
                        top_5 = holdings.nlargest(5, 'Value')
                        print("\n  Top 5 holdings by value:")
                        for _, row in top_5.iterrows():
                            name = row.get('Name', 'N/A')
                            value = row.get('Value', 0)
                            ticker = row.get('Ticker', 'N/A')
                            print(f"    {name[:40]:<40} ${value:>12,.0f}  [{ticker}]")
                else:
                    print("⚠ No holdings data retrieved")
        else:
            print("✗ Could not find CIK")

def test_hybrid_engine():
    """Test hybrid data engine."""
    print("\n" + "="*80)
    print("Testing Hybrid Data Engine")
    print("="*80)
    
    api_key = os.getenv('QUIVER_API_KEY')
    if not api_key:
        print("⚠ QUIVER_API_KEY not set - skipping hybrid tests")
        return
    
    engine = HybridDataEngine(api_key)
    
    # Test strategies
    strategies = [
        "Michael Burry",
        "Bill Ackman",
        "Howard Marks"
    ]
    
    for strategy_name in strategies:
        print(f"\n--- Testing: {strategy_name} ---")
        
        # Check data source status
        status = engine.get_data_source_status(strategy_name)
        print(f"Quiver available: {status['quiver_available']}")
        print(f"SEC EDGAR available: {status['sec_edgar_available']}")
        print(f"Currently using: {status['currently_using']}")
        
        # Try to get signals
        print("Fetching signals...")
        tickers = engine.get_signals(strategy_name)
        
        if tickers:
            print(f"✓ Got {len(tickers)} tickers")
            print(f"  Sample: {tickers[:10]}")
        else:
            print("✗ No tickers retrieved")

def test_comparison():
    """Compare Quiver vs SEC EDGAR data."""
    print("\n" + "="*80)
    print("Comparing Quiver vs SEC EDGAR")
    print("="*80)
    
    api_key = os.getenv('QUIVER_API_KEY')
    if not api_key:
        print("⚠ QUIVER_API_KEY not set - skipping comparison")
        return
    
    from quiver_signals import QuiverSignals
    
    qs = QuiverSignals(api_key)
    sec_client = SECEdgarClient()
    
    print("\n--- Michael Burry / Scion Asset Management ---")
    
    # Try Quiver
    print("\nQuiver API:")
    try:
        quiver_tickers = qs.engine.get_signals("Michael Burry")
        print(f"  Tickers: {len(quiver_tickers) if quiver_tickers else 0}")
        if quiver_tickers:
            print(f"  Sample: {quiver_tickers[:10]}")
    except Exception as e:
        print(f"  Error: {e}")
        quiver_tickers = []
    
    # Try SEC EDGAR
    print("\nSEC EDGAR:")
    try:
        edgar_tickers = sec_client.get_top_holdings("Scion Asset Management", top_n=20)
        print(f"  Tickers: {len(edgar_tickers)}")
        if edgar_tickers:
            print(f"  Sample: {edgar_tickers[:10]}")
    except Exception as e:
        print(f"  Error: {e}")
        edgar_tickers = []
    
    # Compare overlap
    if quiver_tickers and edgar_tickers:
        quiver_set = set(quiver_tickers)
        edgar_set = set(edgar_tickers)
        overlap = quiver_set.intersection(edgar_set)
        
        print(f"\nOverlap: {len(overlap)} tickers")
        if overlap:
            print(f"  Common: {sorted(overlap)[:10]}")

def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("SEC EDGAR INTEGRATION TEST SUITE")
    print("="*80)
    
    # Test 1: SEC EDGAR client
    try:
        test_sec_edgar_client()
    except Exception as e:
        print(f"\n✗ SEC EDGAR client test failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 2: Hybrid engine
    try:
        test_hybrid_engine()
    except Exception as e:
        print(f"\n✗ Hybrid engine test failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 3: Comparison
    try:
        test_comparison()
    except Exception as e:
        print(f"\n✗ Comparison test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)

if __name__ == '__main__':
    main()
