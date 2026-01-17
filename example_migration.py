"""
Example: Migrating from Quiver-only to Hybrid Engine
Shows before/after code comparison
"""

import os

# ============================================================================
# BEFORE: Using Quiver for everything (expensive)
# ============================================================================

def old_way():
    """Old implementation - pays $75/month for Quiver Trader tier."""
    from quiver_signals import QuiverSignals
    
    api_key = os.getenv("QUIVER_API_KEY")
    quiver = QuiverSignals(api_key)
    
    # These require expensive Quiver subscription:
    burry = quiver.get_michael_burry_holdings()  # $$$ Quiver Trader tier
    ackman = quiver.get_bill_ackman_holdings()   # $$$ Quiver Trader tier
    marks = quiver.get_howard_marks_holdings()   # $$$ Quiver Trader tier
    
    # These work on cheaper tier:
    congress = quiver.get_congress_buys()        # $ Quiver Hobbyist tier
    
    return burry, ackman, marks, congress


# ============================================================================
# AFTER: Using Hybrid Engine (saves $65/month)
# ============================================================================

def new_way():
    """New implementation - saves $780/year by using free SEC data."""
    from hybrid_data_engine import create_hybrid_engine
    
    api_key = os.getenv("QUIVER_API_KEY")
    
    # Create hybrid engine
    engine = create_hybrid_engine(
        quiver_api_key=api_key,
        sec_user_agent="IBBot contact@example.com"
    )
    
    # These now use FREE SEC EDGAR data:
    burry = engine.get_signals("Michael Burry")   # FREE via SEC
    ackman = engine.get_signals("Bill Ackman")    # FREE via SEC
    marks = engine.get_signals("Howard Marks")    # FREE via SEC
    
    # These still use Quiver (cheaper tier):
    congress = engine.get_signals("Congress Buys") # $ Quiver Hobbyist tier
    
    return burry, ackman, marks, congress


# ============================================================================
# UPDATE YOUR EXISTING quiver_signals.py CLASS
# ============================================================================

def updated_quiver_signals_class():
    """
    Example of how to update your QuiverSignals class to use hybrid engine.
    
    Copy this pattern into your actual quiver_signals.py file.
    """
    
    class QuiverSignals:
        # Keep all your existing CORE_STRATEGIES and EXPERIMENTAL_STRATEGIES dicts
        # ... (don't change those)
        
        def __init__(self, api_key):
            # CHANGE THIS: Instead of QuiverStrategyEngine
            # self.engine = QuiverStrategyEngine(api_key)
            
            # USE THIS: Hybrid engine
            from hybrid_data_engine import create_hybrid_engine
            self.engine = create_hybrid_engine(
                quiver_api_key=api_key,
                sec_user_agent="IBBot contact@example.com"
            )
        
        # All your methods stay the same!
        # The hybrid engine automatically chooses the best source
        
        def get_michael_burry_holdings(self):
            return self.engine.get_signals("Michael Burry")  # Now FREE via SEC
        
        def get_bill_ackman_holdings(self):
            return self.engine.get_signals("Bill Ackman")    # Now FREE via SEC
        
        def get_howard_marks_holdings(self):
            return self.engine.get_signals("Howard Marks")   # Now FREE via SEC
        
        def get_congress_buys(self):
            return self.engine.get_signals("Congress Buys")  # Still uses Quiver
        
        # ... all other methods work exactly the same


# ============================================================================
# COMPARISON & VALIDATION
# ============================================================================

def compare_old_vs_new():
    """Compare results from Quiver vs SEC to validate data quality."""
    from hybrid_data_engine import create_hybrid_engine
    
    api_key = os.getenv("QUIVER_API_KEY")
    engine = create_hybrid_engine(api_key, "IBBot test@example.com")
    
    print("\n=== DATA QUALITY COMPARISON ===\n")
    
    # Compare Michael Burry data
    comparison = engine.compare_sources("Michael Burry")
    
    print(f"Strategy: {comparison['strategy']}")
    print(f"Fund: {comparison['fund_name']}")
    print(f"\nSEC EDGAR found: {comparison['sec_count']} tickers")
    print(f"Quiver found: {comparison['quiver_count']} tickers")
    print(f"\nData overlap: {comparison['overlap_percentage']:.1f}%")
    
    if comparison['overlap_percentage'] > 80:
        print("✓ High overlap - SEC data is reliable!")
    elif comparison['overlap_percentage'] > 50:
        print("⚠ Moderate overlap - data quality acceptable")
    else:
        print("✗ Low overlap - investigate differences")
    
    # Show tickers only in SEC
    if comparison['sec_only']:
        print(f"\nTickers found by SEC but not Quiver:")
        print(f"  {', '.join(comparison['sec_only'][:10])}")
    
    # Show tickers only in Quiver
    if comparison['quiver_only']:
        print(f"\nTickers found by Quiver but not SEC:")
        print(f"  {', '.join(comparison['quiver_only'][:10])}")
    
    return comparison


# ============================================================================
# COST ANALYSIS
# ============================================================================

def show_cost_savings():
    """Display cost savings analysis."""
    from hybrid_data_engine import create_hybrid_engine
    
    api_key = os.getenv("QUIVER_API_KEY", "demo_key")
    engine = create_hybrid_engine(api_key, "IBBot test@example.com")
    
    savings = engine.estimate_cost_savings()
    
    print("\n=== COST SAVINGS ANALYSIS ===\n")
    print(f"13F Strategies using SEC: {savings['strategies_using_sec']}")
    print(f"\nQuiver Hobbyist Plan: {savings['quiver_hobbyist_cost']}")
    print(f"Quiver Trader Plan (for 13F): {savings['quiver_trader_cost']}")
    print(f"SEC EDGAR: {savings['sec_cost']}")
    print(f"\n💰 Monthly Savings: {savings['monthly_savings']}")
    print(f"💰 Annual Savings: {savings['annual_savings']}")
    print(f"\n{savings['note']}")


# ============================================================================
# MAIN EXAMPLE
# ============================================================================

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Show cost savings
    show_cost_savings()
    
    # Test the new way
    print("\n=== Testing Hybrid Engine ===\n")
    
    try:
        burry, ackman, marks, congress = new_way()
        
        print(f"✓ Michael Burry (SEC): {len(burry)} tickers")
        print(f"✓ Bill Ackman (SEC): {len(ackman)} tickers")
        print(f"✓ Howard Marks (SEC): {len(marks)} tickers")
        print(f"✓ Congress Buys (Quiver): {len(congress)} tickers")
        
        print("\n🎉 Migration successful! You're now saving $780/year.")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("Make sure to set QUIVER_API_KEY environment variable")
    
    # Optionally compare data quality
    if os.getenv("QUIVER_API_KEY"):
        print("\n" + "="*60)
        compare_old_vs_new()
