"""Check Michael Burry CAGR discrepancy."""
import json

# Check validation data
val = json.load(open('.cache/last_validation_results.json'))
if 'Michael Burry' in val.get('strategies', {}):
    mb = val['strategies']['Michael Burry']
    print('Validation Results (Quiver reference):')
    print(f'  CAGR: {mb.get("cagr", "N/A")}%')
    print(f'  Sharpe: {mb.get("sharpe", "N/A")}')
    print(f'  Max DD: {mb.get("max_drawdown", "N/A")}%')
else:
    print('Michael Burry not in validation results')

# Check plot data  
plot = json.load(open('.cache/plot_data.json'))
if 'Michael Burry' in plot.get('strategies', {}):
    mb = plot['strategies']['Michael Burry']
    print(f'\nPlot Data (IB backtest):')
    print(f'  CAGR: {mb.get("cagr", "N/A")}%')
    print(f'  Sharpe: {mb.get("sharpe", "N/A")}')
    
    vals = mb.get('values', [])
    dates = mb.get('dates', [])
    if vals:
        print(f'  Points: {len(vals)}')
        print(f'  Start: {dates[0]} = {vals[0]}')
        print(f'  End: {dates[-1]} = {vals[-1]}')
        total_return = (vals[-1] / vals[0] - 1) * 100
        years = len(vals) / 52  # Weekly data
        cagr_calc = ((vals[-1] / vals[0]) ** (1/years) - 1) * 100
        print(f'  Total return: {total_return:.1f}%')
        print(f'  Years: {years:.1f}')
        print(f'  Calculated CAGR: {cagr_calc:.1f}%')
