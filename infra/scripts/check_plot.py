import json
d = json.load(open('/home/ibbot/ib_bot/.cache/plot_data.json'))
strategies = list(d.get('strategies', {}).keys())
print(f"Generated: {d.get('generated_at')}")
print(f"Strategy count: {len(strategies)}")
for s in sorted(strategies):
    vals = d['strategies'][s].get('values', [])
    cagr = d['strategies'][s].get('cagr', 'N/A')
    print(f"  {s}: {len(vals)} pts, CAGR={cagr}")
bench = d.get('benchmark')
if bench:
    print(f"Benchmark: {bench.get('name', 'N/A')}, {len(bench.get('values', []))} pts")
else:
    print("Benchmark: None")
