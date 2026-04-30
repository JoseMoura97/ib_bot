"""Show Michael Burry's current holdings."""
from sec_edgar import SECEdgarClient

client = SECEdgarClient()
holdings = client.get_latest_holdings('Scion Asset Management')

print('Michael Burry (Scion Asset Management) Current Holdings:')
print('=' * 60)

if not holdings.empty:
    total_value = 0
    for _, row in holdings.iterrows():
        name = str(row.get('Name', 'N/A'))[:35]
        ticker = row.get('Ticker') or row.get('TickerFromName', 'N/A')
        value = row.get('Value', 0)
        shares = row.get('Shares', 0)
        total_value += value
        print(f'{str(ticker):<8} {name:<35} ${value:>12,}  ({shares:,} shares)')
    print('=' * 60)
    print(f'Total portfolio value: ${total_value:,}')
    print(f'Number of positions: {len(holdings)}')
else:
    print('No holdings found')
