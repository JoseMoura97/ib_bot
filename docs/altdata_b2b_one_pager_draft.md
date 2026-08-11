# U.S. public-market alternative-data archive — B2B one-pager

## What exists now

We have a daily point-in-time archive: it preserves what each public source
exposed on the day we captured it, rather than rewriting history with later
revisions.  The current House filing-index package has 30 daily vintages from
2026-07-13 through 2026-08-11.  Its manifest records 51,967 index rows and a
SHA-256 for every delivered Parquet partition.

The package is deliberately precise about its scope.  It is an official House
filing-index archive, not a claimed trade-level feed.  It contains document
and filer metadata plus capture provenance; it does not claim ticker,
transaction-date, transaction-type or amount coverage in those Parquet files.

## Archive coverage

The archive QA receipt names these 11 free source families:

1. CFTC disaggregated futures COT
2. FINRA off-exchange short volume
3. FRED market regime
4. House financial-disclosure index
5. House periodic-transaction-report index
6. Iron Wing equity daily bars
7. Nasdaq symbol directory
8. SEC 13F — Berkshire Hathaway
9. SEC 13F — Scion Asset Management
10. SEC daily material filings
11. USAspending recent contract awards

The 2026-08-11 receipt is green and eligible for the QA streak: all 11
expected sources were observed, with no missing sources or alerts and zero
orders placed or subscriptions purchased.  The receipt log preserves 30
capture-date receipts covering 2026-07-13 through 2026-08-11; the continuous
eligible green run is 23 days, 2026-07-20 through 2026-08-11.

## Evidence and provenance

The House package admits only the two free official House index sources.  It
contains no Quiver data, paid APIs, subscription data or Capitol Trades
content.  Every partition is enumerated with its actual SHA-256 in
[`exports/congress_pit/_manifest.json`](../exports/congress_pit/_manifest.json);
the accompanying datasheet defines the fields, reconstruction policy and
known boundary.

Separate technical PTR evidence is retained with document-level provenance:
three official House PTR PDFs, four parsed lines, and three passed independent
spot checks.  Each check uses a fresh `pdftotext` extraction from an archived
official PDF page and is documented in
[`exports/congress_ptr_trade_lines/spot_checks.json`](../exports/congress_ptr_trade_lines/spot_checks.json).
This evidence is kept separate from the filing-index dataset so the product
does not overstate what its Parquet rows contain.

## What a B2B recipient receives

- A partitioned Parquet filing-index archive for the 30 daily vintages.
- A manifest with per-partition row counts, source allow-list and SHA-256
  checksums, plus a human-readable datasheet and field dictionary.
- The daily QA receipt log, including the latest green receipt and the
  documented eligible streak.
- A separate, bounded PTR evidence bundle with official-document URLs, local
  PDF hashes, page provenance and independent spot-check results.

No buyer has been contacted, no paid source has been acquired, and no
subscription or order has been placed.  Any commercial outreach remains
subject to José's explicit one-tap approval.
