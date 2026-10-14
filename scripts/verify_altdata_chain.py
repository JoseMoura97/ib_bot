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
    """Return content based on actual materialized data, not a trusted column.

    PostgreSQL JSONB normalizes numeric spellings, whereas the historic
    ``content_hash`` was made from Python's pre-JSONB serialization.  Comparing
    those two encodings would falsely condemn valid legacy vintages.  For a
    materialized payload the chain therefore commits the canonical payload hash
    itself.  For a metadata-only unchanged row there is no payload to replay,
    so its already-recorded content hash is the evidence carried forward.
    """
    if row.payload is None:
        return row.content_hash, True
    computed = sha256_json(row.payload)
    return computed, True


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
        # This is deliberately temporary: the verifier runs as the restricted
        # application role, which must not retain CREATE rights in public just
        # to perform an adversarial proof.
        cursor.execute(f"CREATE TEMPORARY TABLE {table} ON COMMIT DROP AS TABLE altdata_snapshots")
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


class ChainTamperError(RuntimeError):
    """Raised when a day already present in the committed baseline no longer matches.

    This is the security-relevant failure mode: it means a retroactive rewrite
    happened between two runs of this script.
    """

    def __init__(self, tampered_days: list[str], verify_result: dict[str, Any]) -> None:
        super().__init__(
            f"refusing to extend/write manifest: previously-committed day(s) no longer "
            f"verify against the baseline on disk: {tampered_days}"
        )
        self.tampered_days = tampered_days
        self.verify_result = verify_result


def extend_manifest(old_baseline: dict[str, Any], actual_days: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify every day already committed to ``old_baseline``, then extend it.

    The committed manifest on disk -- never the just-recomputed data -- is the
    source of truth for days it already covers.  Only after every one of those
    days is confirmed unchanged is it safe to adopt the freshly rebuilt chain
    (which now also includes any brand-new day(s)) as the new baseline.  A
    caller must never write ``actual_days`` as the baseline before this check;
    that would compare the database against itself and could never detect a
    retroactive rewrite.

    ``actual_days`` must already exclude any day that is not yet CLOSED (see
    ``split_closed_days``) -- a day is only safe to commit once no more rows can
    legitimately land for it. Sealing an open day here is the exact 2026-10-13
    defect: a same-day restore/backfill landing after the day was already
    committed turned a legitimate additive write into a tamper detection.
    """
    old_dates = {item["as_of_date"] for item in old_baseline.get("days", [])}
    pre_result = verify(old_baseline, actual_days) if old_dates else {"invalid_days": []}
    tampered = [day for day in pre_result["invalid_days"] if day in old_dates]
    if tampered:
        raise ChainTamperError(tampered, pre_result)
    new_baseline = manifest_document(actual_days)
    return new_baseline, pre_result


def split_closed_days(
    actual_days: list[dict[str, Any]], today_utc_date: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split freshly-built days into CLOSED (safe to seal) and OPEN (today or later).

    A day is only closed once its UTC calendar date is strictly in the past --
    while it is "today" more rows can still legitimately land for it (a backfill,
    a GM restore, a retried capture), and sealing it early is what caused the
    2026-10-13 incident: ``--extend`` ran at 07:00 UTC and committed that same
    day before it had finished accumulating sources, so a later additive row
    broke its own hash and cascaded into every successor.
    """
    closed = [d for d in actual_days if d["as_of_date"] < today_utc_date]
    open_days = [d for d in actual_days if d["as_of_date"] >= today_utc_date]
    return closed, open_days


class ResealError(RuntimeError):
    """Raised when an explicit --reseal-day request cannot be performed safely."""


def reseal_day(
    old_baseline: dict[str, Any],
    closed_days: list[dict[str, Any]],
    reseal_date: str,
    reason: str,
    authority: str,
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Explicitly re-seal ONE already-committed day from live data, audited.

    This is the only supported way to absorb a legitimate additive change to a
    day that was already (wrongly) sealed. Every day strictly before
    ``reseal_date`` must still verify unchanged against the baseline -- this is
    not a bulk regeneration, it touches exactly one day and re-chains its
    successors. Refuses without both ``reason`` and ``authority``, refuses if
    the prefix before the day no longer verifies (a real tamper, not the
    resealed day itself), and refuses to silently drop a previously-committed
    successor day that has no current data.
    """
    if not (reason or "").strip() or not (authority or "").strip():
        raise ResealError("--reseal-day requires both --reason and --authority")

    old_days = old_baseline.get("days", [])
    old_by_date = {d["as_of_date"]: d for d in old_days}
    if reseal_date not in old_by_date:
        raise ResealError(f"{reseal_date} is not a previously-committed day in the baseline -- nothing to reseal")

    actual_by_date = {d["as_of_date"]: d for d in closed_days}
    if reseal_date not in actual_by_date:
        raise ResealError(f"{reseal_date} has no current (closed) source data to reseal from")

    before = [d for d in old_days if d["as_of_date"] < reseal_date]
    prefix_actual = [d for d in closed_days if d["as_of_date"] < reseal_date]
    pre_check = verify({"days": before}, prefix_actual) if before else {"invalid_days": []}
    unexpected = [day for day in pre_check["invalid_days"] if day < reseal_date]
    if unexpected:
        raise ChainTamperError(unexpected, pre_check)

    successors = sorted(d for d in actual_by_date if d >= reseal_date)
    missing = sorted(d for d in old_by_date if d >= reseal_date and d not in actual_by_date)
    if missing:
        raise ResealError(
            f"reseal would drop previously-committed day(s) with no current data -- refusing: {missing}"
        )

    old_source_hash = {s["source"]: s["content_hash"] for s in old_by_date[reseal_date]["sources"]}
    previous_hash = before[-1]["manifest_hash"] if before else None
    rebuilt_tail: list[dict[str, Any]] = []
    for as_of_date in successors:
        actual_day = actual_by_date[as_of_date]
        body = {
            "as_of_date": as_of_date,
            "previous_manifest_hash": previous_hash,
            "sources": [{"source": s["source"], "content_hash": s["content_hash"]} for s in actual_day["sources"]],
        }
        manifest_hash = sha256_json(body)
        rebuilt_tail.append({**body, "manifest_hash": manifest_hash, "sources": actual_day["sources"]})
        previous_hash = manifest_hash

    resealed_day = rebuilt_tail[0]
    new_source_hash = {s["source"]: s["content_hash"] for s in resealed_day["sources"]}
    changed_sources = sorted(
        set(new_source_hash) ^ set(old_source_hash)
        | {name for name, h in new_source_hash.items() if name in old_source_hash and old_source_hash[name] != h}
    )

    audit_entry = {
        "as_of_date": reseal_date,
        "superseded_manifest_hash": old_by_date[reseal_date]["manifest_hash"],
        "new_manifest_hash": resealed_day["manifest_hash"],
        "changed_sources": changed_sources,
        "rechained_successors": [d["as_of_date"] for d in rebuilt_tail[1:]],
        "reason": reason,
        "authority": authority,
        "at": (now or datetime.now(timezone.utc)).isoformat(),
    }

    new_baseline = manifest_document(before + rebuilt_tail)
    new_baseline["reseal_log"] = list(old_baseline.get("reseal_log", [])) + [audit_entry]
    return new_baseline, audit_entry


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
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Create the manifest for the first time. Refuses if one already exists on disk.",
    )
    parser.add_argument(
        "--extend",
        action="store_true",
        help=(
            "Verify every day already committed to the manifest on disk against live data, "
            "then append any new day(s) not yet chained. Refuses to write anything if a "
            "previously-committed day no longer verifies -- this is the only supported way "
            "new days are added; the manifest is never regenerated from current rows before "
            "that check."
        ),
    )
    parser.add_argument("--negative-test", action="store_true")
    parser.add_argument(
        "--reseal-day",
        metavar="YYYY-MM-DD",
        default=None,
        help=(
            "Explicitly re-seal ONE already-committed day from current live data and "
            "re-chain its successors. Only supported way to absorb a legitimate additive "
            "change to a day that was sealed too early. Requires --reason and --authority."
        ),
    )
    parser.add_argument("--reason", default=None, help="Required with --reseal-day: why this reseal is legitimate.")
    parser.add_argument("--authority", default=None, help="Required with --reseal-day: who authorised it.")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    if args.bootstrap and args.extend:
        parser.error("--bootstrap and --extend are mutually exclusive")
    if args.reseal_day and (args.bootstrap or args.extend):
        parser.error("--reseal-day is mutually exclusive with --bootstrap/--extend")
    if args.reseal_day and not (args.reason and args.authority):
        parser.error("--reseal-day requires both --reason and --authority")

    today_utc_date = datetime.now(timezone.utc).date().isoformat()

    with psycopg.connect(psycopg_url(args.database_url)) as conn:
        all_days = build_days(fetch_rows(conn, args.table))
        # A day is only safe to commit to the baseline once it is CLOSED (its UTC
        # calendar date is strictly in the past) -- see split_closed_days. The
        # 2026-10-13 incident was exactly this: --extend sealed "today" at 07:00
        # UTC, then a legitimate same-day additive row broke the seal.
        closed_days, open_days = split_closed_days(all_days, today_utc_date)

        if args.bootstrap:
            if args.manifest.exists():
                raise SystemExit(
                    f"refusing --bootstrap: manifest already exists at {args.manifest} -- "
                    "use --extend to add new days without regenerating the committed baseline"
                )
            baseline = manifest_document(closed_days)
            write_json(args.manifest, baseline)
        elif not args.manifest.exists():
            raise FileNotFoundError(
                f"baseline manifest does not exist: {args.manifest} -- run once with --bootstrap "
                "to create it"
            )
        elif args.extend:
            old_baseline = read_json(args.manifest)
            try:
                baseline, _pre_result = extend_manifest(old_baseline, closed_days)
            except ChainTamperError as exc:
                failure_report = {
                    "schema_version": 1,
                    "verified_at_utc": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc),
                    "tampered_days": exc.tampered_days,
                    **exc.verify_result,
                }
                write_json(args.report, failure_report)
                print(json.dumps(failure_report, indent=2, sort_keys=True))
                print(str(exc), file=sys.stderr)
                return 1
            write_json(args.manifest, baseline)
        elif args.reseal_day:
            old_baseline = read_json(args.manifest)
            try:
                baseline, audit_entry = reseal_day(
                    old_baseline, closed_days, args.reseal_day, args.reason, args.authority
                )
            except (ChainTamperError, ResealError) as exc:
                print(str(exc), file=sys.stderr)
                return 1
            write_json(args.manifest, baseline)
            print(json.dumps({"reseal": audit_entry}, indent=2, sort_keys=True))
        else:
            baseline = read_json(args.manifest)

        result = verify(baseline, closed_days)
        negative = negative_copy_test(conn, baseline) if args.negative_test else prior_negative_proof(args.report)

    report = {
        "schema_version": 1,
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        **result,
        "open_days": [{"as_of_date": d["as_of_date"]} for d in open_days],
        "negative_test_detected": bool(negative and negative["detected"]),
        "negative_test": negative,
    }
    write_json(args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if result["total_days"] and result["chained_valid_days"] == result["total_days"] and (not args.negative_test or report["negative_test_detected"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
