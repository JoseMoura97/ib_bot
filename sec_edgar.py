"""
SEC EDGAR API Client - Free access to 13F filings
Alternative to premium Quiver 13F subscription using SEC's public API
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import logging
from typing import Optional, Dict, List
import xml.etree.ElementTree as ET

class SECEdgarClient:
    """Free SEC EDGAR API client for 13F filings and institutional holdings."""
    
    BASE_URL = "https://www.sec.gov"
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) IB-Bot/1.0',
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate'
    }
    
    # Map of fund names to CIK numbers (Central Index Key)
    FUND_CIK_MAP = {
        "Scion Asset Management": "0001649339",
        "Pershing Square Capital Management": "0001336528",
        "Oaktree Capital Management": "0000949509",  # OAKTREE CAPITAL MANAGEMENT LP (106 13F filings)
        "Bill & Melinda Gates Foundation Trust": "0001166559",
        "Bridgewater Associates": "0001350694",
        "Renaissance Technologies": "0001037389",
        "Berkshire Hathaway": "0001067983"
    }
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self._last_request_time = 0
        self._rate_limit_delay = 0.1  # SEC requests 10 requests/second max
    
    def _rate_limit(self):
        """Enforce SEC rate limiting (10 requests per second)."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - time_since_last)
        self._last_request_time = time.time()
    
    def get_cik_by_name(self, fund_name: str) -> Optional[str]:
        """Get CIK number for a fund name."""
        # Check our map first
        if fund_name in self.FUND_CIK_MAP:
            return self.FUND_CIK_MAP[fund_name]
        
        # Try to search SEC database
        try:
            self._rate_limit()
            url = f"{self.BASE_URL}/cgi-bin/browse-edgar"
            params = {
                'company': fund_name,
                'action': 'getcompany',
                'output': 'atom'
            }
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                # Parse XML response to find CIK
                root = ET.fromstring(response.content)
                # Look for CIK in the response
                for entry in root.findall('.//{http://www.w3.org/2005/Atom}entry'):
                    cik_elem = entry.find('.//{http://www.w3.org/2005/Atom}cik')
                    if cik_elem is not None:
                        return cik_elem.text.zfill(10)
        except Exception as e:
            logging.warning(f"Could not find CIK for {fund_name}: {e}")
        
        return None
    
    def get_13f_filings(self, cik: str, limit: int = 4) -> List[Dict]:
        """Get list of 13F filings for a CIK using JSON API."""
        try:
            self._rate_limit()
            
            # Use the data.sec.gov submissions API (more reliable)
            cik_padded = str(cik).zfill(10)
            url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
            
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                logging.error(f"SEC EDGAR returned status {response.status_code}")
                return []
            
            data = response.json()
            
            # Extract recent filings
            filings = []
            recent_filings = data.get('filings', {}).get('recent', {})
            
            if recent_filings:
                forms = recent_filings.get('form', [])
                filing_dates = recent_filings.get('filingDate', [])
                accession_numbers = recent_filings.get('accessionNumber', [])
                
                # Find 13F-HR filings
                for i, form in enumerate(forms):
                    if form == '13F-HR' and len(filings) < limit:
                        filings.append({
                            'filed_date': filing_dates[i],
                            'accession_number': accession_numbers[i],
                            'cik': cik
                        })
            
            return filings
        except Exception as e:
            logging.error(f"Error fetching 13F filings: {e}")
            return []
    
    def parse_13f_holdings(self, cik: str, accession_number: str) -> pd.DataFrame:
        """Parse holdings from a 13F filing."""
        try:
            # Remove dashes from accession number for URL
            acc_no_dashes = accession_number.replace('-', '')
            
            # Construct URL to the filing folder
            cik_no_lead = str(int(cik))  # Remove leading zeros
            base_url = f"https://www.sec.gov/cgi-bin/viewer"
            
            # Try multiple possible filenames for the info table
            possible_files = [
                'primary_doc.xml',
                'form13fInfoTable.xml',
                'infotable.xml',
                'doc.xml'
            ]
            
            for filename in possible_files:
                try:
                    self._rate_limit()
                    url = f"https://www.sec.gov/Archives/edgar/data/{cik_no_lead}/{acc_no_dashes}/{filename}"
                    response = self.session.get(url, timeout=10)
                    
                    if response.status_code == 200:
                        df = self._parse_13f_xml(response.content)
                        if not df.empty:
                            return df
                except Exception as e:
                    continue
        
        except Exception as e:
            logging.error(f"Error parsing 13F holdings: {e}")
        
        return pd.DataFrame()
    
    def _parse_13f_xml(self, xml_content: bytes) -> pd.DataFrame:
        """Parse 13F XML content into DataFrame."""
        try:
            root = ET.fromstring(xml_content)
            
            # Define namespace (SEC 13F uses this)
            ns = {'ns': 'http://www.sec.gov/edgar/document/thirteenf/informationtable'}
            
            holdings = []
            
            # Try with namespace first
            info_tables = root.findall('.//ns:infoTable', ns)
            if not info_tables:
                # Fallback to no namespace
                info_tables = root.findall('.//infoTable')
            
            # Parse all infoTable entries
            for info_table in info_tables:
                holding = {}
                
                # Get name of issuer
                name_elem = info_table.find('.//ns:nameOfIssuer', ns)
                if name_elem is None:
                    name_elem = info_table.find('.//nameOfIssuer')
                if name_elem is not None:
                    holding['Name'] = name_elem.text
                
                # Get ticker/CUSIP
                cusip_elem = info_table.find('.//ns:cusip', ns)
                if cusip_elem is None:
                    cusip_elem = info_table.find('.//cusip')
                if cusip_elem is not None:
                    holding['CUSIP'] = cusip_elem.text
                
                # Get value (in thousands)
                value_elem = info_table.find('.//ns:value', ns)
                if value_elem is None:
                    value_elem = info_table.find('.//value')
                if value_elem is not None:
                    try:
                        holding['Value'] = float(value_elem.text) * 1000  # Convert to dollars
                    except (ValueError, TypeError):
                        pass
                
                # Get shares
                shares_elem = info_table.find('.//ns:sshPrnamt', ns)
                if shares_elem is None:
                    shares_elem = info_table.find('.//sshPrnamt')
                if shares_elem is not None:
                    try:
                        holding['Shares'] = float(shares_elem.text)
                    except (ValueError, TypeError):
                        pass
                
                # Get share type
                type_elem = info_table.find('.//ns:sshPrnamtType', ns)
                if type_elem is None:
                    type_elem = info_table.find('.//sshPrnamtType')
                if type_elem is not None:
                    holding['ShareType'] = type_elem.text
                
                if holding and 'Name' in holding:
                    holdings.append(holding)
            
            if holdings:
                df = pd.DataFrame(holdings)
                
                # Try to add tickers using CUSIP lookup
                if 'CUSIP' in df.columns:
                    df['Ticker'] = df['CUSIP'].apply(self._cusip_to_ticker)
                
                # Also try to extract tickers from names
                if 'Name' in df.columns:
                    extracted_tickers = self._extract_tickers_from_names(df['Name'].tolist())
                    df['TickerFromName'] = extracted_tickers
                    
                    # Fill in missing tickers
                    if 'Ticker' in df.columns:
                        df['Ticker'] = df['Ticker'].fillna(df['TickerFromName'])
                    else:
                        df['Ticker'] = df['TickerFromName']
                
                return df
        
        except Exception as e:
            logging.error(f"Error parsing XML: {e}")
            import traceback
            logging.error(traceback.format_exc())
        
        return pd.DataFrame()
    
    def _cusip_to_ticker(self, cusip: str) -> Optional[str]:
        """Convert CUSIP to ticker symbol using comprehensive mapping."""
        # Comprehensive CUSIP to ticker mapping for common stocks
        cusip_map = {
            # Tech
            '037833100': 'AAPL',   # Apple
            '594918104': 'MSFT',   # Microsoft
            '023135106': 'AMZN',   # Amazon
            '02079K305': 'GOOGL',  # Alphabet A
            '02079K107': 'GOOG',   # Alphabet C
            '30303M102': 'META',   # Meta
            '88160R101': 'TSLA',   # Tesla
            '67066G104': 'NVDA',   # Nvidia
            '17275R102': 'CSCO',   # Cisco
            '68389X105': 'ORCL',   # Oracle
            '02364J107': 'AMD',    # AMD
            '91912E105': 'V',      # Visa
            '57636Q104': 'MA',     # Mastercard
            '98850P109': 'NFLX',   # Netflix
            '00724F101': 'ADBE',   # Adobe
            '172967424': 'CRM',    # Salesforce
            '30231G102': 'EXPE',   # Expedia
            '46120E102': 'INTC',   # Intel
            '46625H100': 'JPM',    # JPMorgan
            '025816109': 'AMEX',   # American Express
            '24906P109': 'GS',     # Goldman Sachs
            '06652K103': 'BAC',    # Bank of America
            '14448C104': 'CAT',    # Caterpillar
            '191216100': 'KO',     # Coca-Cola
            '742718109': 'PG',     # Procter & Gamble
            '90353T100': 'UNH',    # UnitedHealth
            '437076102': 'HD',     # Home Depot
            '717081103': 'PFE',    # Pfizer
            '478160104': 'JNJ',    # Johnson & Johnson
            '084670702': 'BRK.B',  # Berkshire Hathaway B
            '084670108': 'BRK.A',  # Berkshire Hathaway A
            '931142103': 'WMT',    # Walmart
            '037833AK47': 'AAPL',  # Apple (alt)
            '594918AH62': 'MSFT',  # Microsoft (alt)
            '278642103': 'EBAY',   # eBay
            '81762P102': 'SHOP',   # Shopify
            '88579Y101': 'TSMC',   # Taiwan Semi (ADR)
            '459200101': 'IBM',    # IBM
            '68389X105': 'ORCL',   # Oracle
            '747525103': 'QCOM',   # Qualcomm
            '911312106': 'TXN',    # Texas Instruments
            '594918104': 'MSFT',   # Microsoft
            '070858107': 'BABA',   # Alibaba
            '92826C839': 'VIAC',   # ViacomCBS
            '302130109': 'T',      # AT&T
            '92343V104': 'VZ',     # Verizon
            '191216100': 'KO',     # Coca-Cola
            '713448108': 'PEP',    # PepsiCo
            '88579Y101': 'TSM',    # Taiwan Semi
            '032095101': 'AMGN',   # Amgen
            '126650100': 'CVS',    # CVS Health
            '02376R102': 'AAL',    # American Airlines
            '247361702': 'DAL',    # Delta
            '844741108': 'SBUX',   # Starbucks
            '58933Y105': 'MCD',    # McDonald's
            '931142103': 'WMT',    # Walmart
            '918204108': 'ULTA',   # Ulta Beauty
            '594918104': 'MSFT',   # Microsoft
            # Actual holdings from 13F filings
            '116794207': 'BRKR',   # Bruker Corp (preferred)
            '406216101': 'HAL',    # Halliburton
            '550021109': 'LULU',   # Lululemon
            '69608A108': 'PLTR',   # Palantir
            '90353T100': 'UNH',    # UnitedHealth
            '903724107': 'UBER',   # Uber Technologies
            '112585104': 'BN',     # Brookfield
            '443669107': 'HHH',    # Howard Hughes
            '024382104': 'AMZN',   # Amazon
            '169656105': 'CMG',    # Chipotle
            '76169C102': 'QSR',    # Restaurant Brands
            '02079K107': 'GOOGL',  # Alphabet
            '43300A203': 'HLT',    # Hilton
            '428291108': 'HTZ',    # Hertz
            '606496204': 'MOH',    # Molina Healthcare
            '829224107': 'SLM',    # SLM Corp
        }
        
        # Try direct lookup
        if cusip in cusip_map:
            return cusip_map[cusip]
        
        # Try with first 9 characters (base CUSIP)
        base_cusip = cusip[:9] if len(cusip) > 9 else cusip
        if base_cusip in cusip_map:
            return cusip_map[base_cusip]
        
        return None
    
    def get_latest_holdings(self, fund_name: str) -> pd.DataFrame:
        """Get the most recent 13F holdings for a fund."""
        # Get CIK
        cik = self.get_cik_by_name(fund_name)
        if not cik:
            logging.error(f"Could not find CIK for {fund_name}")
            return pd.DataFrame()
        
        # Get recent filings
        filings = self.get_13f_filings(cik, limit=1)
        if not filings:
            logging.error(f"No 13F filings found for {fund_name}")
            return pd.DataFrame()
        
        # Parse the most recent filing
        latest_filing = filings[0]
        holdings = self.parse_13f_holdings(cik, latest_filing['accession_number'])
        
        if not holdings.empty:
            holdings['FilingDate'] = latest_filing['filed_date']
            holdings['Fund'] = fund_name
        
        return holdings

    def get_holdings_as_of_date(self, fund_name: str, as_of_date: datetime, search_limit: int = 40) -> pd.DataFrame:
        """
        Get the latest 13F holdings *known as of* a given date.

        This is used for backtests/replication (time travel):
        pick the most recent 13F-HR filing with filed_date <= as_of_date.

        Notes:
        - 13F filings are quarterly and reported with a lag; this method uses filed_date
          (not the quarter end) as the "known" timestamp.
        """
        try:
            if not isinstance(as_of_date, datetime):
                as_of_date = pd.to_datetime(as_of_date).to_pydatetime()
        except Exception:
            as_of_date = datetime.now()

        cik = self.get_cik_by_name(fund_name)
        if not cik:
            logging.error(f"Could not find CIK for {fund_name}")
            return pd.DataFrame()

        filings = self.get_13f_filings(cik, limit=search_limit)
        if not filings:
            return pd.DataFrame()

        chosen = None
        for f in filings:
            fd = f.get("filed_date")
            try:
                fdt = datetime.fromisoformat(fd)
            except Exception:
                continue
            if fdt <= as_of_date:
                if chosen is None:
                    chosen = f
                else:
                    try:
                        chosen_dt = datetime.fromisoformat(chosen.get("filed_date"))
                        if fdt > chosen_dt:
                            chosen = f
                    except Exception:
                        chosen = f

        if chosen is None:
            # No filing existed yet as-of-date
            return pd.DataFrame()

        holdings = self.parse_13f_holdings(cik, chosen["accession_number"])
        if not holdings.empty:
            holdings["FilingDate"] = chosen.get("filed_date")
            holdings["Fund"] = fund_name
        return holdings
    
    def get_holdings_history(self, fund_name: str, num_quarters: int = 4) -> pd.DataFrame:
        """Get historical 13F holdings for multiple quarters."""
        # Get CIK
        cik = self.get_cik_by_name(fund_name)
        if not cik:
            logging.error(f"Could not find CIK for {fund_name}")
            return pd.DataFrame()
        
        # Get recent filings
        filings = self.get_13f_filings(cik, limit=num_quarters)
        if not filings:
            logging.error(f"No 13F filings found for {fund_name}")
            return pd.DataFrame()
        
        # Parse all filings
        all_holdings = []
        for filing in filings:
            holdings = self.parse_13f_holdings(cik, filing['accession_number'])
            if not holdings.empty:
                holdings['FilingDate'] = filing['filed_date']
                holdings['Fund'] = fund_name
                all_holdings.append(holdings)
        
        if all_holdings:
            return pd.concat(all_holdings, ignore_index=True)
        
        return pd.DataFrame()
    
    def get_top_holdings(self, fund_name: str, top_n: int = 10) -> List[str]:
        """Get top N holdings by value for a fund."""
        holdings = self.get_latest_holdings(fund_name)
        
        if holdings.empty:
            return []
        
        # Sort by value and get top N
        if 'Value' in holdings.columns:
            top_holdings = holdings.nlargest(top_n, 'Value')
            
            # Return tickers if available, otherwise names
            if 'Ticker' in top_holdings.columns and not top_holdings['Ticker'].isna().all():
                return top_holdings['Ticker'].dropna().tolist()
            elif 'Name' in top_holdings.columns:
                # Try to extract ticker-like strings from names
                return self._extract_tickers_from_names(top_holdings['Name'].tolist())
        
        return []
    
    def _extract_tickers_from_names(self, names: List[str]) -> List[str]:
        """Try to extract ticker symbols from company names."""
        # Comprehensive company name to ticker mapping
        name_map = {
            'APPLE': 'AAPL',
            'MICROSOFT': 'MSFT',
            'AMAZON': 'AMZN',
            'ALPHABET': 'GOOGL',
            'GOOGLE': 'GOOGL',
            'META PLATFORMS': 'META',
            'FACEBOOK': 'META',
            'TESLA': 'TSLA',
            'NVIDIA': 'NVDA',
            'BERKSHIRE HATHAWAY': 'BRK.B',
            'JPMORGAN': 'JPM',
            'JP MORGAN': 'JPM',
            'JOHNSON & JOHNSON': 'JNJ',
            'JOHNSON AND JOHNSON': 'JNJ',
            'VISA': 'V',
            'PROCTER & GAMBLE': 'PG',
            'PROCTER AND GAMBLE': 'PG',
            'UNITEDHEALTH': 'UNH',
            'UNITED HEALTH': 'UNH',
            'HOME DEPOT': 'HD',
            'MASTERCARD': 'MA',
            'PFIZER': 'PFE',
            'WALMART': 'WMT',
            'COCA-COLA': 'KO',
            'COCA COLA': 'KO',
            'PEPSICO': 'PEP',
            'PEPSI': 'PEP',
            'NETFLIX': 'NFLX',
            'ADOBE': 'ADBE',
            'CISCO': 'CSCO',
            'ORACLE': 'ORCL',
            'INTEL': 'INTC',
            'AMD': 'AMD',
            'ADVANCED MICRO DEVICES': 'AMD',
            'SALESFORCE': 'CRM',
            'BANK OF AMERICA': 'BAC',
            'GOLDMAN SACHS': 'GS',
            'AMERICAN EXPRESS': 'AXP',
            'CATERPILLAR': 'CAT',
            'BOEING': 'BA',
            'CHEVRON': 'CVX',
            'EXXON': 'XOM',
            'AT&T': 'T',
            'VERIZON': 'VZ',
            'COMCAST': 'CMCSA',
            'DISNEY': 'DIS',
            'MCDONALD': 'MCD',
            'STARBUCKS': 'SBUX',
            'NIKE': 'NKE',
            'IBM': 'IBM',
            'QUALCOMM': 'QCOM',
            'TEXAS INSTRUMENTS': 'TXN',
            'BROADCOM': 'AVGO',
            'ALIBABA': 'BABA',
            'TAIWAN SEMICONDUCTOR': 'TSM',
            'AMGEN': 'AMGN',
            'CVS': 'CVS',
            'ABBVIE': 'ABBV',
            'ELI LILLY': 'LLY',
            'MERCK': 'MRK',
            'BRISTOL-MYERS': 'BMY',
            'BRISTOL MYERS': 'BMY',
            'THERMO FISHER': 'TMO',
            'DANAHER': 'DHR',
            'COSTCO': 'COST',
            'TARGET': 'TGT',
            'LOWE': 'LOW',
            'DELTA': 'DAL',
            'AMERICAN AIRLINES': 'AAL',
            'UNITED AIRLINES': 'UAL',
            'SOUTHWEST': 'LUV',
            'GENERAL ELECTRIC': 'GE',
            'GENERAL MOTORS': 'GM',
            'FORD': 'F',
            '3M': 'MMM',
            'HONEYWELL': 'HON',
            'RAYTHEON': 'RTX',
            'LOCKHEED MARTIN': 'LMT',
            'NORTHROP GRUMMAN': 'NOC',
            # From actual 13F filings
            'PALANTIR': 'PLTR',
            'UBER TECHNOLOGIES': 'UBER',
            'UBER': 'UBER',
            'LULULEMON': 'LULU',
            'HALLIBURTON': 'HAL',
            'BRUKER': 'BRKR',
            'BROOKFIELD': 'BN',
            'HOWARD HUGHES': 'HHH',
            'CHIPOTLE': 'CMG',
            'RESTAURANT BRANDS': 'QSR',
            'HILTON': 'HLT',
            'HERTZ': 'HTZ',
            'MOLINA HEALTHCARE': 'MOH',
            'PFIZER': 'PFE',
            'SLM CORP': 'SLM',
            'SALLIE MAE': 'SLM',
        }
        
        tickers = []
        for name in names:
            if not name:
                continue
            
            name_upper = name.upper().strip()
            ticker_found = False
            
            # Try direct match first
            if name_upper in name_map:
                tickers.append(name_map[name_upper])
                ticker_found = True
            else:
                # Try partial matches
                for key, ticker in name_map.items():
                    if key in name_upper:
                        tickers.append(ticker)
                        ticker_found = True
                        break
            
            # If no match found, keep the original name
            if not ticker_found:
                tickers.append(name[:10])  # Truncate long names
        
        return tickers


# Convenience function
def get_fund_holdings(fund_name: str, top_n: int = None) -> pd.DataFrame:
    """Quick function to get fund holdings."""
    client = SECEdgarClient()
    holdings = client.get_latest_holdings(fund_name)
    
    if not holdings.empty and top_n:
        if 'Value' in holdings.columns:
            holdings = holdings.nlargest(top_n, 'Value')
    
    return holdings
