"""Debug backtest CAGR issues."""
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from rebalancing_backtest_engine import RebalancingBacktestEngine

api_key = os.getenv("QUIVER_API_KEY")
price_source = os.getenv("PRICE_SOURCE", "ib")

bt = RebalancingBacktestEngine(
    quiver_api_key=api_key,
    initial_capital=100000,
    transaction_cost_bps=0.0,
    price_source=price_source,
)

# Test strategies with known issues
test_strategies = [
    "Congress Buys",      # Should be ~30%
    "Congress Sells",     # Should be ~15%  - WAS SHOWING 668%
    "Nancy Pelosi",       # Should be ~24%
    "Insider Purchases",  # Should be ~10% - WAS SHOWING 962%
]

min_start_date = datetime(2020, 1, 1)

for strategy_name in test_strategies:
    print(f"\n{'='*60}")
    print(f"Testing: {strategy_name}")
    print(f"{'='*60}")
    
    result = bt.run_rebalancing_backtest(
        strategy_name=strategy_name,
        start_date=min_start_date,
        end_date=datetime.now(),
    )
    
    if 'error' in result:
        print(f"  ERROR: {result['error']}")
        continue
    
    cagr = result.get('cagr', 0)
    total_return = result.get('total_return', 0)
    final_value = result.get('final_value', 0)
    initial = result.get('initial_capital', 100000)
    
    print(f"  Initial Capital: ${initial:,.2f}")
    print(f"  Final Value:     ${final_value:,.2f}")
    print(f"  Total Return:    {total_return:.4f} ({total_return*100:.2f}%)")
    print(f"  CAGR (raw):      {cagr:.6f}")
    print(f"  CAGR (%):        {cagr*100:.2f}%")
    
    # Check equity curve
    ec = result.get('equity_curve')
    if ec is not None and not ec.empty:
        print(f"  Equity points:   {len(ec)}")
        print(f"  First value:     {ec.iloc[0].values}")
        print(f"  Last value:      {ec.iloc[-1].values}")
