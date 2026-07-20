"""Daily, non-retroactive QA for the point-in-time alt-data archive.

The archive proves that collection happened.  The git-tracked JSONL proves
that QA ran on that date.  Historical backfills are useful diagnostics, but
are explicitly ineligible for the seven-independent-runs acceptance gate.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.altdata import AltDataSnapshot
from app.services.equity_coverage import COLLECTORS, SEC_13F_FUNDS, json_safe


QA_LOG_PATH = Path(
    os.environ.get("ALTDATA_QA_LOG_PATH", "/app/reports/altdata_qa_daily.jsonl")
)
HASH_RE = re.compile(r"^[0-9a-f]{64}$")

EXPECTED_SOURCES = frozenset(spec.source for spec in COLLECTORS) | frozenset(
    source for source, _fund in SEC_13F_FUNDS
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _capture_bounds(capture_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(capture_date, time.min)
    return start, start + timedelta(days=1)


def _rows_captured_on(db: Session, capture_date: date) -> list[AltDataSnapshot]:
    start, end = _capture_bounds(capture_date)
    return (
        db.query(AltDataSnapshot)
        .filter(
            AltDataSnapshot.captured_at >= start,
            AltDataSnapshot.captured_at < end,
        )
        .order_by(AltDataSnapshot.source)
        .all()
    )


def _row_evidence(row: AltDataSnapshot) -> dict[str, Any]:
    return {
        "source": row.source,
        "as_of_date": row.as_of_date.isoformat(),
        "captured_at_utc": _as_utc(row.captured_at).isoformat(),
        "n_rows": row.n_rows,
        "content_hash": row.content_hash,
        "payload_materialized": row.payload is not None,
    }


def evaluate_daily_qa(
    db: Session,
    *,
    qa_date: date,
    generated_at_utc: datetime | None = None,
    execution_mode: str = "daily",
) -> dict[str, Any]:
    """Evaluate ``captured_at::date`` coverage without mutating archive data."""
    if execution_mode not in {"daily", "historical_backfill"}:
        raise ValueError(f"unsupported execution_mode={execution_mode!r}")

    generated_at_utc = _as_utc(generated_at_utc or _utc_now())
    current_rows = _rows_captured_on(db, qa_date)
    previous_rows = _rows_captured_on(db, qa_date - timedelta(days=1))
    current_by_source = {row.source: row for row in current_rows}

    snapshot_count = len(current_rows)
    previous_snapshot_count = len(previous_rows) if previous_rows else None
    count_delta = (
        snapshot_count - previous_snapshot_count
        if previous_snapshot_count is not None
        else None
    )
    observed_sources = set(current_by_source)
    missing_sources = sorted(EXPECTED_SOURCES - observed_sources)
    unexpected_sources = sorted(observed_sources - EXPECTED_SOURCES)

    alerts: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if missing_sources:
        alerts.append({"code": "expected_sources_missing", "sources": missing_sources})
    if count_delta is not None and count_delta < 0:
        alerts.append(
            {
                "code": "snapshot_count_drop",
                "previous": previous_snapshot_count,
                "current": snapshot_count,
                "delta": count_delta,
            }
        )
    if unexpected_sources:
        warnings.append({"code": "unexpected_sources", "sources": unexpected_sources})

    source_counts: dict[str, int | None] = {}
    for source in sorted(EXPECTED_SOURCES):
        row = current_by_source.get(source)
        source_counts[source] = row.n_rows if row is not None else None
        if row is None:
            continue
        if row.n_rows <= 0:
            alerts.append({"code": "non_positive_row_count", "source": source})
        if not HASH_RE.fullmatch(row.content_hash or ""):
            alerts.append({"code": "invalid_content_hash", "source": source})
        if _as_utc(row.captured_at).date() != qa_date:
            alerts.append({"code": "capture_timestamp_date_mismatch", "source": source})

    evidence = [_row_evidence(row) for row in current_rows]
    evidence_digest = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    same_day_execution = generated_at_utc.date() == qa_date
    eligible_for_streak = execution_mode == "daily" and same_day_execution
    return {
        "schema_version": 1,
        "run_id": str(uuid4()),
        "qa_date": qa_date.isoformat(),
        "generated_at_utc": generated_at_utc.isoformat(),
        "execution_mode": execution_mode,
        "eligible_for_streak": eligible_for_streak,
        "status": "green" if not alerts else "red",
        "snapshot_count": snapshot_count,
        "previous_snapshot_count": previous_snapshot_count,
        "snapshot_count_delta": count_delta,
        "expected_source_count": len(EXPECTED_SOURCES),
        "observed_source_count": len(observed_sources & EXPECTED_SOURCES),
        "expected_sources": sorted(EXPECTED_SOURCES),
        "observed_sources": sorted(observed_sources),
        "missing_sources": missing_sources,
        "source_counts": source_counts,
        "alerts": alerts,
        "warnings": warnings,
        "source_evidence_sha256": evidence_digest,
        "orders_placed": 0,
        "subscriptions_purchased": 0,
    }


def read_daily_log(log_path: Path = QA_LOG_PATH) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line_number, raw in enumerate(log_path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {log_path}:{line_number}: {exc}") from exc
        if not isinstance(entry, dict):
            raise ValueError(f"non-object JSONL entry at {log_path}:{line_number}")
        entries.append(entry)
    return entries


def write_daily_log_entry(
    payload: dict[str, Any], log_path: Path = QA_LOG_PATH
) -> tuple[dict[str, Any], bool]:
    """Atomically persist exactly one immutable entry per QA date."""
    entries = read_daily_log(log_path)
    qa_date = str(payload["qa_date"])
    existing = [entry for entry in entries if entry.get("qa_date") == qa_date]
    if len(existing) > 1:
        raise ValueError(f"duplicate QA date already present in {log_path}: {qa_date}")
    if existing:
        return existing[0], False

    log_path.parent.mkdir(parents=True, exist_ok=True)
    entries.append(json_safe(payload))
    entries.sort(key=lambda entry: str(entry.get("qa_date", "")))
    tmp = log_path.with_suffix(log_path.suffix + ".tmp")
    tmp.write_text(
        "".join(
            json.dumps(entry, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
            for entry in entries
        ),
        encoding="utf-8",
    )
    tmp.replace(log_path)
    return payload, True


def backfill_existing_dates(
    db: Session,
    *,
    generated_at_utc: datetime | None = None,
    log_path: Path = QA_LOG_PATH,
) -> list[dict[str, Any]]:
    """Backfill diagnostics for prior capture dates; never streak-eligible."""
    generated_at_utc = _as_utc(generated_at_utc or _utc_now())
    capture_dates = sorted(
        {
            _as_utc(row[0]).date()
            for row in db.query(AltDataSnapshot.captured_at).all()
            if row[0] is not None
        }
    )
    written: list[dict[str, Any]] = []
    for capture_date in capture_dates:
        if capture_date >= generated_at_utc.date():
            continue
        payload = evaluate_daily_qa(
            db,
            qa_date=capture_date,
            generated_at_utc=generated_at_utc,
            execution_mode="historical_backfill",
        )
        stored, appended = write_daily_log_entry(payload, log_path)
        written.append(
            {
                "qa_date": capture_date.isoformat(),
                "status": stored["status"],
                "appended": appended,
                "eligible_for_streak": False,
            }
        )
    return written


def run_and_write_daily_qa(
    db: Session,
    *,
    now_utc: datetime | None = None,
    log_path: Path = QA_LOG_PATH,
) -> tuple[dict[str, Any], bool]:
    """Run today's UTC QA once and append its single versioned log line."""
    now_utc = _as_utc(now_utc or _utc_now())
    payload = evaluate_daily_qa(
        db,
        qa_date=now_utc.date(),
        generated_at_utc=now_utc,
        execution_mode="daily",
    )
    return write_daily_log_entry(payload, log_path)


def _committed_log_text(log_path: Path, repo_root: Path) -> str:
    try:
        relative = log_path.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"QA log must be inside repo root: {log_path}") from exc
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"HEAD:{relative.as_posix()}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def verify_green_log_streak(
    log_path: Path,
    *,
    as_of_date: date,
    required_days: int = 7,
    repo_root: Path | None = None,
    committed_only: bool = True,
) -> dict[str, Any]:
    """Require consecutive same-day greens from the committed JSONL only."""
    if required_days < 1:
        raise ValueError("required_days must be >= 1")
    if committed_only:
        if repo_root is None:
            raise ValueError("repo_root is required when committed_only=True")
        raw_entries = _committed_log_text(log_path, repo_root).splitlines()
        entries = [json.loads(raw) for raw in raw_entries if raw.strip()]
    else:
        entries = read_daily_log(log_path)

    by_date: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        by_date.setdefault(str(entry.get("qa_date")), []).append(entry)

    days: list[dict[str, Any]] = []
    for offset in range(required_days - 1, -1, -1):
        expected_day = as_of_date - timedelta(days=offset)
        candidates = by_date.get(expected_day.isoformat(), [])
        valid = []
        for entry in candidates:
            try:
                generated = datetime.fromisoformat(
                    str(entry.get("generated_at_utc", "")).replace("Z", "+00:00")
                )
            except ValueError:
                continue
            if (
                entry.get("status") == "green"
                and entry.get("execution_mode") == "daily"
                and entry.get("eligible_for_streak") is True
                and _as_utc(generated).date() == expected_day
            ):
                valid.append(entry)
        days.append(
            {
                "qa_date": expected_day.isoformat(),
                "status": "green" if len(valid) == 1 and len(candidates) == 1 else "missing_or_invalid",
                "run_id": valid[0].get("run_id") if len(valid) == 1 else None,
            }
        )

    green_days = sum(day["status"] == "green" for day in days)
    return {
        "status": "green" if green_days == required_days else "red",
        "as_of_date": as_of_date.isoformat(),
        "required_days": required_days,
        "green_days": green_days,
        "committed_only": committed_only,
        "days": days,
    }
