from __future__ import annotations

from scripts.collect_house_ptr_evidence import parse_page


def test_parse_page_requires_visible_ticker_date_and_amount_together():
    document = {
        "doc_id": "20035047",
        "first_name": "James",
        "last_name": "Himes",
        "filing_year": "2026",
    }
    text = """Bank of America Corporation Common Stock (BAC) [ST] S 07/20/2026 $1,001 - $15,000
No qualified trade here: ticker (MISS) only.
"""

    rows = parse_page(text, document=document, page_number=4)

    assert len(rows) == 1
    assert rows[0]["ticker"] == "BAC"
    assert rows[0]["transaction_date"] == "07/20/2026"
    assert rows[0]["amount_range"] == "$1,001 - $15,000"
    assert rows[0]["page"] == 4
    assert rows[0]["document_url"].endswith("/2026/20035047.pdf")
