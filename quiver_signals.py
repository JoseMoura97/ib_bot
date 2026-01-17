import quiverquant
import pandas as pd
from datetime import datetime, timedelta
from quiver_engine import QuiverStrategyEngine
import os
import json

class QuiverSignals:
    # Strategy metadata with descriptions and full metrics
    CORE_STRATEGIES = {
        "Congress Buys": {
            "description": "Tracks the 10 most-purchased stocks by all Congress members, weighted by purchase size; weekly rebalancing.",
            "category": "core",
            "subcategory": "Congressional Group",
            "start_date": "2020-04-01",
            "return_1d": "1.35%",
            "return_30d": "-0.31%",
            "return_1y": "33.27%",
            "cagr": "34.99%",
            "max_drawdown": "-22.80%",
            "beta": 1.12,
            "alpha": 0.09,
            "sharpe": 1.054,
            "win_rate": "64.11%",
            "avg_win": "0.35%",
            "avg_loss": "-0.25%",
            "volatility": "4.62%",
            "info_ratio": 0.75,
            "treynor": 0.20,
            "trades": 2914
        },
        "Dan Meuser": {
            "description": "Mirrors portfolio of Rep. Dan Meuser and family; rebalanced when new trades or annual reports are filed.",
            "category": "core",
            "subcategory": "Congressional Individual",
            "start_date": "2019-08-14",
            "return_1d": "1.32%",
            "return_30d": "-3.35%",
            "return_1y": "22.39%",
            "cagr": "38.16%",
            "max_drawdown": "-43.30%",
            "beta": 1.29,
            "alpha": 0.14,
            "sharpe": 1.024,
            "win_rate": "74.00%",
            "avg_win": "1.24%",
            "avg_loss": "-0.17%",
            "volatility": "6.59%",
            "info_ratio": 1.16,
            "treynor": 0.20,
            "trades": 493
        },
        "Sector Weighted DC Insider": {
            "description": "Combines three data streams (lobbying, government contracts, Congress trading); holdings sector-weighted to match S&P 500; monthly rebalancing.",
            "category": "core",
            "subcategory": "Alternative Data",
            "start_date": "2020-04-01",
            "return_1d": "0.67%",
            "return_30d": "-0.12%",
            "return_1y": "19.34%",
            "cagr": "24.17%",
            "max_drawdown": "-18.70%",
            "beta": 0.98,
            "alpha": 0.06,
            "sharpe": 1.011,
            "win_rate": "65.78%",
            "avg_win": "0.41%",
            "avg_loss": "-0.28%",
            "volatility": "3.71%",
            "info_ratio": 0.59,
            "treynor": 0.17,
            "trades": 2145
        },
        "Michael Burry": {
            "description": "Mirrors Scion Asset Management portfolio using 13F filings; rebalanced quarterly when new filings are reported.",
            "category": "core",
            "subcategory": "Hedge Fund Manager",
            "api_status": "requires_sec13f_subscription",
            "start_date": "2016-02-17",
            "return_1d": "0.75%",
            "return_30d": "7.43%",
            "return_1y": "78.86%",
            "cagr": "30.61%",
            "max_drawdown": "-52.10%",
            "beta": 0.83,
            "alpha": 0.16,
            "sharpe": 0.725,
            "win_rate": "71.34%",
            "avg_win": "1.63%",
            "avg_loss": "-1.01%",
            "volatility": "10.56%",
            "info_ratio": 0.48,
            "treynor": 0.28,
            "trades": 652
        },
        "Lobbying Spending Growth": {
            "description": "Companies with highest quarter-over-quarter growth in U.S. federal lobbying expenditures; equal-weighted; monthly rebalancing.",
            "category": "core",
            "subcategory": "Alternative Data",
            "start_date": "2009-03-01",
            "return_1d": "-0.78%",
            "return_30d": "-0.55%",
            "return_1y": "18.23%",
            "cagr": "26.67%",
            "max_drawdown": "-42.80%",
            "beta": 1.11,
            "alpha": 0.08,
            "sharpe": 0.865,
            "win_rate": "65.22%",
            "avg_win": "0.43%",
            "avg_loss": "-0.38%",
            "volatility": "4.89%",
            "info_ratio": 0.71,
            "treynor": 0.17,
            "trades": 892
        }
    }
    
    EXPERIMENTAL_STRATEGIES = {
        "Transportation and Infra. Committee (House)": {
            "description": "Tracks purchases by House Transportation & Infrastructure Committee members, weighted by purchase size; weekly rebalancing.",
            "category": "experimental",
            "subcategory": "Congressional Committee",
            "start_date": "2020-04-01",
            "return_1d": "3.24%",
            "return_30d": "-1.78%",
            "return_1y": "28.91%",
            "cagr": "33.44%",
            "max_drawdown": "-39.90%",
            "beta": 1.18,
            "alpha": 0.11,
            "sharpe": 1.056,
            "win_rate": "67.33%",
            "avg_win": "0.61%",
            "avg_loss": "-0.52%",
            "volatility": "5.23%",
            "info_ratio": 0.82,
            "treynor": 0.18,
            "trades": 1121
        },
        "U.S. House Long-Short": {
            "description": "Long position in stocks House members buy, short position in stocks House members sell; 130/30 leverage; weekly rebalancing.",
            "category": "experimental",
            "subcategory": "Congressional Group",
            "start_date": "2020-04-01",
            "return_1d": "-3.40%",
            "return_30d": "0.48%",
            "return_1y": "30.23%",
            "cagr": "35.14%",
            "max_drawdown": "-24.30%",
            "beta": 1.06,
            "alpha": 0.10,
            "sharpe": 0.993,
            "win_rate": "54.18%",
            "avg_win": "0.30%",
            "avg_loss": "-0.20%",
            "volatility": "5.57%",
            "info_ratio": 0.63,
            "treynor": 0.22,
            "trades": 4963
        },
        "Top Gov Contract Recipients": {
            "description": "Top 20 recipients of U.S. government contracts, weighted by announced contract value; monthly rebalancing.",
            "category": "experimental",
            "subcategory": "Alternative Data",
            "start_date": "2009-03-01",
            "return_1d": "-0.45%",
            "return_30d": "1.12%",
            "return_1y": "16.78%",
            "cagr": "18.58%",
            "max_drawdown": "-41.20%",
            "beta": 0.94,
            "alpha": 0.01,
            "sharpe": 0.739,
            "win_rate": "59.88%",
            "avg_win": "0.41%",
            "avg_loss": "-0.35%",
            "volatility": "3.88%",
            "info_ratio": 0.21,
            "treynor": 0.13,
            "trades": 1456
        },
        "Donald Beyer": {
            "description": "Mirrors portfolio of Rep. Donald Beyer and family; rebalanced when new trades or annual reports are filed.",
            "category": "experimental",
            "subcategory": "Congressional Individual",
            "start_date": "2016-05-09",
            "return_1d": "-0.51%",
            "return_30d": "-0.34%",
            "return_1y": "9.87%",
            "cagr": "20.17%",
            "max_drawdown": "-32.50%",
            "beta": 1.06,
            "alpha": 0.03,
            "sharpe": 0.732,
            "win_rate": "71.56%",
            "avg_win": "0.57%",
            "avg_loss": "-0.19%",
            "volatility": "3.68%",
            "info_ratio": 0.52,
            "treynor": 0.13,
            "trades": 612
        },
        "Josh Gottheimer": {
            "description": "Mirrors portfolio of Rep. Josh Gottheimer and family; rebalanced when new trades or annual reports are filed.",
            "category": "experimental",
            "subcategory": "Congressional Individual",
            "start_date": "2019-01-01",
            "return_1d": "-0.33%",
            "return_30d": "-0.88%",
            "return_1y": "11.24%",
            "cagr": "23.48%",
            "max_drawdown": "-33.70%",
            "beta": 1.08,
            "alpha": 0.04,
            "sharpe": 0.727,
            "win_rate": "70.18%",
            "avg_win": "0.62%",
            "avg_loss": "-0.21%",
            "volatility": "4.12%",
            "info_ratio": 0.58,
            "treynor": 0.15,
            "trades": 543
        },
        "Top Lobbying Spenders": {
            "description": "Top 10 companies with highest lobbying spending; equal-weighted; monthly rebalancing.",
            "category": "experimental",
            "subcategory": "Alternative Data",
            "start_date": "2009-03-01",
            "return_1d": "-0.56%",
            "return_30d": "-0.23%",
            "return_1y": "14.56%",
            "cagr": "15.70%",
            "max_drawdown": "-28.80%",
            "beta": 0.88,
            "alpha": 0.01,
            "sharpe": 0.694,
            "win_rate": "64.15%",
            "avg_win": "0.38%",
            "avg_loss": "-0.32%",
            "volatility": "3.44%",
            "info_ratio": 0.29,
            "treynor": 0.12,
            "trades": 1678
        },
        "Nancy Pelosi": {
            "description": "Mirrors portfolio of Rep. Nancy Pelosi and family; rebalanced when new trades or annual reports are filed.",
            "category": "experimental",
            "subcategory": "Congressional Individual",
            "start_date": "2014-05-16",
            "return_1d": "-0.70%",
            "return_30d": "-0.66%",
            "return_1y": "14.13%",
            "cagr": "21.25%",
            "max_drawdown": "-37.40%",
            "beta": 1.14,
            "alpha": 0.05,
            "sharpe": 0.739,
            "win_rate": "73.04%",
            "avg_win": "0.75%",
            "avg_loss": "-0.17%",
            "volatility": "3.46%",
            "info_ratio": 0.64,
            "treynor": 0.12,
            "trades": 715
        },
        "Sheldon Whitehouse": {
            "description": "Mirrors portfolio of Senator Sheldon Whitehouse and family; rebalanced when new trades or annual reports are filed.",
            "category": "experimental",
            "subcategory": "Congressional Individual",
            "start_date": "2014-02-28",
            "return_1d": "-0.12%",
            "return_30d": "0.56%",
            "return_1y": "8.91%",
            "cagr": "18.22%",
            "max_drawdown": "-30.60%",
            "beta": 1.02,
            "alpha": 0.02,
            "sharpe": 0.707,
            "win_rate": "69.34%",
            "avg_win": "0.51%",
            "avg_loss": "-0.24%",
            "volatility": "3.22%",
            "info_ratio": 0.41,
            "treynor": 0.12,
            "trades": 678
        },
        "Howard Marks": {
            "description": "Mirrors Oaktree Capital Management portfolio using 13F filings; rebalanced quarterly when new filings are reported.",
            "category": "experimental",
            "subcategory": "Hedge Fund Manager",
            "api_status": "requires_sec13f_subscription",
            "start_date": "2015-02-17",
            "return_1d": "-2.01%",
            "return_30d": "-1.47%",
            "return_1y": "11.06%",
            "cagr": "14.49%",
            "max_drawdown": "-45.50%",
            "beta": 0.87,
            "alpha": 0.02,
            "sharpe": 0.495,
            "win_rate": "66.03%",
            "avg_win": "0.53%",
            "avg_loss": "-0.36%",
            "volatility": "3.56%",
            "info_ratio": 0.10,
            "treynor": 0.11,
            "trades": 1099
        },
        "Bill Ackman": {
            "description": "Mirrors Pershing Square Capital Management portfolio using 13F filings; rebalanced quarterly when new filings are reported.",
            "category": "experimental",
            "subcategory": "Hedge Fund Manager",
            "api_status": "requires_sec13f_subscription",
            "start_date": "2015-02-18",
            "return_1d": "0.82%",
            "return_30d": "-0.49%",
            "return_1y": "3.67%",
            "cagr": "16.76%",
            "max_drawdown": "-45.10%",
            "beta": 0.97,
            "alpha": 0.03,
            "sharpe": 0.607,
            "win_rate": "73.52%",
            "avg_win": "0.76%",
            "avg_loss": "-0.51%",
            "volatility": "2.88%",
            "info_ratio": 0.28,
            "treynor": 0.11,
            "trades": 726
        },
        "Wall Street Conviction": {
            "description": "Uses 13F filings for institutions holding over $100M in securities to find each fund's highest conviction stock within the S&P500 universe. Conviction is measured as the percent allocation in their portfolio less the allocation in the S&P500. The highest-conviction stock for all funds are aggregated to form equal-weighted positions. Rebalanced quarterly, 47 days after quarter end to allow time for funds to file. Based on the whitepaper: Systematic 13F Hedge Fund Alpha.",
            "category": "experimental",
            "subcategory": "Alternative Data",
            "api_status": "requires_subscription",
            "start_date": "2017-01-01",
            "return_1d": "-0.89%",
            "return_30d": "4.07%",
            "return_1y": "21.48%",
            "cagr": "17.74%",
            "max_drawdown": "-30.40%",
            "beta": 1.01,
            "alpha": 0.02,
            "sharpe": 0.652,
            "win_rate": "86.05%",
            "avg_win": "0.55%",
            "avg_loss": "-0.85%",
            "volatility": "2.71%",
            "info_ratio": 0.42,
            "treynor": 0.11,
            "trades": 621
        },
        "Insider Purchases": {
            "description": "Corporate insider purchases scored by proprietary model; top 10 equally weighted; weekly rebalancing.",
            "category": "experimental",
            "subcategory": "Alternative Data",
            "start_date": "2014-01-01",
            "return_1d": "-0.34%",
            "return_30d": "0.78%",
            "return_1y": "12.45%",
            "cagr": "18.15%",
            "max_drawdown": "-53.00%",
            "beta": 1.19,
            "alpha": 0.04,
            "sharpe": 0.527,
            "win_rate": "61.33%",
            "avg_win": "0.67%",
            "avg_loss": "-0.58%",
            "volatility": "5.67%",
            "info_ratio": 0.35,
            "treynor": 0.11,
            "trades": 3204
        },
        "Congress Long-Short": {
            "description": "Long position in stocks Congress buys, short position in stocks Congress sells; 130/30 leverage; weekly rebalancing.",
            "category": "experimental",
            "subcategory": "Congressional Group",
            "start_date": "2020-04-01",
            "return_1d": "0.05%",
            "return_30d": "-2.89%",
            "return_1y": "30.25%",
            "cagr": "31.82%",
            "max_drawdown": "-24.60%",
            "beta": 1.13,
            "alpha": 0.07,
            "sharpe": 0.890,
            "win_rate": "51.55%",
            "avg_win": "0.31%",
            "avg_loss": "-0.19%",
            "volatility": "5.72%",
            "info_ratio": 0.52,
            "treynor": 0.19,
            "trades": 5343
        },
        "Congress Sells": {
            "description": "Takes long positions in stocks Congress sells, weighted by sale size; weekly rebalancing.",
            "category": "experimental",
            "subcategory": "Congressional Group",
            "start_date": "2020-04-01",
            "return_1d": "-1.00%",
            "return_30d": "0.45%",
            "return_1y": "3.16%",
            "cagr": "22.79%",
            "max_drawdown": "-26.40%",
            "beta": 1.06,
            "alpha": 0.01,
            "sharpe": 0.735,
            "win_rate": "62.42%",
            "avg_win": "0.29%",
            "avg_loss": "-0.25%",
            "volatility": "3.71%",
            "info_ratio": 0.16,
            "treynor": 0.13,
            "trades": 2856
        },
        "Analyst Buys": {
            "description": "Uses proprietary algorithm scoring Wall Street analysts based on historical accuracy of price targets; selects top 10 highest-conviction stocks; monthly rebalancing.",
            "category": "experimental",
            "subcategory": "Alternative Data",
            "start_date": "2023-02-01",
            "return_1d": "-1.13%",
            "return_30d": "-1.41%",
            "return_1y": "14.40%",
            "cagr": "29.44%",
            "max_drawdown": "-26.10%",
            "beta": 1.24,
            "alpha": 0.03,
            "sharpe": 0.868,
            "win_rate": "80.38%",
            "avg_win": "0.61%",
            "avg_loss": "-0.72%",
            "volatility": "3.10%",
            "info_ratio": 0.66,
            "treynor": 0.12,
            "trades": 336
        },
        "Energy and Commerce Committee (House)": {
            "description": "Tracks purchases by House Energy & Commerce Committee members, weighted by purchase size; weekly rebalancing.",
            "category": "experimental",
            "subcategory": "Congressional Committee",
            "start_date": "2020-04-01",
            "return_1d": "1.39%",
            "return_30d": "1.58%",
            "return_1y": "23.59%",
            "cagr": "21.12%",
            "max_drawdown": "-39.90%",
            "beta": 0.86,
            "alpha": 0.03,
            "sharpe": 0.671,
            "win_rate": "69.47%",
            "avg_win": "0.50%",
            "avg_loss": "-0.58%",
            "volatility": "4.00%",
            "info_ratio": 0.08,
            "treynor": 0.16,
            "trades": 1387
        },
        "Homeland Security Committee (Senate)": {
            "description": "Tracks purchases by Senate Homeland Security Committee members, weighted by purchase size; weekly rebalancing.",
            "category": "experimental",
            "subcategory": "Congressional Committee",
            "start_date": "2020-04-01",
            "return_1d": "-0.42%",
            "return_30d": "1.23%",
            "return_1y": "18.76%",
            "cagr": "11.54%",
            "max_drawdown": "-32.90%",
            "beta": 0.79,
            "alpha": -0.01,
            "sharpe": 0.356,
            "win_rate": "58.88%",
            "avg_win": "0.33%",
            "avg_loss": "-0.29%",
            "volatility": "4.13%",
            "info_ratio": -0.05,
            "treynor": 0.10,
            "trades": 1045
        }
    }
    
    @classmethod
    def get_all_strategies(cls):
        """Returns all available strategies with metadata."""
        base = {**cls.CORE_STRATEGIES, **cls.EXPERIMENTAL_STRATEGIES}
        site = cls._load_site_strategy_cache()
        if not site:
            return base

        for name, meta in site.items():
            existing = base.get(name, {})
            merged = {**existing, **meta}
            if "category" not in merged:
                merged["category"] = "quiver_site"
            if "subcategory" not in merged:
                merged["subcategory"] = "Quiver"
            base[name] = merged
        return base
    
    @classmethod
    def get_strategy_info(cls, strategy_name):
        """Get metadata for a specific strategy."""
        all_strategies = cls.get_all_strategies()
        return all_strategies.get(strategy_name, {})

    @classmethod
    def _load_site_strategy_cache(cls):
        """
        Load Quiver strategy metadata scraped from quiverquant.com.

        Cache format (written by quiver_strategy_sync.py):
          {
            "fetched_at": "...",
            "strategies": { "<Strategy Name>": { ...metrics..., "description": "..."} }
          }
        """
        cache_path = os.getenv(
            "QUIVER_STRATEGY_CACHE_PATH",
            os.path.join(os.path.dirname(__file__), ".cache", "quiver_strategies_site.json"),
        )
        try:
            if not os.path.exists(cache_path):
                return {}
            with open(cache_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            strategies = payload.get("strategies", {})
            return strategies if isinstance(strategies, dict) else {}
        except Exception:
            return {}

    def __init__(self, api_key):
        self.engine = QuiverStrategyEngine(api_key)

    # Core Strategy Methods
    def get_congress_buys(self):
        return self.engine.get_signals("Congress Buys")

    def get_dan_meuser_trades(self):
        return self.engine.get_signals("Dan Meuser")

    def get_sector_insider_signals(self):
        return self.engine.get_signals("Sector Weighted DC Insider")

    def get_michael_burry_holdings(self):
        return self.engine.get_signals("Michael Burry")

    def get_lobbying_growth_signals(self):
        return self.engine.get_signals("Lobbying Spending Growth")
    
    # Experimental Strategy Methods
    def get_transportation_committee_trades(self):
        return self.engine.get_signals("Transportation and Infra. Committee (House)")
    
    def get_house_long_short_signals(self):
        return self.engine.get_signals("U.S. House Long-Short")
    
    def get_gov_contract_recipients(self):
        return self.engine.get_signals("Top Gov Contract Recipients")
    
    def get_donald_beyer_trades(self):
        return self.engine.get_signals("Donald Beyer")
    
    def get_josh_gottheimer_trades(self):
        return self.engine.get_signals("Josh Gottheimer")
    
    def get_top_lobbying_spenders(self):
        return self.engine.get_signals("Top Lobbying Spenders")
    
    def get_nancy_pelosi_trades(self):
        return self.engine.get_signals("Nancy Pelosi")
    
    def get_sheldon_whitehouse_trades(self):
        return self.engine.get_signals("Sheldon Whitehouse")
    
    def get_howard_marks_holdings(self):
        return self.engine.get_signals("Howard Marks")
    
    def get_bill_ackman_holdings(self):
        return self.engine.get_signals("Bill Ackman")
    
    def get_wall_street_conviction(self):
        return self.engine.get_signals("Wall Street Conviction")

    def get_combined_portfolio(self, include_experimental=False):
        """Combines selected strategies into a target ticker list.
        
        Args:
            include_experimental: If True, includes experimental strategies in addition to core ones
        """
        portfolio = set()
        
        # Always include core strategies
        core_strategies = list(self.CORE_STRATEGIES.keys())
        strategies_to_use = core_strategies.copy()
        
        # Optionally include experimental strategies
        if include_experimental:
            strategies_to_use.extend(list(self.EXPERIMENTAL_STRATEGIES.keys()))
        
        for strat in strategies_to_use:
            try:
                signals = self.engine.get_signals(strat)
                if signals:
                    portfolio.update(signals)
            except Exception as e:
                print(f"Error in {strat}: {e}")
                
        return list(portfolio)
