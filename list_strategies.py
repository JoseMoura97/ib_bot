import json
d = json.load(open('.cache/plot_data.json'))
print(f'Total strategies: {len(d["strategies"])}')
print(f'Has benchmark: {d.get("benchmark") is not None}')
print('\nAll strategies:')
for i, (name, strat) in enumerate(sorted(d['strategies'].items()), 1):
    cagr = strat.get('cagr', 0)
    points = len(strat.get('values', []))
    print(f'  {i:2}. {name:<45} CAGR: {cagr:>6.1f}%  Points: {points}')
