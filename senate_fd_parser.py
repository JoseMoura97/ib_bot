"""
Senate Annual FD parser — companion to annual_fd_parser.py for Senators.

Senate disclosures live at efdsearch.senate.gov which requires an interstitial
"prohibition agreement" form before search. The flow is:

  1. GET  /search/home/           → grab CSRF from form
  2. POST /search/home/           → accept agreement
  3. POST /search/report/data/    → search reports by name/type
  4. GET  /search/view/annual/{uuid}/  → HTML report (or /paper/{id}/ for PDF)

We then extract text (HTML or PDF) and feed to DeepSeek using the same
extraction prompt as the House parser. Results land in
.cache/annual_fd/{last}_{first}_{year}.json with the same schema as House
filings, so annual_fd_loader picks them up transparently.

Report type codes (observed on efdsearch):
  7  = Annual Public Financial Disclosure
  11 = Periodic Transaction Report

Reference: neelsomani/senator-filings scraper (MIT licence).
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from annual_fd_parser import (
    CACHE_ROOT,
    PDF_CACHE_ROOT,
    Holding,
    extract_holdings_via_deepseek,
)

logger = logging.getLogger(__name__)

ROOT = "https://efdsearch.senate.gov"
LANDING_PAGE_URL = f"{ROOT}/search/home/"
SEARCH_PAGE_URL = f"{ROOT}/search/"
REPORTS_URL = f"{ROOT}/search/report/data/"

ANNUAL_REPORT_TYPE = 7   # Annual Public FD
PAPER_PREFIX = "/search/view/paper/"
HTML_PREFIX = "/search/view/annual/"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def _new_session() -> requests.Session:
    """efdsearch.senate.gov is behind a WAF that 403's clients missing the
    full Chrome fingerprint (Sec-Fetch-* and Sec-Ch-Ua-* headers). We send
    them all on every request.
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def _accept_agreement(session: requests.Session) -> str:
    """Hit landing, accept the prohibition agreement, return CSRF token."""
    r = session.get(LANDING_PAGE_URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    el = soup.find(attrs={"name": "csrfmiddlewaretoken"})
    if not el or not el.get("value"):
        raise RuntimeError("Could not find CSRF on Senate landing page")
    csrf = el["value"]

    session.post(
        LANDING_PAGE_URL,
        data={"csrfmiddlewaretoken": csrf, "prohibition_agreement": "1"},
        headers={"Referer": LANDING_PAGE_URL},
        timeout=30,
    )

    csrf = session.cookies.get("csrftoken") or session.cookies.get("csrf") or csrf
    return csrf


def search_annual_reports(
    session: requests.Session,
    csrf: str,
    *,
    first_name: str,
    last_name: str,
    start_date: str = "01/01/2014 00:00:00",
) -> list[dict]:
    """POST to the Senate /search/report/data/ endpoint and return rows.

    Each row is a list: [first, last, office, link_html, date_received].
    We promote them to dicts with parsed link + date for ease of use.
    """
    out: list[dict] = []
    offset = 0
    batch_size = 100
    while True:
        time.sleep(2.0)  # polite rate limit
        payload = {
            "start": str(offset),
            "length": str(batch_size),
            "report_types": f"[{ANNUAL_REPORT_TYPE}]",
            "filer_types": "[]",
            "submitted_start_date": start_date,
            "submitted_end_date": "",
            "candidate_state": "",
            "senator_state": "",
            "office_id": "",
            "first_name": first_name,
            "last_name": last_name,
            "csrfmiddlewaretoken": csrf,
        }
        r = session.post(
            REPORTS_URL,
            data=payload,
            headers={"Referer": SEARCH_PAGE_URL},
            timeout=30,
        )
        r.raise_for_status()
        rows = r.json().get("data", [])
        if not rows:
            break
        for row in rows:
            # Row format: [first, last, office, link_html, date_received]
            if len(row) < 5:
                continue
            first, last, office, link_html, date_received = row[:5]
            href = ""
            try:
                href = BeautifulSoup(link_html, "html.parser").a.get("href", "")
            except Exception:
                pass
            out.append({
                "first_name": first.strip(),
                "last_name": last.strip(),
                "office": office.strip(),
                "href": href,
                "filing_date": date_received.strip(),
            })
        if len(rows) < batch_size:
            break
        offset += batch_size
    return out


def _filing_year(filing_date_str: str) -> Optional[int]:
    """Senate dates look like '05/15/2024'. The disclosed CALENDAR YEAR is
    typically the year before filing (annual FDs cover prior calendar year)."""
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", filing_date_str)
    if not m:
        return None
    filed_year = int(m.group(3))
    return filed_year - 1


def _fetch_report_text(session: requests.Session, href: str) -> tuple[str, str]:
    """Return (text, source) where source is 'html' or 'pdf'."""
    url = f"{ROOT}{href}"
    r = session.get(url, timeout=60)
    r.raise_for_status()

    # If the response is a PDF (paper filing redirect), save + extract.
    if r.headers.get("Content-Type", "").startswith("application/pdf") or r.content[:4] == b"%PDF":
        m = re.search(r"/([^/]+)/?$", href.rstrip("/"))
        doc_id = m.group(1) if m else "unknown"
        pdf_path = PDF_CACHE_ROOT / f"senate_{doc_id}.pdf"
        pdf_path.write_bytes(r.content)
        from annual_fd_parser import _extract_text
        return _extract_text(pdf_path), "pdf"

    # HTML disclosure — strip tags and keep the body text.
    soup = BeautifulSoup(r.text, "html.parser")
    # Senate HTML disclosures put the report in the main content div.
    main = soup.find("section", id="main-content") or soup.find("div", class_="container") or soup
    text = main.get_text("\n", strip=True)
    return text, "html"


def fetch_and_parse_senate_annual_fd(
    *,
    first_name: str,
    last_name: str,
    target_year: Optional[int] = None,
    force: bool = False,
    model: Optional[str] = None,
) -> dict[int, list[Holding]]:
    """End-to-end Senate FD ingestion.

    Returns a dict mapping calendar year → list[Holding] for every annual
    disclosure found for this senator. Caches each year separately at
    .cache/annual_fd/{lastname_lower}_{firstname_lower}_{year}.json so the
    main `annual_fd_loader` picks them up.
    """
    cache_key = f"{last_name.lower()}_{first_name.lower()}"

    # Skip refetching cached years unless force.
    cached_years: set[int] = set()
    if not force:
        for p in CACHE_ROOT.glob(f"{cache_key}_*.json"):
            m = re.search(r"_(\d{4})\.json$", p.name)
            if m:
                cached_years.add(int(m.group(1)))

    session = _new_session()
    csrf = _accept_agreement(session)
    reports = search_annual_reports(
        session, csrf,
        first_name=first_name, last_name=last_name,
    )
    logger.info("Senate search: %d annual reports for %s %s",
                len(reports), first_name, last_name)

    results: dict[int, list[Holding]] = {}

    for rep in reports:
        year = _filing_year(rep["filing_date"])
        if year is None:
            continue
        if target_year and year != target_year:
            continue
        if year in cached_years and not force:
            logger.info("Skipping %s %d — cached", cache_key, year)
            try:
                payload = json.loads((CACHE_ROOT / f"{cache_key}_{year}.json").read_text(encoding="utf-8"))
                results[year] = [Holding(**h) for h in payload["holdings"]]
            except Exception:
                pass
            continue
        if not rep["href"]:
            logger.warning("No href for %s %d", cache_key, year)
            continue

        try:
            text, src = _fetch_report_text(session, rep["href"])
        except Exception as e:
            logger.warning("Fetch failed for %s %d: %s", cache_key, year, e)
            continue
        if len(text.strip()) < 200:
            logger.warning("Empty text for %s %d (%s)", cache_key, year, src)
            continue

        try:
            holdings = extract_holdings_via_deepseek(text, model=model)
        except Exception as e:
            logger.warning("DeepSeek extract failed for %s %d: %s", cache_key, year, e)
            continue

        # Write in the same schema as annual_fd_parser.fetch_and_parse_annual_fd
        out_path = CACHE_ROOT / f"{cache_key}_{year}.json"
        out_path.write_text(
            json.dumps({
                "year": year,
                "doc_id": rep["href"],
                "bioguide_id": None,
                "first_name": first_name,
                "last_name": last_name,
                "model": model or "deepseek-v4-flash",
                "source": f"senate_{src}",
                "holdings": [h.to_dict() for h in holdings],
            }, indent=2),
            encoding="utf-8",
        )
        results[year] = holdings
        logger.info("Senate FD %s %d → %d holdings (%d tickered)",
                    cache_key, year, len(holdings),
                    sum(1 for h in holdings if h.ticker))

    return results


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--first", required=True)
    p.add_argument("--last", required=True)
    p.add_argument("--year", type=int, default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--model", default=None)
    a = p.parse_args()
    res = fetch_and_parse_senate_annual_fd(
        first_name=a.first, last_name=a.last,
        target_year=a.year, force=a.force, model=a.model,
    )
    print(f"Parsed {len(res)} year(s):")
    for yr, hs in sorted(res.items()):
        tickers = sum(1 for h in hs if h.ticker)
        print(f"  {yr}: {len(hs)} holdings ({tickers} tickered)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _cli()
