"""
Annual Financial Disclosure (FD) parser for U.S. House politicians.

Pipeline
--------
1. Resolve each politician's annual FD DocID from the House Clerk index XMLs
   (one XML per year at https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}/index.xml).
2. Download the corresponding PDF from
   https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{DocID}.pdf
   (older years use /financial-pdfs/{year}/{DocID}.pdf).
3. Extract text with pypdf (fast path) and fall back to OCR when the PDF is
   scanned (older filings).
4. Pass the extracted text to DeepSeek (v4-flash by default, v4-pro for hard
   layouts) with a strict JSON schema prompt. The LLM returns structured
   holdings: [{name, ticker, asset_type, value_range_low, value_range_high,
   transaction_type, income_type}].
5. Cache the parsed JSON to .cache/annual_fd/{bioguide}_{year}.json. Subsequent
   runs skip the LLM call.

Why DeepSeek
------------
- v4-flash is $0.14/$0.28 per 1M tokens (input/output). An annual FD is
  typically 5-15 pages = ~5-15k input tokens = ~$0.001-0.003 per filing.
- Conductor already has a working DeepSeek wrapper at
  ~/Desktop/cursor-projects/conductor/orchestrator/conductor/llm/deepseek.py
  and an API key in conductor/.env. This module reuses the same key.

Usage
-----
    from annual_fd_parser import fetch_and_parse_annual_fd
    holdings = fetch_and_parse_annual_fd(
        bioguide_id="M001207",        # Dan Meuser
        first_name="Daniel",
        last_name="Meuser",
        year=2023,
    )
    # → list of dicts with normalized holdings

Integration with the backtest engine
-----------------------------------
`quiver_engine._get_raw_data_with_metadata_at_date` will (separately) load these
parsed annual FDs and merge them with PTR-derived weights before passing to
`apply_strategy_weights_at_date`. See `annual_fd_loader.merge_with_ptrs`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

# --- Configuration -------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_ROOT = PROJECT_ROOT / ".cache" / "annual_fd"
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
PDF_CACHE_ROOT = CACHE_ROOT / "pdfs"
PDF_CACHE_ROOT.mkdir(parents=True, exist_ok=True)

# House Clerk endpoints. The annual ZIP under /public_disc/financial-pdfs/<year>FD.zip
# contains <year>FD.xml (the index) and the PDFs. We hit the JSON-equivalent
# of the index for cleaner parsing.
HOUSE_FD_INDEX_URL = (
    "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
)
HOUSE_FD_PDF_URL = (
    "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"
)
HOUSE_FD_PDF_FALLBACK_URL = (
    "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}/{doc_id}.pdf"
)

# DeepSeek config: read from conductor/.env if available, else env vars.
def _load_deepseek_creds() -> tuple[str, str, str]:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
    model = os.environ.get("ANNUAL_FD_MODEL", "deepseek-v4-flash").strip()

    if not api_key:
        # Fall back to conductor's .env
        conductor_env = Path.home() / "Desktop" / "cursor-projects" / "conductor" / ".env"
        if conductor_env.exists():
            for line in conductor_env.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("DEEPSEEK_BASE_URL="):
                    base_url = line.split("=", 1)[1].strip().strip('"').strip("'")

    return api_key, base_url, model


# --- Data types ---------------------------------------------------------

@dataclass
class Holding:
    name: str                       # Asset name as disclosed
    ticker: Optional[str]           # Ticker symbol if parseable
    asset_type: str                 # ST (stock), MF (mutual fund), GS (govt), etc.
    value_low: Optional[float]      # Low end of disclosed value range (USD)
    value_high: Optional[float]     # High end of disclosed value range
    income_type: Optional[str]      # Dividends, Interest, None, etc.
    income_amount: Optional[float]  # Reported income amount

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnnualFDIndexEntry:
    doc_id: str
    bioguide_id: Optional[str]
    first_name: str
    last_name: str
    filing_year: int
    filing_type: str   # "A" = Annual, "P" = PTR, etc.


# --- Index parsing -------------------------------------------------------

def _index_cache_path(year: int) -> Path:
    return CACHE_ROOT / f"index_{year}.json"


def fetch_index(year: int, *, force: bool = False) -> list[AnnualFDIndexEntry]:
    """Download + parse the House Clerk annual FD index XML for `year`.

    The official endpoint returns a ZIP containing `<year>FD.xml`. We unzip and
    parse it, keeping only FilingType == 'A' (Annual) rows.
    """
    cache_path = _index_cache_path(year)
    if cache_path.exists() and not force:
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            return [AnnualFDIndexEntry(**r) for r in payload]
        except Exception:
            logger.warning("Stale index cache for %s — refetching", year)

    import io, zipfile

    url = HOUSE_FD_INDEX_URL.format(year=year)
    headers = {"User-Agent": "ib_bot annual_fd_parser/1.0"}
    with httpx.Client(timeout=60.0, headers=headers) as client:
        r = client.get(url)
        r.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    xml_name = next((n for n in zf.namelist() if n.lower().endswith(".xml")), None)
    if xml_name is None:
        raise RuntimeError(f"No XML in {url}")
    xml_bytes = zf.read(xml_name)

    root = ET.fromstring(xml_bytes)
    entries: list[AnnualFDIndexEntry] = []
    for m in root.findall("Member"):
        entries.append(AnnualFDIndexEntry(
            doc_id=(m.findtext("DocID") or "").strip(),
            bioguide_id=(m.findtext("BioGuideID") or "").strip() or None,
            first_name=(m.findtext("First") or "").strip(),
            last_name=(m.findtext("Last") or "").strip(),
            filing_year=int(m.findtext("Year") or year),
            filing_type=(m.findtext("FilingType") or "").strip(),
        ))

    cache_path.write_text(json.dumps([e.__dict__ for e in entries], indent=2), encoding="utf-8")
    return entries


_ANNUAL_FILING_TYPES = {"A", "O"}  # A=Annual, O=OGE 278/Original — both are comprehensive year-end disclosures.


def find_annual_fd(
    *,
    year: int,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    bioguide_id: Optional[str] = None,
) -> Optional[AnnualFDIndexEntry]:
    """Lookup the politician's Annual FD entry for `year`. Returns None if not found.

    Accepts FilingType A (Annual) or O (OGE 278 / Original). Both are
    comprehensive year-end disclosures with full asset listings; PTRs (P)
    are transaction-only and not what we want here.
    """
    entries = fetch_index(year)
    bid = (bioguide_id or "").strip().upper() or None
    fn = (first_name or "").strip().lower() or None
    ln = (last_name or "").strip().lower() or None

    for e in entries:
        if e.filing_type not in _ANNUAL_FILING_TYPES:
            continue
        if bid and (e.bioguide_id or "").upper() == bid:
            return e
        # Loose first-name match: House Clerk records often include a middle
        # name ("Donald Sternoff" for Donald Beyer), so we match on prefix and
        # also accept first-token equality.
        e_first = e.first_name.lower().strip()
        e_first_tok = e_first.split()[0] if e_first else ""
        if fn and ln and e.last_name.lower() == ln and (
            e_first == fn or e_first.startswith(fn + " ") or e_first_tok == fn
        ):
            return e
    return None


# --- PDF download + text extraction --------------------------------------

def _download_pdf(year: int, doc_id: str) -> Path:
    cache = PDF_CACHE_ROOT / f"{year}_{doc_id}.pdf"
    if cache.exists() and cache.stat().st_size > 1024:
        return cache

    headers = {"User-Agent": "ib_bot annual_fd_parser/1.0"}
    for url in (HOUSE_FD_PDF_URL, HOUSE_FD_PDF_FALLBACK_URL):
        full = url.format(year=year, doc_id=doc_id)
        try:
            with httpx.Client(timeout=60.0, headers=headers, follow_redirects=True) as client:
                r = client.get(full)
                if r.status_code == 200 and r.content[:4] == b"%PDF":
                    cache.write_bytes(r.content)
                    return cache
        except Exception as e:
            logger.warning("PDF fetch failed (%s): %s", full, e)
    raise RuntimeError(f"Could not download FD PDF for {year}/{doc_id}")


def _extract_text(pdf_path: Path) -> str:
    """Extract text from a PDF. Tries pypdf first, then OCR via pytesseract."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf not installed; pip install pypdf")

    text_parts: list[str] = []
    try:
        reader = PdfReader(str(pdf_path))
        for page in reader.pages:
            t = page.extract_text() or ""
            text_parts.append(t)
    except Exception as e:
        logger.warning("pypdf failed on %s: %s — falling back to OCR", pdf_path, e)
        text_parts = []

    text = "\n".join(text_parts).strip()
    if len(text) < 200:
        # Looks like a scanned PDF — try OCR.
        text = _ocr_pdf(pdf_path)
    return text


def _ocr_pdf(pdf_path: Path) -> str:
    """OCR an image-only PDF using pdf2image + pytesseract. Best-effort."""
    try:
        from pdf2image import convert_from_path  # type: ignore
        import pytesseract  # type: ignore
    except ImportError:
        logger.warning("OCR deps missing (pdf2image, pytesseract); skipping OCR for %s", pdf_path)
        return ""

    pages = convert_from_path(str(pdf_path), dpi=200)
    text_parts: list[str] = []
    for img in pages:
        try:
            text_parts.append(pytesseract.image_to_string(img))
        except Exception as e:
            logger.warning("OCR failed on page: %s", e)
    return "\n".join(text_parts)


# --- DeepSeek extraction -------------------------------------------------

_EXTRACTION_PROMPT = """You are an expert at extracting structured data from
U.S. House of Representatives Annual Financial Disclosure (FD) forms.

The text below is a single representative's annual FD. Extract Schedule A
(assets / unearned income) holdings ONLY. Skip Schedule B (transactions),
Schedule C (earned income), Schedule D (liabilities), Schedule E (positions),
Schedule F (agreements), Schedule G (gifts), Schedule H (travel),
Schedule I (payments to charity).

For each Schedule A row, return a JSON object with EXACTLY these keys:
  - "name":         Asset name as disclosed, verbatim (string)
  - "ticker":       Best-guess US ticker symbol if it's a publicly traded
                    equity or ETF, else null (e.g. "Apple Inc. (AAPL)" → "AAPL")
  - "asset_type":   One of: "ST" (stock), "MF" (mutual fund), "ETF",
                    "BD" (bond), "GS" (govt securities), "RP" (real estate),
                    "OT" (other), "OL" (other long-term), "CASH"
  - "value_low":    Low end of value range in USD (integer or null)
                    Use mapping: $1-$1,000=500; $1,001-$15,000=8000;
                    $15,001-$50,000=32500; $50,001-$100,000=75000;
                    $100,001-$250,000=175000; $250,001-$500,000=375000;
                    $500,001-$1,000,000=750000; $1,000,001-$5,000,000=3000000;
                    $5,000,001-$25,000,000=15000000; $25,000,001-$50,000,000=37500000;
                    "Over $50,000,000"=75000000
  - "value_high":   High end of same range (integer or null), use the upper bound
  - "income_type":  "Dividends", "Interest", "Capital Gains", "None", or null
  - "income_amount": Reported income in USD (integer or null)

Return ONLY a JSON array of objects. No prose, no markdown fence, no
explanation. If no Schedule A is present, return [].

--- FD TEXT START ---
{text}
--- FD TEXT END ---
"""


def extract_holdings_via_deepseek(
    text: str,
    *,
    model: Optional[str] = None,
    timeout_s: float = 180.0,
) -> list[Holding]:
    """Run DeepSeek to extract structured Schedule A holdings from FD text."""
    api_key, base_url, default_model = _load_deepseek_creds()
    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY not configured. Set in env or in "
            "~/Desktop/cursor-projects/conductor/.env"
        )
    model = model or default_model

    prompt = _EXTRACTION_PROMPT.format(text=text[:60000])  # cap input
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    t0 = time.time()
    with httpx.Client(timeout=timeout_s) as client:
        r = client.post(f"{base_url.rstrip('/')}/chat/completions",
                        json=payload, headers=headers)
    elapsed = time.time() - t0
    if r.status_code != 200:
        raise RuntimeError(f"DeepSeek {r.status_code}: {r.text[:400]}")
    body = r.json()
    content = body["choices"][0]["message"]["content"]

    # response_format=json_object can return {"holdings": [...]} or a bare array.
    parsed: list[dict]
    try:
        obj = json.loads(content)
        if isinstance(obj, list):
            parsed = obj
        elif isinstance(obj, dict):
            # try common wrappers
            for k in ("holdings", "schedule_a", "items", "data", "rows"):
                if k in obj and isinstance(obj[k], list):
                    parsed = obj[k]
                    break
            else:
                parsed = []
        else:
            parsed = []
    except json.JSONDecodeError:
        # Try to extract JSON array via regex.
        m = re.search(r"\[\s*\{.*\}\s*\]", content, re.DOTALL)
        parsed = json.loads(m.group(0)) if m else []

    holdings: list[Holding] = []
    for row in parsed:
        if not isinstance(row, dict):
            continue
        holdings.append(Holding(
            name=str(row.get("name") or "").strip(),
            ticker=(str(row.get("ticker")).strip().upper() if row.get("ticker") else None),
            asset_type=str(row.get("asset_type") or "OT").strip().upper(),
            value_low=_to_float(row.get("value_low")),
            value_high=_to_float(row.get("value_high")),
            income_type=row.get("income_type") if row.get("income_type") else None,
            income_amount=_to_float(row.get("income_amount")),
        ))

    logger.info(
        "DeepSeek (%s) extracted %d holdings in %.1fs (in=%d out=%d tokens)",
        model, len(holdings), elapsed,
        body.get("usage", {}).get("prompt_tokens", 0),
        body.get("usage", {}).get("completion_tokens", 0),
    )
    return holdings


def _to_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --- Top-level pipeline --------------------------------------------------

def fetch_and_parse_annual_fd(
    *,
    year: int,
    bioguide_id: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    force: bool = False,
    model: Optional[str] = None,
) -> list[Holding]:
    """End-to-end: index → PDF → text → structured holdings (cached)."""
    cache_key = bioguide_id or f"{(last_name or '').lower()}_{(first_name or '').lower()}"
    cache_path = CACHE_ROOT / f"{cache_key}_{year}.json"

    if cache_path.exists() and not force:
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            return [Holding(**r) for r in payload["holdings"]]
        except Exception:
            logger.warning("Stale holdings cache for %s — refetching", cache_key)

    entry = find_annual_fd(
        year=year, bioguide_id=bioguide_id,
        first_name=first_name, last_name=last_name,
    )
    if entry is None:
        logger.info("No annual FD found for %s in %d", cache_key, year)
        return []

    pdf_path = _download_pdf(year, entry.doc_id)
    text = _extract_text(pdf_path)
    if len(text.strip()) < 100:
        logger.warning("FD %s/%s extracted <100 chars of text; skipping", year, entry.doc_id)
        return []

    holdings = extract_holdings_via_deepseek(text, model=model)

    cache_path.write_text(
        json.dumps({
            "year": year,
            "doc_id": entry.doc_id,
            "bioguide_id": entry.bioguide_id,
            "first_name": entry.first_name,
            "last_name": entry.last_name,
            "model": model or _load_deepseek_creds()[2],
            "holdings": [h.to_dict() for h in holdings],
        }, indent=2),
        encoding="utf-8",
    )
    return holdings


# --- CLI -----------------------------------------------------------------

def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--bioguide", type=str, default=None)
    p.add_argument("--first", type=str, default=None)
    p.add_argument("--last", type=str, default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--model", type=str, default=None,
                   help="deepseek-v4-flash (default) or deepseek-v4-pro")
    args = p.parse_args()

    holdings = fetch_and_parse_annual_fd(
        year=args.year, bioguide_id=args.bioguide,
        first_name=args.first, last_name=args.last,
        force=args.force, model=args.model,
    )
    print(json.dumps([h.to_dict() for h in holdings], indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _cli()
