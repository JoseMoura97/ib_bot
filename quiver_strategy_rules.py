"""
Quiver Strategy Trading Rules - Exact Replication
Implements Quiver's exact methodology for each strategy
"""

from typing import Dict, List, Tuple
from datetime import datetime, timedelta

class QuiverStrategyRules:
    """
    Defines the exact trading rules for each Quiver strategy
    to match their published backtests.
    """
    
    STRATEGY_RULES = {
        # Congressional Group Strategies
        "Congress Buys": {
            "type": "congressional_aggregate",
            "selection": "top_10_purchased",
            "weighting": "purchase_size",  # Weight by transaction amount
            "rebalance_frequency": "weekly",
            "rebalance_day": "monday",
            "universe": "all_congress",
            "lookback_days": 120,  # Look at recent 120 days of purchases
        },
        
        "Congress Sells": {
            "type": "congressional_aggregate",
            "selection": "top_10_sold",
            "weighting": "sale_size",
            "rebalance_frequency": "weekly",
            "rebalance_day": "monday",
            "universe": "all_congress",
            "lookback_days": 120,
        },
        
        "Congress Long-Short": {
            "type": "long_short",
            "long_allocation": 1.30,  # 130% long
            "short_allocation": 0.30,  # 30% short
            "long_selection": "top_buys",
            "short_selection": "top_sells",
            "weighting": "transaction_size",
            "rebalance_frequency": "weekly",
            "rebalance_day": "monday",
            "universe": "all_congress",
            "lookback_days": 120,
        },
        
        # Individual Politicians (Event-Driven)
        "Nancy Pelosi": {
            "type": "portfolio_mirror",
            "weighting": "equal",  # Equal weight portfolio
            "rebalance_frequency": "on_trade",  # When new trade filed
            "min_rebalance_days": 1,  # Check daily for new trades
            "include_family": True,
        },
        
        "Dan Meuser": {
            "type": "portfolio_mirror",
            "weighting": "equal",
            "rebalance_frequency": "on_trade",
            "min_rebalance_days": 1,
            "include_family": True,
        },
        
        "Josh Gottheimer": {
            "type": "portfolio_mirror",
            "weighting": "equal",
            "rebalance_frequency": "on_trade",
            "min_rebalance_days": 1,
            "include_family": True,
        },
        
        "Sheldon Whitehouse": {
            "type": "portfolio_mirror",
            "weighting": "equal",
            "rebalance_frequency": "on_trade",
            "min_rebalance_days": 1,
            "include_family": True,
        },
        
        "Donald Beyer": {
            "type": "portfolio_mirror",
            "weighting": "equal",
            "rebalance_frequency": "on_trade",
            "min_rebalance_days": 1,
            "include_family": True,
        },
        
        # Congressional Committees
        "Transportation and Infra. Committee (House)": {
            "type": "congressional_committee",
            "selection": "committee_purchases",
            "weighting": "purchase_size",
            "rebalance_frequency": "weekly",
            "rebalance_day": "monday",
            "committee": "House Transportation & Infrastructure",
            "lookback_days": 120,
        },
        
        # Long-Short Strategies
        "U.S. House Long-Short": {
            "type": "long_short",
            "long_allocation": 1.30,
            "short_allocation": 0.30,
            "long_selection": "house_buys",
            "short_selection": "house_sells",
            "weighting": "transaction_size",
            "rebalance_frequency": "weekly",
            "rebalance_day": "monday",
            "lookback_days": 120,
        },
        
        # Alternative Data - Lobbying
        "Lobbying Spending Growth": {
            "type": "alternative_data",
            "data_source": "lobbying",
            "selection": "highest_qoq_growth",  # Quarter-over-quarter growth
            "num_holdings": 20,
            "weighting": "equal",
            "rebalance_frequency": "monthly",
            "rebalance_day": 1,  # First day of month
        },
        
        "Top Lobbying Spenders": {
            "type": "alternative_data",
            "data_source": "lobbying",
            "selection": "top_10_spenders",
            "num_holdings": 10,
            "weighting": "equal",
            "rebalance_frequency": "monthly",
            "rebalance_day": 1,
        },
        
        # Alternative Data - Government Contracts
        "Top Gov Contract Recipients": {
            "type": "alternative_data",
            "data_source": "contracts",
            "selection": "top_20_recipients",
            "num_holdings": 20,
            "weighting": "contract_value",  # Weight by announced contract value
            "rebalance_frequency": "monthly",
            "rebalance_day": 1,
        },
        
        # Composite Strategy
        "Sector Weighted DC Insider": {
            "type": "composite",
            "data_sources": ["lobbying", "contracts", "congress"],
            "weighting": "sector_match_sp500",  # Match S&P 500 sector allocation
            "rebalance_frequency": "monthly",
            "rebalance_day": 1,
            "universe": "combined",
        },

        # Official strategies (holdings time-series)
        "WSB Top 10": {
            "type": "official_holdings",
            "weighting": "provided",
            "rebalance_frequency": "weekly",
            "rebalance_day": "monday",
        },
        "Analyst Long": {
            "type": "official_holdings",
            "weighting": "provided",
            "rebalance_frequency": "monthly",
            "rebalance_day": 1,
        },
        "House Natural Resources": {
            "type": "official_holdings",
            "weighting": "provided",
            "rebalance_frequency": "weekly",
            "rebalance_day": "monday",
        },
        "Energy and Commerce Committee (House)": {
            "type": "official_holdings",
            "weighting": "provided",
            "rebalance_frequency": "weekly",
            "rebalance_day": "monday",
        },
        "Homeland Security Committee (Senate)": {
            "type": "official_holdings",
            "weighting": "provided",
            "rebalance_frequency": "weekly",
            "rebalance_day": "monday",
        },
        
        # 13F Hedge Fund Managers
        "Michael Burry": {
            "type": "13f_mirror",
            "fund": "Scion Asset Management",
            "weighting": "portfolio_weight",  # Use actual 13F portfolio weights
            "rebalance_frequency": "quarterly",
            "rebalance_offset_days": 45,  # 45 days after quarter end
        },
        
        "Bill Ackman": {
            "type": "13f_mirror",
            "fund": "Pershing Square Capital Management",
            "weighting": "portfolio_weight",
            "rebalance_frequency": "quarterly",
            "rebalance_offset_days": 45,
        },
        
        "Howard Marks": {
            "type": "13f_mirror",
            "fund": "Oaktree Capital Management",
            "weighting": "portfolio_weight",
            "rebalance_frequency": "quarterly",
            "rebalance_offset_days": 45,
        },
        
        # Alternative Data - Insider Trading
        "Insider Purchases": {
            "type": "alternative_data",
            "data_source": "insider_trades",
            "selection": "top_10_proprietary_score",  # Quiver's proprietary model
            "num_holdings": 10,
            "weighting": "equal",
            "rebalance_frequency": "weekly",
            "rebalance_day": "monday",
        },
        
        # Premium Strategies
        "Wall Street Conviction": {
            "type": "13f_aggregate",
            "selection": "highest_conviction_sp500",  # Highest conviction within S&P 500
            "weighting": "equal",
            "rebalance_frequency": "quarterly",
            "rebalance_offset_days": 47,  # 47 days after quarter end
            "universe": "sp500",
            "min_aum": 100_000_000,  # Institutions with >$100M
        },
        
        "Analyst Buys": {
            "type": "alternative_data",
            "data_source": "analyst_ratings",
            "selection": "top_10_proprietary_score",  # Quiver's analyst accuracy model
            "num_holdings": 10,
            "weighting": "equal",
            "rebalance_frequency": "monthly",
            "rebalance_day": 1,
        },
    }
    
    @classmethod
    def get_strategy_rules(cls, strategy_name: str) -> Dict:
        """Get the exact trading rules for a strategy."""
        return cls.STRATEGY_RULES.get(strategy_name, {})
    
    @classmethod
    def get_rebalance_dates(cls, strategy_name: str, start_date: datetime, end_date: datetime) -> List[datetime]:
        """
        Calculate all rebalance dates for a strategy between start and end dates.
        
        Returns:
            List of datetime objects representing rebalance dates
        """
        rules = cls.get_strategy_rules(strategy_name)
        if not rules:
            return []
        
        frequency = rules.get('rebalance_frequency', 'monthly')
        rebalance_dates = []
        current = start_date
        
        if frequency == 'daily':
            while current <= end_date:
                rebalance_dates.append(current)
                current += timedelta(days=1)
        
        elif frequency == 'weekly':
            # Find first Monday (or specified day)
            target_day = rules.get('rebalance_day', 'monday')
            day_map = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3, 'friday': 4}
            target_weekday = day_map.get(target_day, 0)
            
            while current.weekday() != target_weekday:
                current += timedelta(days=1)
            
            while current <= end_date:
                rebalance_dates.append(current)
                current += timedelta(weeks=1)
        
        elif frequency == 'monthly':
            # First day of month (or specified day)
            target_day = rules.get('rebalance_day', 1)
            
            # Start from first occurrence
            if current.day <= target_day:
                current = current.replace(day=target_day)
            else:
                # Move to next month
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1, day=target_day)
                else:
                    current = current.replace(month=current.month + 1, day=target_day)
            
            while current <= end_date:
                rebalance_dates.append(current)
                # Move to next month
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1)
                else:
                    current = current.replace(month=current.month + 1)
        
        elif frequency == 'quarterly':
            # Quarterly rebalancing (45-47 days after quarter end)
            offset_days = rules.get('rebalance_offset_days', 45)
            
            # Quarter end dates
            quarter_ends = []
            year = start_date.year
            while True:
                for month in [3, 6, 9, 12]:  # Q1, Q2, Q3, Q4
                    # Last day of quarter
                    if month == 3:
                        quarter_end = datetime(year, 3, 31)
                    elif month == 6:
                        quarter_end = datetime(year, 6, 30)
                    elif month == 9:
                        quarter_end = datetime(year, 9, 30)
                    else:
                        quarter_end = datetime(year, 12, 31)
                    
                    rebalance_date = quarter_end + timedelta(days=offset_days)
                    
                    if start_date <= rebalance_date <= end_date:
                        quarter_ends.append(rebalance_date)
                
                year += 1
                if datetime(year, 1, 1) > end_date:
                    break
            
            rebalance_dates = quarter_ends
        
        elif frequency == 'on_trade':
            # Event-driven: Would need actual trade dates
            # For backtesting, approximate with daily checks
            while current <= end_date:
                rebalance_dates.append(current)
                current += timedelta(days=rules.get('min_rebalance_days', 1))
        
        return rebalance_dates
    
    @classmethod
    def get_weighting_method(cls, strategy_name: str) -> str:
        """Get the weighting method for a strategy."""
        rules = cls.get_strategy_rules(strategy_name)
        return rules.get('weighting', 'equal')
    
    @classmethod
    def requires_long_short(cls, strategy_name: str) -> bool:
        """Check if strategy requires long-short implementation."""
        rules = cls.get_strategy_rules(strategy_name)
        return rules.get('type') == 'long_short'
    
    @classmethod
    def get_long_short_allocation(cls, strategy_name: str) -> Tuple[float, float]:
        """Get long and short allocation percentages."""
        rules = cls.get_strategy_rules(strategy_name)
        if rules.get('type') == 'long_short':
            return rules.get('long_allocation', 1.0), rules.get('short_allocation', 0.0)
        return 1.0, 0.0
    
    @classmethod
    def get_strategy_type(cls, strategy_name: str) -> str:
        """Get the strategy type."""
        rules = cls.get_strategy_rules(strategy_name)
        return rules.get('type', 'unknown')
    
    @classmethod
    def summary(cls) -> str:
        """Print summary of all strategies and their rules."""
        output = []
        output.append("=" * 100)
        output.append("QUIVER STRATEGY TRADING RULES")
        output.append("=" * 100)
        
        for strategy_name, rules in cls.STRATEGY_RULES.items():
            output.append(f"\n{strategy_name}")
            output.append("-" * 100)
            output.append(f"  Type: {rules.get('type')}")
            output.append(f"  Weighting: {rules.get('weighting')}")
            output.append(f"  Rebalance: {rules.get('rebalance_frequency')}")
            
            if rules.get('type') == 'long_short':
                output.append(f"  Long/Short: {rules.get('long_allocation', 1.0)*100:.0f}% / {rules.get('short_allocation', 0)*100:.0f}%")
            
            if 'num_holdings' in rules:
                output.append(f"  Holdings: {rules.get('num_holdings')}")
        
        output.append("\n" + "=" * 100)
        return "\n".join(output)


# Quick test
if __name__ == "__main__":
    print(QuiverStrategyRules.summary())
    
    # Test rebalance date calculation
    print("\n\nExample Rebalance Dates:")
    print("=" * 100)
    
    test_strategies = [
        "Congress Buys",  # Weekly
        "Lobbying Spending Growth",  # Monthly
        "Michael Burry",  # Quarterly
    ]
    
    start = datetime(2025, 1, 1)
    end = datetime(2025, 6, 30)
    
    for strategy in test_strategies:
        dates = QuiverStrategyRules.get_rebalance_dates(strategy, start, end)
        print(f"\n{strategy}:")
        print(f"  Frequency: {QuiverStrategyRules.get_strategy_rules(strategy).get('rebalance_frequency')}")
        print(f"  Dates: {[d.strftime('%Y-%m-%d') for d in dates[:6]]}")
        print(f"  Total: {len(dates)} rebalances")
