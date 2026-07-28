# Draft — U.S. House disclosure point-in-time archive

## Decision material for José — not buyer-facing

We have started accumulating daily copies of the public U.S. House financial
disclosure index.  The archive began in July 2026.  A point-in-time archive
matters because it can show what the public index exposed on a particular day,
rather than silently using information added later.

Today the technical package contains daily Parquet partitions of filing-index
metadata: official document ID, filer name, filing type/year, source and capture
date.  Its human-readable datasheet is `_DATASHEET.md`, intentionally prefixed
so normal `pd.read_parquet` directory reads see only Parquet files. It contains
no Quiver or other paid data.

It is not yet a commercial congressional-trades product.  The current archive
does not parse the individual transaction lines inside PTR PDFs, so it cannot
truthfully claim ticker/date/amount coverage or pass a three-trade official
spot-check.  It also has fewer than 30 real daily vintages and must not claim
history before July 2026.

Recommended next technical gate: retain 30 genuine daily vintages, then add a
document-provenanced official-PTR parser, independently spot-check three parsed
trades against House disclosures, and only then reassess whether the resulting
dataset is worth commercial outreach.  Any contact with potential buyers remains
José's decision; no external contact has been made.
