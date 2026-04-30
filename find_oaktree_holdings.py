"""Find the actual holdings XML file for Oaktree."""
import requests
from bs4 import BeautifulSoup

cik = '949509'
accession = '0000949509-25-000007'
acc_no_dashes = accession.replace('-', '')

# Get the filing index
index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no_dashes}/"
print(f"Checking: {index_url}")

r = requests.get(index_url, headers={'User-Agent': 'test@test.com'}, timeout=10)
print(f"Status: {r.status_code}")

if r.status_code == 200:
    soup = BeautifulSoup(r.text, 'html.parser')
    # Find all links
    links = soup.find_all('a')
    print(f"\nFiles in folder:")
    for link in links:
        href = link.get('href', '')
        if href and not href.startswith('?') and not href.startswith('/'):
            print(f"  {href}")
    
    # Try to find the info table
    print("\nLooking for info table XML...")
    for link in links:
        href = link.get('href', '')
        if 'infotable' in href.lower() or 'table' in href.lower():
            print(f"  Found: {href}")
            # Fetch it
            file_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no_dashes}/{href}"
            r2 = requests.get(file_url, headers={'User-Agent': 'test@test.com'}, timeout=10)
            if r2.status_code == 200:
                print(f"  Content: {r2.text[:1000]}")
