#!/usr/bin/env python3
"""Independently re-check three PTR rows directly from archived official PDFs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def canonical(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def page_text(pdf: Path, page: int) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(pdf), "-"],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in (args.evidence / "trade_lines.jsonl").read_text(encoding="utf-8").splitlines()]
    if len(rows) < 3:
        raise SystemExit("need at least three parsed trade rows")
    checks = []
    for row in rows[:3]:
        text = page_text(args.evidence / row["pdf_file"], int(row["page"]))
        passed = all(
            (
                f"({row['ticker']})" in text,
                row["transaction_date"] in text,
                canonical(row["amount_range"]).replace("$ ", "$")
                in canonical(text).replace("$ ", "$"),
            )
        )
        checks.append(
            {
                "doc_id": row["doc_id"],
                "document_url": row["document_url"],
                "page": row["page"],
                "ticker": row["ticker"],
                "transaction_date": row["transaction_date"],
                "amount_range": row["amount_range"],
                "official_page_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "passed": passed,
            }
        )
    result = {"independent_method": "fresh pdftotext extraction from archived official PDF pages", "checks": checks, "passed": all(item["passed"] for item in checks)}
    (args.evidence / "spot_checks.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not result["passed"]:
        raise SystemExit("one or more independent official-PDF spot checks failed")
    print(json.dumps({"spot_checks": len(checks), "passed": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
