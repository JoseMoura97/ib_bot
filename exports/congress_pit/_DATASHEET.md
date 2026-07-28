# House congressional filing-index point-in-time archive — draft

> This file deliberately starts with `_` so standard PyArrow/Pandas dataset
> discovery ignores it when opening the containing directory with
> `pd.read_parquet`.  It is the dataset's human-readable datasheet.

## What this is

This package contains daily point-in-time vintages of the official U.S. House
financial-disclosure filing index.  Each row identifies an official filing by
`doc_id`, filer name, filing type, filing year, source, and the date on which
our archive captured the index.

The package is a **filing-index dataset, not a trade-line dataset**.  It does
not presently contain a ticker, transaction date, transaction type, or amount.
The source collector intentionally records free official PTR (`filing_type=P`)
metadata but does not parse the transaction lines inside the linked PDFs.

## Coverage and point-in-time meaning

- First captured vintage: 2026-07-13 UTC.
- Last generated partition is stated in `_manifest.json`; coverage must never be
  represented as preceding July 2026.
- A partition named `date=YYYY-MM-DD` contains only records observed in the
  corresponding `altdata_snapshots.captured_at::date` vintage.
- Repeated filing-index records across days are deliberate: they preserve what
  the official index exposed on each capture date.
- When a source snapshot is metadata-only (the unchanged content hash is
  retained without duplicating its payload), the export reconstructs that day
  by carrying forward the latest materialized payload for that source and marks
  every repeated row `payload_mode=carried_forward_unchanged`.

## Sources and rights boundary

Only these free official-source collectors are admitted:

1. `house_financial_disclosure_index`
2. `house_periodic_transaction_report_index`

No Quiver data, API output, paid subscription data, or Capitol Trades content
is included.  The files are derived from public House disclosure-index metadata;
this provenance statement is not legal advice or a redistribution licence.

## Schema

| Field | Meaning |
| --- | --- |
| `snapshot_id` | Source archive row identifier. |
| `captured_at`, `captured_date`, `date` | UTC timestamp/date when this vintage was captured; `date` is the Hive partition field supplied when a Parquet directory is read. |
| `as_of_date` | Collector's requested as-of date. |
| `source` | One of the two allowed official House index sources. |
| `content_hash`, `declared_snapshot_rows` | Integrity and source-snapshot metadata. |
| `payload_mode` | `materialized` if the vintage contained the payload; `carried_forward_unchanged` if an unchanged metadata-only vintage was reconstructed from the last payload. |
| `doc_id` | Official House disclosure document identifier. |
| `first_name`, `last_name`, `bioguide_id` | Filer identity fields supplied by the index. |
| `filing_type`, `filing_year` | Official filing classification and year. |

## Known gaps and release gate

This draft cannot support a three-trade ticker/date/amount spot-check, because
the archived records lack individual transaction lines.  A commercial
trade-level release requires: (a) parsing and archiving the official PTR PDF
transaction lines with document-level provenance, (b) independently verifying
three parsed trades against the official disclosure documents, and (c) at least
30 real daily partitions.  Until then it must be described only as an internal
filing-index archive, never as a licensable congressional-trades dataset.
