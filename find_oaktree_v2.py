"""Find the actual holdings XML file for Oaktree using SEC API."""
import requests
import json

cik = '0000949509'
cik_no_lead = '949509'
accession = '0000949509-25-000007'
acc_no_dashes = accession.replace('-', '')

# Get the filing index JSON
index_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=13F-HR&dateb=&owner=include&count=1&output=atom"
print(f"Checking filing info...")

# Try the document index
doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik_no_lead}/{acc_no_dashes}/index.json"
print(f"\nTrying: {doc_url}")

r = requests.get(doc_url, headers={'User-Agent': 'test@test.com'}, timeout=10)
print(f"Status: {r.status_code}")

if r.status_code == 200:
    data = r.json()
    print(json.dumps(data, indent=2)[:2000])
else:
    # Try without leading zeros in CIK
    # Also try the -index.htm file
    htm_url = f"https://www.sec.gov/Archives/edgar/data/{cik_no_lead}/{acc_no_dashes}/{acc_no_dashes}-index.htm"
    print(f"\nTrying: {htm_url}")
    r2 = requests.get(htm_url, headers={'User-Agent': 'test@test.com'}, timeout=10)
    print(f"Status: {r2.status_code}")
    if r2.status_code == 200:
        # Look for XML files
        import re
        xml_files = re.findall(r'href="([^"]+\.xml)"', r2.text)
        print(f"XML files found: {xml_files}")
        
        for xml_file in xml_files:
            if 'table' in xml_file.lower() or 'info' in xml_file.lower():
                file_url = f"https://www.sec.gov/Archives/edgar/data/{cik_no_lead}/{acc_no_dashes}/{xml_file}"
                print(f"\nFetching: {file_url}")
                r3 = requests.get(file_url, headers={'User-Agent': 'test@test.com'}, timeout=10)
                print(f"Status: {r3.status_code}, Content: {r3.text[:500]}")
