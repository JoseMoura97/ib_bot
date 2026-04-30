import json
d = json.load(open('/home/ibbot/ib_bot/.cache/plot_data.json'))
print('strategies:', len(d.get('strategies', {})))
print('benchmark:', 'SPY' if d.get('benchmark') else 'None')
print('synthetic:', d.get('synthetic'))
print('data_source:', d.get('data_source'))
for k in d.get('strategies', {}).keys():
    s = d['strategies'][k]
    print(f"  {k}: CAGR={s.get('cagr')}% sharpe={s.get('sharpe')} points={len(s.get('dates',[]))}")
