#!/usr/bin/env python3
"""Export free House disclosure filing-index vintages as daily Parquet.

This intentionally exports only the two official House sources captured in
``altdata_snapshots``.  It does *not* label a filing-index row as a trade: the
current collector has document identifiers and filer metadata, but does not
parse the transaction lines inside PTR PDFs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from app.db.session import SessionLocal  # noqa: E402
from app.models.altdata import AltDataSnapshot  # noqa: E402


FREE_HOUSE_SOURCES = frozenset(
    {
        "house_financial_disclosure_index",
        "house_periodic_transaction_report_index",
    }
)
REQUIRED_COLUMNS = (
    "snapshot_id",
    "captured_at",
    "captured_date",
    "as_of_date",
    "source",
    "content_hash",
    "declared_snapshot_rows",
    "payload_mode",
    "doc_id",
    "first_name",
    "last_name",
    "bioguide_id",
    "filing_type",
    "filing_year",
)
INTEGER_COLUMNS = ("snapshot_id", "declared_snapshot_rows", "filing_year")
STRING_COLUMNS = tuple(column for column in REQUIRED_COLUMNS if column not in INTEGER_COLUMNS)


def _normalise_payload(
    snapshot: AltDataSnapshot, payload: list[dict[str, Any]], *, payload_mode: str
) -> list[dict[str, Any]]:
    """Return explicitly labelled filing-index records for one source vintage."""
    if snapshot.source not in FREE_HOUSE_SOURCES:
        raise ValueError(f"unsupported/non-free source in export: {snapshot.source}")
    if not isinstance(payload, list):
        raise ValueError(
            f"{snapshot.source} snapshot {snapshot.id} payload must be a list, got "
            f"{type(payload).__name__}"
        )

    records: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError(
                f"{snapshot.source} snapshot {snapshot.id} contains a non-object record"
            )
        record = {
            "snapshot_id": snapshot.id,
            "captured_at": snapshot.captured_at.isoformat(),
            "captured_date": snapshot.captured_at.date().isoformat(),
            "as_of_date": snapshot.as_of_date.isoformat(),
            "source": snapshot.source,
            "content_hash": snapshot.content_hash,
            "declared_snapshot_rows": snapshot.n_rows,
            "payload_mode": payload_mode,
            "doc_id": item.get("doc_id"),
            "first_name": item.get("first_name"),
            "last_name": item.get("last_name"),
            "bioguide_id": item.get("bioguide_id"),
            "filing_type": item.get("filing_type"),
            "filing_year": item.get("filing_year"),
        }
        records.append(record)
    return records


def _typed_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Keep every partition schema identical, including all-null fields."""
    frame = pd.DataFrame(records, columns=REQUIRED_COLUMNS)
    for column in STRING_COLUMNS:
        frame[column] = frame[column].astype("string")
    for column in INTEGER_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype("Int64")
    return frame


def export_snapshots(
    snapshots: Iterable[AltDataSnapshot], output_dir: Path, *, replace: bool = False
) -> dict[str, Any]:
    """Write one Parquet file per real capture date and return its manifest."""
    snapshots = list(snapshots)
    unexpected = sorted({snapshot.source for snapshot in snapshots} - FREE_HOUSE_SOURCES)
    if unexpected:
        raise ValueError(f"refusing non-free/unknown sources: {', '.join(unexpected)}")

    by_date: dict[str, list[dict[str, Any]]] = {}
    latest_materialized_payload: dict[str, list[dict[str, Any]]] = {}
    for snapshot in snapshots:
        if snapshot.payload is None:
            payload = latest_materialized_payload.get(snapshot.source)
            if payload is None:
                raise ValueError(
                    f"cannot reconstruct metadata-only {snapshot.source} snapshot "
                    f"{snapshot.id}: no earlier materialized payload"
                )
            payload_mode = "carried_forward_unchanged"
        else:
            payload = snapshot.payload
            if not isinstance(payload, list):
                raise ValueError(
                    f"{snapshot.source} snapshot {snapshot.id} payload must be a list, got "
                    f"{type(payload).__name__}"
                )
            latest_materialized_payload[snapshot.source] = payload
            payload_mode = "materialized"
        for row in _normalise_payload(snapshot, payload, payload_mode=payload_mode):
            by_date.setdefault(row["captured_date"], []).append(row)

    if not by_date:
        raise ValueError("no materialized official House filing-index records to export")

    if output_dir.exists() and replace:
        for child in output_dir.glob("date=*"):
            if child.is_dir():
                shutil.rmtree(child)
    output_dir.mkdir(parents=True, exist_ok=True)

    partitions: list[dict[str, Any]] = []
    for captured_date in sorted(by_date):
        partition_dir = output_dir / f"date={captured_date}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        final_path = partition_dir / "filing_index.parquet"
        temporary_path = partition_dir / "filing_index.parquet.tmp"
        frame = _typed_frame(by_date[captured_date])
        frame.to_parquet(temporary_path, index=False, engine="pyarrow")
        temporary_path.replace(final_path)
        file_sha256 = hashlib.sha256(final_path.read_bytes()).hexdigest()
        partitions.append(
            {
                "captured_date": captured_date,
                "path": str(final_path.relative_to(output_dir)),
                "rows": len(frame),
                "sha256": file_sha256,
                "sources": sorted(frame["source"].dropna().unique().tolist()),
            }
        )

    manifest = {
        "schema_version": 1,
        "dataset": "house_congressional_filing_index_point_in_time",
        "record_granularity": "official House filing-index row, not an individual trade",
        "metadata_only_policy": "repeat the most recent materialized source payload with payload_mode=carried_forward_unchanged",
        "allowed_sources": sorted(FREE_HOUSE_SOURCES),
        "paid_sources_included": [],
        "partitions": partitions,
        "partition_count": len(partitions),
        "row_count": sum(partition["rows"] for partition in partitions),
    }
    # Leading underscore is deliberate: pyarrow dataset discovery ignores it,
    # so ``pd.read_parquet(output_dir)`` sees only parquet partitions.
    (output_dir / "_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        snapshots = (
            db.query(AltDataSnapshot)
            .filter(AltDataSnapshot.source.in_(sorted(FREE_HOUSE_SOURCES)))
            .order_by(AltDataSnapshot.captured_at, AltDataSnapshot.source)
            .all()
        )
        manifest = export_snapshots(snapshots, args.out, replace=args.replace)
    finally:
        db.close()

    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
