"""Test a single backtest to debug empty equity curves."""
from rebalancing_backtest_engine import RebalancingBacktestEngine
from datetime import datetime
import os

bt = RebalancingBacktestEngine(
    quiver_api_key=os.getenv('QUIVER_API_KEY'),
    initial_capital=100000,
    transaction_cost_bps=0.0,
    price_source='ib',
)

# Test with one simple strategy
print('Testing Congress Long-Short...')
result = bt.run_rebalancing_backtest(
    strategy_name='Congress Long-Short',
    start_date=datetime(2020, 1, 1),
    end_date=datetime.now(),
    lookback_days_override=None,
)

if 'error' in result:
    print(f'ERROR: {result["error"]}')
elif 'equity_curve' in result and result['equity_curve'] is not None:
    ec = result['equity_curve']
    if hasattr(ec, '__len__'):
        print(f'SUCCESS: {len(ec)} rows')
        print(f'CAGR: {result.get("cagr", 0)*100:.1f}%')
        print(f'Sharpe: {result.get("sharpe_ratio", 0):.2f}')
    else:
        print('EMPTY: equity_curve has no length')
else:
    print('EMPTY: No equity curve returned')
    print(f'Keys in result: {list(result.keys())}')
