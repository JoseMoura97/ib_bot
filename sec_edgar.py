"""
SEC EDGAR API Client - Free access to 13F filings
Alternative to premium Quiver 13F subscription using SEC's public API
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import logging
import os
import json
from typing import Optional, Dict, List
import xml.etree.ElementTree as ET
import re

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

        # Persistent cache (survives container restarts if .cache is volume-mounted)
        self._cache_dir = os.path.join(os.path.dirname(__file__), ".cache", "sec_edgar")
        os.makedirs(self._cache_dir, exist_ok=True)
        self._cusip_ticker_cache_path = os.path.join(self._cache_dir, "cusip_ticker_cache.json")
        self._cusip_ticker_cache: Dict[str, str] = {}
        self._load_cusip_ticker_cache()

    def _load_cusip_ticker_cache(self) -> None:
        try:
            if os.path.exists(self._cusip_ticker_cache_path):
                with open(self._cusip_ticker_cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    # normalize keys (CUSIPs) to stripped strings
                    self._cusip_ticker_cache = {str(k).strip(): str(v).strip() for k, v in data.items() if v}
        except Exception:
            self._cusip_ticker_cache = {}

    def _save_cusip_ticker_cache(self) -> None:
        try:
            with open(self._cusip_ticker_cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cusip_ticker_cache, f, indent=2, sort_keys=True)
        except Exception:
            pass

    @staticmethod
    def _is_valid_ticker(t: Optional[str]) -> bool:
        """
        Basic sanity check for US tickers.
        Allows letters/digits plus '.' and '-' (e.g., BRK.B, BF-A).
        """
        if not t:
            return False
        s = str(t).strip().upper()
        if len(s) < 1 or len(s) > 10:
            return False
        return re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]*", s) is not None

    def _openfigi_map_cusip_to_ticker(self, cusip: str) -> Optional[str]:
        """
        Use OpenFIGI to map CUSIP -> ticker.
        Works with or without API key (rate-limited for anonymous access).
        """
        api_key = os.environ.get("OPENFIGI_API_KEY", "").strip()
        try:
            url = "https://api.openfigi.com/v3/mapping"
            headers = {
                "Content-Type": "application/json",
            }
            if api_key:
                headers["X-OPENFIGI-APIKEY"] = api_key
            
            # Clean CUSIP - use first 9 chars (base CUSIP) for equity lookup
            clean_cusip = str(cusip).strip()[:9]
            
            # Try US equity mapping. OpenFIGI accepts list payloads.
            payload = [
                {"idType": "ID_CUSIP", "idValue": clean_cusip, "exchCode": "US"},
            ]
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            if resp.status_code == 429:
                # Rate limited - wait and don't cache miss
                logging.debug(f"OpenFIGI rate limited for CUSIP {cusip}")
                return None
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not isinstance(data, list) or not data:
                return None
            # Each element is { "data": [ { "ticker": "...", ... } ], "error": ... }
            item = data[0] if isinstance(data[0], dict) else {}
            rows = item.get("data") if isinstance(item, dict) else None
            if isinstance(rows, list) and rows:
                # Prefer common stock over other security types
                for row in rows:
                    sec_type = row.get("securityType", "")
                    if sec_type in ("Common Stock", "COMMON STOCK", "Depositary Receipt"):
                        ticker = row.get("ticker")
                        if self._is_valid_ticker(ticker):
                            return str(ticker).upper()
                # Fallback to first valid ticker
                ticker = rows[0].get("ticker")
                if self._is_valid_ticker(ticker):
                    return str(ticker).upper()
        except Exception as e:
            logging.debug(f"OpenFIGI lookup failed for CUSIP {cusip}: {e}")
            return None
        return None

    def _cache_path_filings(self, cik: str) -> str:
        safe = str(cik).strip().zfill(10)
        return os.path.join(self._cache_dir, f"filings_CIK{safe}.json")

    def _cache_path_holdings(self, cik: str, accession_number: str) -> str:
        safe_cik = str(cik).strip().zfill(10)
        safe_acc = str(accession_number).strip().replace("-", "")
        return os.path.join(self._cache_dir, f"holdings_CIK{safe_cik}_{safe_acc}.pkl")

    @staticmethod
    def _is_cache_fresh(path: str, max_age_seconds: float) -> bool:
        try:
            if not os.path.exists(path):
                return False
            age = time.time() - os.path.getmtime(path)
            return age <= float(max_age_seconds)
        except Exception:
            return False
    
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
            # Prefer cache to reduce SEC load / rate-limit issues.
            cache_path = self._cache_path_filings(cik)
            if self._is_cache_fresh(cache_path, max_age_seconds=12 * 3600):
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                    if isinstance(cached, list):
                        return cached[: int(limit)]
                except Exception:
                    pass

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

            # Cache full list (even if empty) to smooth repeat calls.
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(filings, f)
            except Exception:
                pass

            return filings
        except Exception as e:
            logging.error(f"Error fetching 13F filings: {e}")
            return []
    
    def parse_13f_holdings(self, cik: str, accession_number: str) -> pd.DataFrame:
        """Parse holdings from a 13F filing."""
        try:
            cache_path = self._cache_path_holdings(cik, accession_number)
            if self._is_cache_fresh(cache_path, max_age_seconds=30 * 24 * 3600):
                try:
                    df = pd.read_pickle(cache_path)
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        return df
                except Exception:
                    pass

            # Remove dashes from accession number for URL
            acc_no_dashes = accession_number.replace('-', '')
            
            # Construct URL to the filing folder
            cik_no_lead = str(int(cik))  # Remove leading zeros
            base_folder = f"https://www.sec.gov/Archives/edgar/data/{cik_no_lead}/{acc_no_dashes}"
            
            # First, check the index.json to find the actual info table XML file
            # Some funds use custom names like "13F_OCMLP_3Q2025.xml"
            possible_files = []
            try:
                self._rate_limit()
                index_url = f"{base_folder}/index.json"
                idx_response = self.session.get(index_url, timeout=10)
                if idx_response.status_code == 200:
                    idx_data = idx_response.json()
                    items = idx_data.get("directory", {}).get("item", [])
                    for item in items:
                        name = item.get("name", "")
                        size = item.get("size", "0")
                        # Look for large XML files (likely the info table)
                        # Skip primary_doc.xml (cover page) and index files
                        if name.endswith(".xml") and name != "primary_doc.xml":
                            try:
                                if int(size) > 5000:  # Info tables are usually > 5KB
                                    possible_files.insert(0, name)  # Prioritize large files
                            except (ValueError, TypeError):
                                possible_files.append(name)
            except Exception:
                pass
            
            # Fallback to common filenames if index.json didn't help
            possible_files.extend([
                'form13fInfoTable.xml',
                'infotable.xml',
                'doc.xml',
                'primary_doc.xml'  # Last resort
            ])
            
            for filename in possible_files:
                try:
                    self._rate_limit()
                    url = f"{base_folder}/{filename}"
                    response = self.session.get(url, timeout=10)
                    
                    if response.status_code == 200:
                        df = self._parse_13f_xml(response.content)
                        if not df.empty:
                            try:
                                df.to_pickle(cache_path)
                            except Exception:
                                pass
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
                        # SEC 13F values are reported in dollars (not thousands)
                        holding['Value'] = float(value_elem.text)
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
                
                # Get putCall (for options - PUT or CALL)
                put_call_elem = info_table.find('.//ns:putCall', ns)
                if put_call_elem is None:
                    put_call_elem = info_table.find('.//putCall')
                if put_call_elem is not None:
                    holding['PutCall'] = put_call_elem.text  # 'Put' or 'Call'
                
                # Get titleOfClass to detect preferred shares
                title_elem = info_table.find('.//ns:titleOfClass', ns)
                if title_elem is None:
                    title_elem = info_table.find('.//titleOfClass')
                if title_elem is not None:
                    holding['TitleOfClass'] = title_elem.text
                
                if holding and 'Name' in holding:
                    holdings.append(holding)
            
            if holdings:
                df = pd.DataFrame(holdings)
                
                # Handle options based on include_options mode
                # Mode is controlled by environment variable or can be set programmatically
                # Default to stock-only for accuracy:
                # - 13F option rows lack strike/expiry, so any delta mapping is heuristic.
                # - If you want an approximation of directional exposure, set:
                #   SEC_13F_OPTIONS_MODE=delta_adjusted (and optionally SEC_13F_PUT_DELTA / SEC_13F_CALL_DELTA)
                include_options_mode = os.environ.get('SEC_13F_OPTIONS_MODE', 'filter')
                # Options modes:
                # - 'filter': Remove all options (conservative)
                # - 'as_exposure': Treat PUT as 100% SHORT, CALL as 100% LONG
                # - 'delta_adjusted': Treat PUT as ~40% SHORT, CALL as ~40% LONG (default, most accurate)
                # - 'include': Include options as-is (legacy behavior, WRONG)
                
                # Delta estimates for options (since 13F doesn't include strike/expiration)
                # These are typical deltas for at-the-money options
                PUT_DELTA = float(os.environ.get('SEC_13F_PUT_DELTA', '0.40'))   # 40% short exposure
                CALL_DELTA = float(os.environ.get('SEC_13F_CALL_DELTA', '0.40')) # 40% long exposure
                
                if 'PutCall' in df.columns:
                    options_mask = df['PutCall'].notna()
                    options_count = options_mask.sum()
                    
                    if include_options_mode == 'delta_adjusted' and options_count > 0:
                        # Delta-adjusted exposure:
                        # - CALL = CALL_DELTA * value (partial long exposure)
                        # - PUT = -PUT_DELTA * value (partial short exposure)
                        logging.info(f"Converting {options_count} options to delta-adjusted exposure (PUT={PUT_DELTA}x SHORT, CALL={CALL_DELTA}x LONG)")
                        
                        put_mask = df['PutCall'].str.upper() == 'PUT'
                        call_mask = df['PutCall'].str.upper() == 'CALL'
                        
                        if 'Value' in df.columns:
                            # PUT: negative value * delta (short exposure)
                            df.loc[put_mask, 'Value'] = -df.loc[put_mask, 'Value'].abs() * PUT_DELTA
                            # CALL: positive value * delta (long exposure)
                            df.loc[call_mask, 'Value'] = df.loc[call_mask, 'Value'].abs() * CALL_DELTA
                        
                        df['ExposureType'] = 'LONG'
                        df.loc[put_mask, 'ExposureType'] = 'SHORT'
                        df['Delta'] = 1.0  # Stock positions
                        df.loc[put_mask, 'Delta'] = -PUT_DELTA
                        df.loc[call_mask, 'Delta'] = CALL_DELTA
                        
                    elif include_options_mode == 'as_exposure' and options_count > 0:
                        # Full 100% exposure (PUT = 100% SHORT, CALL = 100% LONG)
                        logging.info(f"Converting {options_count} options to full exposure (PUT=100% SHORT, CALL=100% LONG)")
                        
                        put_mask = df['PutCall'].str.upper() == 'PUT'
                        if 'Value' in df.columns:
                            df.loc[put_mask, 'Value'] = -df.loc[put_mask, 'Value'].abs()
                        
                        df['ExposureType'] = 'LONG'
                        df.loc[put_mask, 'ExposureType'] = 'SHORT'
                        
                    elif include_options_mode == 'filter' and options_count > 0:
                        # Remove all options
                        logging.info(f"Filtering out {options_count} option positions (PUT/CALL)")
                        df = df[~options_mask]
                    # else 'include': keep options as-is (legacy)
                
                # Filter out preferred shares (typically have different price behavior)
                if 'TitleOfClass' in df.columns:
                    # Keep only common stock (COM, CL A, CL B, etc.) not PREF
                    pref_mask = df['TitleOfClass'].str.upper().str.contains('PREF|PREFERRED', na=False)
                    pref_count = pref_mask.sum()
                    if pref_count > 0:
                        logging.info(f"Filtering out {pref_count} preferred share positions")
                    df = df[~pref_mask]
                
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
        if not cusip:
            return None
        cusip = str(cusip).strip()

        # 1) Check persistent cache first (user-extendable, and filled by OpenFIGI if enabled).
        cached = self._cusip_ticker_cache.get(cusip)
        if cached and self._is_valid_ticker(cached):
            return str(cached).upper()

        # Comprehensive CUSIP to ticker mapping for common stocks
        cusip_map = {
            # Tech Giants
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
            '025816109': 'AXP',    # American Express
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
            '278642103': 'EBAY',   # eBay
            '81762P102': 'SHOP',   # Shopify
            '88579Y101': 'TSM',    # Taiwan Semi (ADR)
            '459200101': 'IBM',    # IBM
            '747525103': 'QCOM',   # Qualcomm
            '911312106': 'TXN',    # Texas Instruments
            '070858107': 'BABA',   # Alibaba
            '92826C839': 'PARA',   # Paramount (was ViacomCBS)
            '302130109': 'T',      # AT&T
            '92343V104': 'VZ',     # Verizon
            '713448108': 'PEP',    # PepsiCo
            '032095101': 'AMGN',   # Amgen
            '126650100': 'CVS',    # CVS Health
            '02376R102': 'AAL',    # American Airlines
            '247361702': 'DAL',    # Delta
            '844741108': 'SBUX',   # Starbucks
            '58933Y105': 'MCD',    # McDonald's
            '918204108': 'ULTA',   # Ulta Beauty
            # From 13F filings - hedge fund holdings
            '116794207': 'BRKR',   # Bruker Corp
            '406216101': 'HAL',    # Halliburton
            '550021109': 'LULU',   # Lululemon
            '69608A108': 'PLTR',   # Palantir
            '903724107': 'UBER',   # Uber Technologies
            '112585104': 'BN',     # Brookfield
            '443669107': 'HHH',    # Howard Hughes
            '024382104': 'AMZN',   # Amazon
            '169656105': 'CMG',    # Chipotle
            '76169C102': 'QSR',    # Restaurant Brands
            '43300A203': 'HLT',    # Hilton
            '428291108': 'HTZ',    # Hertz
            '606496204': 'MOH',    # Molina Healthcare
            '829224107': 'SLM',    # SLM Corp
            # Oaktree Capital Holdings (Howard Marks)
            '87266J104': 'TPIC',   # TPI Composites
            '09075P204': 'BTAI',   # BioXcel Therapeutics
            '30050B101': 'EVH',    # Evolent Health
            '33835L104': 'FVRR',   # Fiverr International
            '893870203': 'TGS',    # Transportadora de Gas del Sur
            '450056106': 'IRTC',   # iRhythm Technologies
            '31188V100': 'FSLY',   # Fastly
            '98975W100': 'ZD',     # Ziff Davis
            '70614W100': 'PTON',   # Peloton
            '04351P101': 'ASND',   # Ascendis Pharma
            '94419L101': 'W',      # Wayfair
            '55087P104': 'LYFT',   # Lyft
            '737446104': 'POST',   # Post Holdings
            '08265T108': 'BSY',    # Bentley Systems
            '25402D102': 'DOCN',   # DigitalOcean
            '83304A106': 'SNAP',   # Snap Inc
            '29664W105': 'ESPR',   # Esperion Therapeutics
            '682189105': 'ON',     # ON Semiconductor
            '399473107': 'GRPN',   # Groupon
            '10806X102': 'BBIO',   # BridgeBio Pharma
            '42703M102': 'HLF',    # Herbalife
            '74736L109': 'QTWO',   # Q2 Holdings
            '852234103': 'SQ',     # Block Inc (Square)
            '090043102': 'BILL',   # BILL Holdings
            '156727103': 'CRNC',   # Cerence
            '64049M108': 'NEO',    # NeoGenomics
            '91332U101': 'U',      # Unity Software
            '401617105': 'GES',    # Guess Inc
            '07134L107': 'BATL',   # Battalion Oil
            '90187B109': 'TWO',    # Two Harbors Investment
            '00827B106': 'AFRM',   # Affirm Holdings
            '67011X109': 'NVCR',   # Novocure
            '13118K108': 'MODG',   # Topgolf Callaway (was MODG)
            '974637100': 'WGO',    # Winnebago Industries
            '40131M109': 'GH',     # Guardant Health
            '35953D107': 'FUBO',   # fuboTV
            '91688F108': 'UPWK',   # Upwork
            '92343X100': 'VRNT',   # Verint Systems
            '358039100': 'FRPT',   # Freshpet
            '842587107': 'SO',     # Southern Company
            '40415F101': 'HDB',    # HDFC Bank
            '70932A103': 'PMT',    # PennyMac Mortgage
            '89677Q107': 'TCOM',   # Trip.com
            '758075100': 'RWT',    # Redwood Trust
            '91879Q109': 'MTN',    # Vail Resorts
            '501812107': 'LCII',   # LCI Industries
            '55955D107': 'MGNI',   # Magnite
            '516544103': 'LNTH',   # Lantheus Holdings
            # Pershing Square Holdings (Bill Ackman)
            '43300A104': 'HLT',    # Hilton Worldwide
            '45168D104': 'HHH',    # Howard Hughes Holdings
            '112585104': 'BN',     # Brookfield Corp
            # Scion Asset Management (Michael Burry)
            '070500105': 'BAP',    # Credicorp
            '031162100': 'AMKR',   # Amkor Technology
            '04316A108': 'ARRY',   # Array Technologies
            '05351W103': 'AXTA',   # Axalta Coating Systems
            '29080A104': 'EMN',    # Eastman Chemical
            '30303M102': 'META',   # Meta Platforms
            '34959E109': 'FROG',   # JFrog
            '37959E102': 'GLOB',   # Globant
            '40049J206': 'GTLB',   # GitLab
            '42251A104': 'HCP',    # HashiCorp
            '45867R105': 'ICU',    # SeaStar Medical
            '46128T105': 'IOT',    # Samsara
            '49271V100': 'KEYS',   # Keysight Technologies
            '52736R102': 'LECO',   # Lincoln Electric
            '55087P104': 'LYFT',   # Lyft
            '59522J103': 'MIDD',   # Middleby Corp
            '624756102': 'MUSA',   # Murphy USA
            '629482107': 'NBIX',   # Neurocrine Biosciences
            '63946M104': 'NSA',    # National Storage Affiliates
            '65339F101': 'NI',     # NiSource
            '655664100': 'NKE',    # Nike
            '67066G104': 'NVDA',   # Nvidia
            '68902V107': 'OSW',    # OneSpaWorld
            '69349H107': 'PBH',    # Prestige Consumer Healthcare
            '70060P107': 'PARR',   # Par Pacific Holdings
            '72814L108': 'PKG',    # Packaging Corp of America
            '74758T303': 'QRVO',   # Qorvo
            '756109104': 'REG',    # Regency Centers
            '78409V104': 'SPG',    # Simon Property Group
            '78467J100': 'STX',    # Seagate Technology
            '80105N105': 'SANM',   # Sanmina
            '82480R100': 'SHEL',   # Shell PLC
            '82968B103': 'SIGI',   # Selective Insurance
            '843646104': 'SXI',    # Standex International
            '85254J102': 'STAG',   # STAG Industrial
            '87612E106': 'TDC',    # Teradata
            '88076W103': 'TER',    # Teradyne
            '88826T102': 'THS',    # TreeHouse Foods
            '89236T109': 'TSEM',   # Tower Semiconductor
            '896239100': 'TT',     # Trane Technologies
            '90353T100': 'UNH',    # UnitedHealth
            '90384S303': 'UBER',   # Uber
            '91325V108': 'UDR',    # UDR Inc
            '92343E102': 'VFC',    # VF Corp
            '92345Y106': 'VMC',    # Vulcan Materials
            '92553P201': 'VIPS',   # Vipshop
            '92763W103': 'VSAT',   # Viasat
            '929903102': 'WBA',    # Walgreens Boots Alliance
            '93114W100': 'WAB',    # Wabtec Corp
            '94106L109': 'WDAY',   # Workday
            '945528109': 'WGO',    # Winnebago
            '94770V102': 'WEN',    # Wendy's
            '96145D105': 'WH',     # Wyndham Hotels
            '98138H101': 'WOR',    # Worthington Industries
            '98419M100': 'XM',     # Qualtrics
            '98422D105': 'XPO',    # XPO Logistics
            '98956P102': 'ZBH',    # Zimmer Biomet
        }
        
        # Try direct lookup
        if cusip in cusip_map:
            return cusip_map[cusip]
        
        # Try with first 9 characters (base CUSIP)
        base_cusip = cusip[:9] if len(cusip) > 9 else cusip
        if base_cusip in cusip_map:
            return cusip_map[base_cusip]
        
        # Issuer code (6 char) to ticker mapping for convertibles/bonds
        issuer_map = {
            '037833': 'AAPL',   # Apple
            '594918': 'MSFT',   # Microsoft
            '023135': 'AMZN',   # Amazon
            '02079K': 'GOOGL',  # Alphabet
            '30303M': 'META',   # Meta
            '88160R': 'TSLA',   # Tesla
            '67066G': 'NVDA',   # Nvidia
            '91912E': 'V',      # Visa
            '90353T': 'UBER',   # Uber (important - their conv notes)
            # Oaktree holdings - issuer codes
            '87266J': 'TPIC',   # TPI Composites
            '09075P': 'BTAI',   # BioXcel
            '30050B': 'EVH',    # Evolent Health
            '33835L': 'FVRR',   # Fiverr
            '893870': 'TGS',    # Transportadora de Gas
            '450056': 'IRTC',   # iRhythm
            '31188V': 'FSLY',   # Fastly
            '48123V': 'ZD',     # Ziff Davis
            '70614W': 'PTON',   # Peloton
            '04351P': 'ASND',   # Ascendis
            '94419L': 'W',      # Wayfair
            '55087P': 'LYFT',   # Lyft
            '737446': 'POST',   # Post Holdings
            '08265T': 'BSY',    # Bentley Systems
            '25402D': 'DOCN',   # DigitalOcean
            '83304A': 'SNAP',   # Snap
            '29664W': 'ESPR',   # Esperion
            '682189': 'ON',     # ON Semiconductor
            '399473': 'GRPN',   # Groupon
            '10806X': 'BBIO',   # BridgeBio
            '42703M': 'HLF',    # Herbalife
            '74736L': 'QTWO',   # Q2 Holdings
            '852234': 'SQ',     # Block/Square
            '090043': 'BILL',   # BILL Holdings
            '156727': 'CRNC',   # Cerence
            '64049M': 'NEO',    # NeoGenomics
            '91332U': 'U',      # Unity
            '401617': 'GES',    # Guess
            '07134L': 'BATL',   # Battalion Oil
            '90187B': 'TWO',    # Two Harbors
            '00827B': 'AFRM',   # Affirm
            '67011X': 'NVCR',   # Novocure
            '13118K': 'MODG',   # Topgolf Callaway
            '974637': 'WGO',    # Winnebago
            '40131M': 'GH',     # Guardant Health
            '35953D': 'FUBO',   # fuboTV
            '91688F': 'UPWK',   # Upwork
            '92343X': 'VRNT',   # Verint
            '358039': 'FRPT',   # Freshpet
            '842587': 'SO',     # Southern Company
            '40415F': 'HDB',    # HDFC Bank
            '70932A': 'PMT',    # PennyMac
            '89677Q': 'TCOM',   # Trip.com
            '758075': 'RWT',    # Redwood Trust
            '91879Q': 'MTN',    # Vail Resorts
            '501812': 'LCII',   # LCI Industries
            '55955D': 'MGNI',   # Magnite
            '516544': 'LNTH',   # Lantheus
            '903724': 'UBER',   # Uber Technologies
            # Additional common issuers
            '46625H': 'JPM',    # JPMorgan
            '06652K': 'BAC',    # Bank of America
            '84670B': 'BRK.B',  # Berkshire
            '478160': 'JNJ',    # J&J
            '717081': 'PFE',    # Pfizer
            '17275R': 'CSCO',   # Cisco
            '68389X': 'ORCL',   # Oracle
            '713448': 'PEP',    # PepsiCo
            '191216': 'KO',     # Coca-Cola
            '931142': 'WMT',    # Walmart
        }
        
        # For bond/convertible CUSIPs (letters in positions 7-8), try issuer lookup
        # Bond CUSIPs have format: XXXXXX[A-Z][A-Z]# where stock would be XXXXXX###
        issuer_code = cusip[:6] if len(cusip) >= 6 else cusip
        
        # Direct issuer code lookup
        if issuer_code in issuer_map:
            return issuer_map[issuer_code]
        
        if len(cusip) >= 8 and any(c.isalpha() for c in cusip[6:8]):
            # Try common stock suffix patterns (10#, 20#)
            for suffix in ['101', '100', '102', '103', '104', '105', '106', '107', '108', '109',
                          '201', '200', '202', '203', '204', '205', '206', '207', '208', '209',
                          '301', '302', '303', '304', '305', '306', '307', '308', '309']:
                stock_cusip = issuer_code + suffix
                if stock_cusip in cusip_map:
                    return cusip_map[stock_cusip]

        # 2) OpenFIGI lookup (fills persistent cache when successful)
        #    Skip during batch operations (backtests) to avoid rate limits and slowdowns.
        if os.environ.get("SEC_SKIP_OPENFIGI", "").strip().lower() not in ("1", "true", "yes"):
            ticker = self._openfigi_map_cusip_to_ticker(cusip)
            if ticker:
                self._cusip_ticker_cache[cusip] = ticker
                if base_cusip and base_cusip != cusip:
                    self._cusip_ticker_cache[base_cusip] = ticker
                self._save_cusip_ticker_cache()
                return ticker

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
            df = pd.DataFrame()
            df.attrs["sec_edgar_had_filing"] = False
            df.attrs["sec_edgar_fund"] = fund_name
            return df

        filings = self.get_13f_filings(cik, limit=search_limit)
        if not filings:
            df = pd.DataFrame()
            df.attrs["sec_edgar_had_filing"] = False
            df.attrs["sec_edgar_fund"] = fund_name
            return df

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
            df = pd.DataFrame()
            df.attrs["sec_edgar_had_filing"] = False
            df.attrs["sec_edgar_fund"] = fund_name
            return df

        holdings = self.parse_13f_holdings(cik, chosen["accession_number"])
        # Attach metadata even when holdings is empty, so backtests can distinguish:
        # - "no filing yet" (carry previous portfolio)
        # - "filing exists but filtered/empty" (liquidate to cash)
        try:
            holdings.attrs["sec_edgar_had_filing"] = True
            holdings.attrs["sec_edgar_filing_date"] = chosen.get("filed_date")
            holdings.attrs["sec_edgar_accession_number"] = chosen.get("accession_number")
            holdings.attrs["sec_edgar_fund"] = fund_name
        except Exception:
            pass
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
            # Tech Giants
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
            # From 13F filings - Hedge fund holdings
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
            'SLM CORP': 'SLM',
            'SALLIE MAE': 'SLM',
            # Oaktree Capital Holdings (Howard Marks)
            'TPI COMPOSITES': 'TPIC',
            'BIOXCEL THERAPEUTICS': 'BTAI',
            'EVOLENT HEALTH': 'EVH',
            'FIVERR': 'FVRR',
            'TRANSPORTADORA DE GAS': 'TGS',
            'IRHYTHM': 'IRTC',
            'FASTLY': 'FSLY',
            'ZIFF DAVIS': 'ZD',
            'PELOTON': 'PTON',
            'ASCENDIS': 'ASND',
            'WAYFAIR': 'W',
            'LYFT': 'LYFT',
            'POST HOLDINGS': 'POST',
            'BENTLEY SYSTEMS': 'BSY',
            'DIGITALOCEAN': 'DOCN',
            'SNAP': 'SNAP',
            'ESPERION': 'ESPR',
            'ON SEMICONDUCTOR': 'ON',
            'GROUPON': 'GRPN',
            'BRIDGEBIO': 'BBIO',
            'HERBALIFE': 'HLF',
            'Q2 HOLDINGS': 'QTWO',
            'BLOCK INC': 'SQ',
            'SQUARE': 'SQ',
            'BILL HOLDINGS': 'BILL',
            'CERENCE': 'CRNC',
            'NEOGENOMICS': 'NEO',
            'UNITY SOFTWARE': 'U',
            'GUESS': 'GES',
            'BATTALION OIL': 'BATL',
            'TWO HARBORS': 'TWO',
            'AFFIRM': 'AFRM',
            'NOVOCURE': 'NVCR',
            'TOPGOLF CALLAWAY': 'MODG',
            'CALLAWAY': 'MODG',
            'WINNEBAGO': 'WGO',
            'GUARDANT': 'GH',
            'FUBOTV': 'FUBO',
            'UPWORK': 'UPWK',
            'VERINT': 'VRNT',
            'FRESHPET': 'FRPT',
            'SOUTHERN CO': 'SO',
            'HDFC BANK': 'HDB',
            'PENNYMAC': 'PMT',
            'TRIP.COM': 'TCOM',
            'REDWOOD TRUST': 'RWT',
            'VAIL RESORTS': 'MTN',
            'LCI INDUSTRIES': 'LCII',
            'MAGNITE': 'MGNI',
            'LANTHEUS': 'LNTH',
            # Pershing Square Holdings (Bill Ackman)
            'HILTON WORLDWIDE': 'HLT',
            # Scion Asset Management (Michael Burry)
            'CREDICORP': 'BAP',
            'AMKOR': 'AMKR',
            'ARRAY TECHNOLOGIES': 'ARRY',
            'AXALTA': 'AXTA',
            'EASTMAN CHEMICAL': 'EMN',
            'JFROG': 'FROG',
            'GLOBANT': 'GLOB',
            'GITLAB': 'GTLB',
            'HASHICORP': 'HCP',
            'SAMSARA': 'IOT',
            'KEYSIGHT': 'KEYS',
            'LINCOLN ELECTRIC': 'LECO',
            'MIDDLEBY': 'MIDD',
            'MURPHY USA': 'MUSA',
            'NEUROCRINE': 'NBIX',
            'NATIONAL STORAGE': 'NSA',
            'NISOURCE': 'NI',
            'ONESPAWORLD': 'OSW',
            'PRESTIGE CONSUMER': 'PBH',
            'PAR PACIFIC': 'PARR',
            'PACKAGING CORP': 'PKG',
            'QORVO': 'QRVO',
            'REGENCY CENTERS': 'REG',
            'SIMON PROPERTY': 'SPG',
            'SEAGATE': 'STX',
            'SANMINA': 'SANM',
            'SHELL': 'SHEL',
            'SELECTIVE INSURANCE': 'SIGI',
            'STANDEX': 'SXI',
            'STAG INDUSTRIAL': 'STAG',
            'TERADATA': 'TDC',
            'TERADYNE': 'TER',
            'TREEHOUSE FOODS': 'THS',
            'TOWER SEMICONDUCTOR': 'TSEM',
            'TRANE': 'TT',
            'UDR': 'UDR',
            'VF CORP': 'VFC',
            'VULCAN MATERIALS': 'VMC',
            'VIPSHOP': 'VIPS',
            'VIASAT': 'VSAT',
            'WALGREENS': 'WBA',
            'WABTEC': 'WAB',
            'WORKDAY': 'WDAY',
            'WENDY': 'WEN',
            'WYNDHAM': 'WH',
            'WORTHINGTON': 'WOR',
            'XPO': 'XPO',
            'ZIMMER': 'ZBH',
        }
        
        tickers = []
        for name in names:
            if not name:
                tickers.append(None)
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
                # Returning a fake "ticker" here creates invalid symbols and breaks backtests.
                tickers.append(None)
        
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
