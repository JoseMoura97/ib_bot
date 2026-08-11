# House congressional filing-index point-in-time archive

> The leading underscore deliberately keeps this datasheet out of standard
> PyArrow/Pandas directory discovery: `pd.read_parquet("exports/congress_pit")`
> reads the Parquet partitions only.

## Release snapshot and integrity

This release has **30 daily UTC vintages**, from **2026-07-13** through
**2026-08-11**, containing **51,967** filing-index rows.  The authoritative
inventory is [`_manifest.json`](_manifest.json): it lists every partition,
its row count, allowed sources, and the SHA-256 of the exact Parquet file.
The SHA-256 of this manifest is
`ce0247a71f6a2ab0a73e5244892dbdd688d434c7a6f48b76395c854fa944d12b`.

To verify a delivery, recompute each `date=*/filing_index.parquet` SHA-256
and compare it to its corresponding `partitions[].sha256` value in the
manifest.  The partition name is the capture date, not a filing date.

## What this is

Each partition preserves the official U.S. House filing index as our archive
observed it on that capture date.  Repeated records across days are expected:
they retain the point-in-time state of the public index rather than replacing
an earlier vintage with a later version.

This is a **filing-index dataset, not a trade-line dataset**.  It records
official document identifiers, filer metadata, filing classifications and
capture provenance.  It does not claim ticker, transaction-date, transaction-
type or amount coverage in these Parquet files.

## Sources, reconstruction and rights boundary

The package admits exactly two free official House index sources:

1. `house_financial_disclosure_index`
2. `house_periodic_transaction_report_index`

No Quiver data, paid API output, subscription data or Capitol Trades content
is included.  These files derive from public House disclosure-index metadata;
this provenance statement is not legal advice or a redistribution licence.

If an unchanged source snapshot is stored as metadata-only, the exporter
reconstructs its vintage by carrying forward that source's most recent
materialized payload and labels the resulting rows
`payload_mode=carried_forward_unchanged`.  Materialized payloads are labelled
`payload_mode=materialized`.

## Schema

| Field | Meaning |
| --- | --- |
| `snapshot_id` | Source archive row identifier. |
| `captured_at`, `captured_date`, `date` | UTC timestamp/date of the vintage; `date` is supplied by Hive partition discovery. |
| `as_of_date` | Collector's requested as-of date. |
| `source` | One of the two allowed official House index sources. |
| `content_hash`, `declared_snapshot_rows` | Source-snapshot integrity and size metadata. |
| `payload_mode` | `materialized` or a transparently reconstructed `carried_forward_unchanged` payload. |
| `doc_id` | Official House disclosure document identifier. |
| `first_name`, `last_name`, `bioguide_id` | Filer identity fields provided by the index. |
| `filing_type`, `filing_year` | Official filing classification and year. |

## QA and separate PTR evidence

The archive-level QA log at
[`reports/altdata_qa_daily.jsonl`](../../reports/altdata_qa_daily.jsonl)
contains receipts for the same 30 capture dates.  Its latest receipt
(`2026-08-11`) is green and eligible for the streak: it reports all 11
expected archive sources observed, no missing sources, no alerts, and zero
orders or subscriptions.  The log records a 23-day eligible green run from
2026-07-20 through 2026-08-11; earlier capture receipts remain preserved,
including the initial incomplete 2026-07-13 receipt.

Trade-line provenance is intentionally a separate bounded technical-evidence
bundle at [`exports/congress_ptr_trade_lines`](../congress_ptr_trade_lines/).
Its manifest records three archived official House PTR PDFs and four parsed
lines; its three passed spot checks use fresh `pdftotext` extraction from the
archived official PDF pages.  Those lines are not represented as trade rows in
this filing-index Parquet package.
