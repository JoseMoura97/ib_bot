#!/usr/bin/env python3
"""Build and independently verify the append-only alt-data hash chain.

The committed manifest is the baseline.  Verification recomputes every
materialized payload hash from the database, rebuilds the chain from that data,
and compares it to the baseline.  A changed vintage therefore invalidates its
own day and every successor, even if an attacker also changed ``content_hash``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import psycopg


REPO = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO / "reports" / "altdata_chain_manifest.json"
DEFAULT_REPORT = REPO / "reports" / "altdata_chain_verify.json"
TABLE_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class SnapshotRow:
    as_of_date: str
    source: str
    content_hash: str
    payload: Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def actual_source_hash(row: SnapshotRow) -> tuple[str, bool]:
    """Return content based on actual materialized data, not a trusted column."""
    if row.payload is None:
        return row.content_hash, True
    computed = sha256_json(row.payload)
    return computed, computed == row.content_hash


def build_days(rows: Iterable[SnapshotRow]) -> list[dict[str, Any]]:
    grouped: dict[str, list[SnapshotRow]] = {}
    for row in rows:
        grouped.setdefault(row.as_of_date, []).append(row)

    previous_hash: str | None = None
    days: list[dict[str, Any]] = []
    for as_of_date in sorted(grouped):
        sources = []
        for row in sorted(grouped[as_of_date], key=lambda item: item.source):
            source_hash, stored_hash_matches_payload = actual_source_hash(row)
            sources.append(
                {
                    "source": row.source,
                    "content_hash": source_hash,
                    "stored_hash_matches_payload": stored_hash_matches_payload,
                }
            )
        body = {
            "as_of_date": as_of_date,
            "previous_manifest_hash": previous_hash,
            "sources": [{"source": item["source"], "content_hash": item["content_hash"]} for item in sources],
        }
        manifest_hash = sha256_json(body)
        days.append({**body, "manifest_hash": manifest_hash, "sources": sources})
        previous_hash = manifest_hash
    return days


def manifest_document(days: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_days": len(days),
        "top_manifest_hash": days[-1]["manifest_hash"] if days else None,
        "days": days,
    }


def verify(expected: dict[str, Any], actual_days: list[dict[str, Any]]) -> dict[str, Any]:
    expected_days = expected.get("days", [])
    expected_by_date = {item["as_of_date"]: item for item in expected_days}
    actual_dates = {item["as_of_date"] for item in actual_days}
    invalid_days: list[str] = []
    details: list[dict[str, Any]] = []
    for actual in actual_days:
        date_key = actual["as_of_date"]
        baseline = expected_by_date.get(date_key)
        source_hashes_ok = all(item["stored_hash_matches_payload"] for item in actual["sources"])
        valid = bool(baseline) and source_hashes_ok and (
            baseline["manifest_hash"] == actual["manifest_hash"]
            and baseline.get("previous_manifest_hash") == actual.get("previous_manifest_hash")
        )
        if not valid:
            invalid_days.append(date_key)
        details.append(
            {
                "as_of_date": date_key,
                "valid": valid,
                "expected_manifest_hash": baseline.get("manifest_hash") if baseline else None,
                "actual_manifest_hash": actual["manifest_hash"],
                "source_hashes_ok": source_hashes_ok,
            }
        )
    unexpected_baseline_days = sorted(set(expected_by_date) - actual_dates)
    invalid_days.extend(unexpected_baseline_days)
    return {
        "total_days": len(actual_days),
        "chained_valid_days": len(actual_days) - len(invalid_days),
        "invalid_days": invalid_days,
        "top_manifest_hash": actual_days[-1]["manifest_hash"] if actual_days else None,
        "baseline_top_manifest_hash": expected.get("top_manifest_hash"),
        "days": details,
    }


def _table_name(value: str) -> str:
    if not TABLE_RE.fullmatch(value):
        raise ValueError(f"unsafe table name: {value!r}")
    return value


def fetch_rows(conn: psycopg.Connection, table: str) -> list[SnapshotRow]:
    table = _table_name(table)
    with conn.cursor() as cursor:
        cursor.execute(
            f"SELECT as_of_date::text, source, content_hash, payload FROM {table} ORDER BY as_of_date, source"
        )
        return [SnapshotRow(*row) for row in cursor.fetchall()]


def negative_copy_test(conn: psycopg.Connection, expected: dict[str, Any]) -> dict[str, Any]:
    table = "altdata_snapshots_chain_negative"
    with conn.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {table}")
        cursor.execute(f"CREATE TABLE {table} AS TABLE altdata_snapshots")
        cursor.execute(
            f"SELECT id, as_of_date::text FROM {table} WHERE payload IS NOT NULL "
            "ORDER BY as_of_date, source OFFSET (SELECT count(*) / 2 FROM altdata_snapshots) LIMIT 1"
        )
        target = cursor.fetchone()
        if target is None:
            raise RuntimeError("negative test requires a materialized payload")
        target_id, target_date = target
        cursor.execute(
            f"UPDATE {table} SET payload = payload || '{{\"__chain_negative_test\":true}}'::jsonb WHERE id = %s",
            (target_id,),
        )
    result = verify(expected, build_days(fetch_rows(conn, table)))
    with conn.cursor() as cursor:
        cursor.execute(f"DROP TABLE {table}")
    expected_invalid = [
        item["as_of_date"] for item in expected["days"] if item["as_of_date"] >= target_date
    ]
    detected = result["invalid_days"] == expected_invalid
    return {
        "target_day": target_date,
        "invalid_days": result["invalid_days"],
        "expected_invalid_days": expected_invalid,
        "detected": detected,
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def psycopg_url(database_url: str) -> str:
    """Convert the service's SQLAlchemy URL to psycopg's native spelling."""
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def prior_negative_proof(report_path: Path) -> dict[str, Any] | None:
    """Keep a proven adversarial receipt when routine daily verification runs."""
    if not report_path.exists():
        return None
    previous = read_json(report_path)
    proof = previous.get("negative_test")
    if previous.get("negative_test_detected") is True and isinstance(proof, dict) and proof.get("detected") is True:
        return proof
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--table", default="altdata_snapshots")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--negative-test", action="store_true")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")

    with psycopg.connect(psycopg_url(args.database_url)) as conn:
        actual_days = build_days(fetch_rows(conn, args.table))
        if args.write_manifest:
            expected = manifest_document(actual_days)
            write_json(args.manifest, expected)
        elif not args.manifest.exists():
            raise FileNotFoundError(f"baseline manifest does not exist: {args.manifest}")
        else:
            expected = read_json(args.manifest)
        result = verify(expected, actual_days)
        negative = negative_copy_test(conn, expected) if args.negative_test else prior_negative_proof(args.report)

    report = {
        "schema_version": 1,
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        **result,
        "negative_test_detected": bool(negative and negative["detected"]),
        "negative_test": negative,
    }
    write_json(args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if result["total_days"] and result["chained_valid_days"] == result["total_days"] and (not args.negative_test or report["negative_test_detected"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
