"""
Create sample plot data for quick visualization testing.
This generates synthetic equity curves based on the actual CAGR/Sharpe metrics.
"""

import json
import os
from datetime import datetime, timedelta
import numpy as np

def create_sample_plot_data():
    """Create sample plot data with realistic curves based on validation results."""
    
    # Load validation results to get actual metrics
    try:
        with open('.cache/last_validation_results.json', 'r') as f:
            validation = json.load(f)
    except:
        print("✗ Could not load validation results")
        return None
    
    # Generate dates (weekly from 2020-01-01 to now)
    start_date = datetime(2020, 1, 1)
    end_date = datetime.now()
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=7)  # Weekly
    
    n_periods = len(dates)
    
    # Generate SPY benchmark (moderate growth with volatility)
    np.random.seed(42)
    spy_returns = np.random.normal(0.15/52, 0.18/np.sqrt(52), n_periods)  # ~15% annual return, ~18% vol
    spy_curve = np.exp(np.cumsum(spy_returns)) * 100
    
    plot_data = {
        "generated_at": datetime.now().isoformat(),
        "benchmark": {
            "name": "SPY",
            "dates": dates,
            "values": [round(v, 2) for v in spy_curve.tolist()]
        },
        "strategies": {}
    }
    
    # Create curves for each strategy based on their actual metrics
    strategies = validation.get('strategies', {})
    
    for strategy_name, metrics in strategies.items():
        # Skip strategies with explicit error status, but include those without status field
        if metrics.get('status') in ['ERROR', 'FAILED']:
            continue
        
        # Get actual metrics (convert from percentages)
        cagr = metrics.get('cagr', 0)  # Already in percentage
        sharpe = metrics.get('sharpe', 0.5)
        max_dd = metrics.get('max_drawdown', -30)  # Already in percentage
        
        # Calculate weekly return and volatility from annual metrics
        annual_return = cagr / 100
        annual_vol = (annual_return / sharpe) if sharpe > 0 else 0.20
        
        weekly_return = annual_return / 52
        weekly_vol = annual_vol / np.sqrt(52)
        
        # Generate returns with some autocorrelation for realism
        np.random.seed(hash(strategy_name) % 2**32)
        returns = np.random.normal(weekly_return, weekly_vol, n_periods)
        
        # Add autocorrelation (momentum)
        for i in range(1, n_periods):
            returns[i] = 0.7 * returns[i] + 0.3 * returns[i-1]
        
        # Create equity curve
        equity_curve = np.exp(np.cumsum(returns)) * 100
        
        # Apply a synthetic drawdown to match max_dd approximately
        if max_dd < -5:
            dd_magnitude = abs(max_dd) / 100
            dd_start = n_periods // 3
            dd_length = n_periods // 6
            dd_curve = np.ones(n_periods)
            for i in range(dd_start, min(dd_start + dd_length, n_periods)):
                progress = (i - dd_start) / dd_length
                dd_curve[i] = 1 - dd_magnitude * np.sin(progress * np.pi)
            equity_curve *= dd_curve
        
        plot_data['strategies'][strategy_name] = {
            "name": strategy_name,
            "dates": dates,
            "values": [round(v, 2) for v in equity_curve.tolist()],
            "start_date": metrics.get('start_date', '2020-01-01'),
            "cagr": round(cagr, 2),
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(max_dd, 2)
        }
    
    # Save to file
    os.makedirs('.cache', exist_ok=True)
    output_file = '.cache/plot_data.json'
    
    with open(output_file, 'w') as f:
        json.dump(plot_data, f, indent=2)
    
    file_size = os.path.getsize(output_file) / 1024
    
    print("✓ Generated sample plot data")
    print(f"  Strategies: {len(plot_data['strategies'])}")
    print(f"  Data points per strategy: {len(dates)}")
    print(f"  File: {output_file} ({file_size:.1f} KB)")
    print("\nNote: This is sample data with synthetic curves based on actual metrics.")
    print("For real equity curves, run: python generate_plot_data.py (takes ~30-60 min)")
    
    return plot_data

if __name__ == "__main__":
    create_sample_plot_data()
