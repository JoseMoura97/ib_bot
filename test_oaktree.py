"""Debug Oaktree 13F parsing."""
from sec_edgar import SECEdgarClient
import logging
logging.basicConfig(level=logging.WARNING)

fetcher = SECEdgarClient()
cik = '0000949509'  # Oaktree
accession = '0000949509-25-000007'  # Latest filing

print('Testing Oaktree parsing...')
holdings = fetcher.parse_13f_holdings(cik, accession)
print(f'Holdings type: {type(holdings)}')
print(f'Holdings empty: {holdings.empty}')
if not holdings.empty:
    print(f'Holdings shape: {holdings.shape}')
    print(f'Holdings columns: {holdings.columns.tolist()}')
else:
    # Try manually fetching the XML
    print('\nTrying to fetch XML directly...')
    import requests
    cik_no_lead = str(int(cik))
    acc_no_dashes = accession.replace('-', '')
    
    files_to_try = [
        'primary_doc.xml',
        'form13fInfoTable.xml', 
        'infotable.xml',
        'doc.xml',
        'xslForm13F_X01/primary_doc.xml',
    ]
    
    for filename in files_to_try:
        url = f"https://www.sec.gov/Archives/edgar/data/{cik_no_lead}/{acc_no_dashes}/{filename}"
        print(f'Trying: {url}')
        try:
            r = requests.get(url, headers={'User-Agent': 'test@test.com'}, timeout=10)
            print(f'  Status: {r.status_code}')
            if r.status_code == 200:
                print(f'  Content length: {len(r.content)}')
                print(f'  First 500 chars: {r.text[:500]}')
                break
        except Exception as e:
            print(f'  Error: {e}')
