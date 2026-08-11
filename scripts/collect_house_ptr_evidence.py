#!/usr/bin/env python3
"""Archive a small, auditable sample of official House PTR trade lines.

The House Clerk's annual filing index identifies PTR documents but is not a
trade-level feed.  This collector deliberately downloads only public official
PDFs, preserves the original document bytes, and emits only lines for which a
ticker, transaction date and amount range occur together on one PDF page.
It is a bounded evidence collector, not a production trading-data ingestion
job.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


INDEX_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
PDF_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"
USER_AGENT = "ib_bot official House PTR evidence collector/1.0"
TICKER_RE = re.compile(r"\(([A-Z][A-Z0-9.]{0,5})\)")
DATE_RE = re.compile(r"\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:20)?\d{2}\b")
AMOUNT_RE = re.compile(
    r"\$?\s*(?:1\s*-\s*\$?\s*1,000|1,001\s*-\s*\$?\s*15,000|"
    r"15,001\s*-\s*\$?\s*50,000|50,001\s*-\s*\$?\s*100,000|"
    r"100,001\s*-\s*\$?\s*250,000|250,001\s*-\s*\$?\s*500,000|"
    r"500,001\s*-\s*\$?\s*1,000,000|1,000,001\s*-\s*\$?\s*5,000,000|"
    r"5,000,001\s*-\s*\$?\s*25,000,000|25,000,001\s*-\s*\$?\s*50,000,000|"
    r"Over\s+\$?\s*50,000,000)"
)


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed official URL
        return response.read()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ptr_documents(year: int) -> list[dict[str, str]]:
    archive = fetch(INDEX_URL.format(year=year))
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        xml_name = next(name for name in zf.namelist() if name.lower().endswith(".xml"))
        root = ET.fromstring(zf.read(xml_name))
    docs = []
    for member in root.findall("Member"):
        if (member.findtext("FilingType") or "").strip() != "P":
            continue
        doc_id = (member.findtext("DocID") or "").strip()
        if not doc_id:
            continue
        docs.append(
            {
                "doc_id": doc_id,
                "first_name": (member.findtext("First") or "").strip(),
                "last_name": (member.findtext("Last") or "").strip(),
                "filing_year": str(year),
            }
        )
    return sorted(docs, key=lambda item: int(item["doc_id"]), reverse=True)


def page_text(pdf_path: Path) -> list[str]:
    info = subprocess.run(["pdfinfo", str(pdf_path)], check=True, text=True, capture_output=True)
    pages_match = re.search(r"^Pages:\s+(\d+)$", info.stdout, re.MULTILINE)
    if not pages_match:
        raise RuntimeError(f"pdfinfo did not report page count for {pdf_path}")
    pages = []
    for page in range(1, int(pages_match.group(1)) + 1):
        result = subprocess.run(
            ["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(pdf_path), "-"],
            check=True,
            text=True,
            capture_output=True,
        )
        pages.append(result.stdout)
    return pages


def normalise_amount(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("$ ", "$ ")).strip()


def parse_page(text: str, *, document: dict[str, str], page_number: int) -> list[dict[str, object]]:
    """Extract bounded evidence records from a single official page.

    A line is accepted only when all three acceptance fields are visibly on a
    short window around an explicit parenthesised ticker.  The retained
    ``official_text_excerpt`` lets a reviewer inspect the original layout.
    """
    lines = text.splitlines()
    records: list[dict[str, object]] = []
    for index, line in enumerate(lines):
        ticker_match = TICKER_RE.search(line)
        # The House form's stock asset rows mark the parenthesised ticker with
        # ``[ST]``.  Requiring it prevents an unrelated parenthesised word in
        # a neighbouring wrapped line from borrowing a previous trade's date
        # and amount range.
        if not ticker_match or "[ST]" not in line:
            continue
        window = " ".join(lines[max(0, index - 1) : min(len(lines), index + 3)])
        dates = DATE_RE.findall(window)
        amount_match = AMOUNT_RE.search(window)
        if not dates or not amount_match:
            continue
        transaction_type = None
        type_match = re.search(r"\b(P|S|E|G|X)\b", window)
        if type_match:
            transaction_type = type_match.group(1)
        record = {
            "doc_id": document["doc_id"],
            "filer": " ".join(part for part in (document["first_name"], document["last_name"]) if part),
            "filing_year": int(document["filing_year"]),
            "document_url": PDF_URL.format(year=document["filing_year"], doc_id=document["doc_id"]),
            "pdf_file": f"pdf/{document['filing_year']}_{document['doc_id']}.pdf",
            "page": page_number,
            "ticker": ticker_match.group(1),
            "transaction_date": dates[-1],
            "amount_range": normalise_amount(amount_match.group(0)),
            "transaction_type": transaction_type,
            "official_text_excerpt": window,
        }
        key = (record["doc_id"], record["page"], record["ticker"], record["transaction_date"], record["amount_range"])
        if not any((r["doc_id"], r["page"], r["ticker"], r["transaction_date"], r["amount_range"]) == key for r in records):
            records.append(record)
    return records


def atomic_replace(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    source.replace(destination)


def collect(out: Path, year: int, max_documents: int) -> dict[str, object]:
    stage = Path(tempfile.mkdtemp(prefix="house_ptr_evidence_", dir=out.parent))
    (stage / "pdf").mkdir()
    (stage / "page_text").mkdir()
    records: list[dict[str, object]] = []
    documents: list[dict[str, object]] = []
    selected_docs: set[str] = set()
    try:
        for document in ptr_documents(year)[:max_documents]:
            url = PDF_URL.format(year=year, doc_id=document["doc_id"])
            try:
                data = fetch(url)
                if not data.startswith(b"%PDF"):
                    continue
                pdf_name = f"{year}_{document['doc_id']}.pdf"
                pdf_path = stage / "pdf" / pdf_name
                pdf_path.write_bytes(data)
                pages = page_text(pdf_path)
            except Exception as exc:  # leave a machine-readable record and try another official PTR
                documents.append({**document, "document_url": url, "status": "unusable", "error": type(exc).__name__})
                continue
            per_document: list[dict[str, object]] = []
            for page_number, text in enumerate(pages, start=1):
                (stage / "page_text" / f"{year}_{document['doc_id']}_p{page_number}.txt").write_text(text, encoding="utf-8")
                per_document.extend(parse_page(text, document=document, page_number=page_number))
            if not per_document:
                pdf_path.unlink(missing_ok=True)
                for path in (stage / "page_text").glob(f"{year}_{document['doc_id']}_p*.txt"):
                    path.unlink()
                documents.append({**document, "document_url": url, "status": "no_qualifying_ticker_date_amount_line"})
                continue
            selected_docs.add(document["doc_id"])
            records.extend(per_document)
            documents.append(
                {
                    **document,
                    "document_url": url,
                    "status": "archived",
                    "pdf_file": f"pdf/{pdf_name}",
                    "pdf_sha256": sha256(data),
                    "page_count": len(pages),
                    "parsed_line_count": len(per_document),
                }
            )
            if len(records) >= 3 and len(selected_docs) >= 1:
                break
        if len(records) < 3:
            raise RuntimeError(f"only {len(records)} qualifying PTR ticker/date/amount lines found")
        records.sort(key=lambda row: (str(row["doc_id"]), int(row["page"]), str(row["ticker"])))
        with (stage / "trade_lines.jsonl").open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        manifest = {
            "schema_version": 1,
            "source": "official U.S. House Clerk PTR PDFs only",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "documents": documents,
            "archived_document_count": sum(1 for item in documents if item.get("status") == "archived"),
            "parsed_line_count": len(records),
            "trade_lines_file": "trade_lines.jsonl",
            "provenance_required": ["document_url", "pdf_file", "page"],
        }
        (stage / "_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (stage / "_DATASHEET.md").write_text(
            "# Official House PTR trade-line evidence (technical subgate)\n\n"
            "Each JSONL row is a bounded extraction from an archived public House Clerk PTR PDF. "
            "It carries the official document URL, local PDF path, and one-based PDF page. "
            "This evidence does not change the separate 30-capture-date or José-delivery gates.\n",
            encoding="utf-8",
        )
        atomic_replace(stage, out)
        return manifest
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--year", type=int, default=datetime.now(timezone.utc).year)
    parser.add_argument("--max-documents", type=int, default=40)
    args = parser.parse_args()
    manifest = collect(args.out, args.year, args.max_documents)
    print(json.dumps({"archived_document_count": manifest["archived_document_count"], "parsed_line_count": manifest["parsed_line_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
