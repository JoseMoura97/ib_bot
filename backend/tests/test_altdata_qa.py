from __future__ import annotations

import json
import subprocess
from datetime import date, datetime, timedelta, timezone

from app.models.altdata import AltDataSnapshot
from app.services import equity_coverage as coverage
from app.services.altdata_qa import (
    EXPECTED_SOURCES,
    backfill_existing_dates,
    run_and_write_daily_qa,
    verify_green_log_streak,
)


def _seed_day(db_session, day: date, *, omit: set[str] | None = None, n_rows: int = 100):
    omit = omit or set()
    for source in sorted(EXPECTED_SOURCES - omit):
        coverage.store_snapshot(db_session, source, [{"row": i} for i in range(n_rows)], day)
        db_session.flush()
        row = (
            db_session.query(AltDataSnapshot)
            .filter(
                AltDataSnapshot.source == source,
                AltDataSnapshot.as_of_date == day,
            )
            .one()
        )
        row.captured_at = datetime(day.year, day.month, day.day, 6, 0)
    db_session.commit()


def test_daily_qa_logs_count_delta_and_expected_sources(db_session, tmp_path):
    _seed_day(db_session, date(2026, 7, 19))
    _seed_day(db_session, date(2026, 7, 20))
    log_path = tmp_path / "reports" / "altdata_qa_daily.jsonl"

    payload, appended = run_and_write_daily_qa(
        db_session,
        now_utc=datetime(2026, 7, 20, 7, 0, tzinfo=timezone.utc),
        log_path=log_path,
    )

    assert appended is True
    assert payload["status"] == "green"
    assert payload["eligible_for_streak"] is True
    assert payload["snapshot_count"] == len(EXPECTED_SOURCES)
    assert payload["previous_snapshot_count"] == len(EXPECTED_SOURCES)
    assert payload["snapshot_count_delta"] == 0
    assert payload["missing_sources"] == []
    assert len(log_path.read_text().splitlines()) == 1


def test_daily_qa_alerts_when_source_and_count_drop(db_session, tmp_path):
    missing = next(iter(EXPECTED_SOURCES))
    _seed_day(db_session, date(2026, 7, 19))
    _seed_day(db_session, date(2026, 7, 20), omit={missing})

    payload, _appended = run_and_write_daily_qa(
        db_session,
        now_utc=datetime(2026, 7, 20, 7, 0, tzinfo=timezone.utc),
        log_path=tmp_path / "qa.jsonl",
    )

    assert payload["status"] == "red"
    assert payload["snapshot_count_delta"] == -1
    assert payload["missing_sources"] == [missing]
    assert {alert["code"] for alert in payload["alerts"]} >= {
        "expected_sources_missing",
        "snapshot_count_drop",
    }


def test_historical_backfill_is_persisted_but_never_streak_eligible(db_session, tmp_path):
    for offset in range(8):
        _seed_day(db_session, date(2026, 7, 13) + timedelta(days=offset))
    log_path = tmp_path / "qa.jsonl"

    result = backfill_existing_dates(
        db_session,
        generated_at_utc=datetime(2026, 7, 20, 7, 0, tzinfo=timezone.utc),
        log_path=log_path,
    )

    entries = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert len(result) == 7
    assert len(entries) == 7
    assert all(entry["execution_mode"] == "historical_backfill" for entry in entries)
    assert all(entry["eligible_for_streak"] is False for entry in entries)


def test_streak_reads_head_and_rejects_uncommitted_or_backfilled_rows(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "qa@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "QA Test"], check=True)
    log_path = repo / "reports" / "altdata_qa_daily.jsonl"
    log_path.parent.mkdir()
    as_of = date(2026, 7, 20)
    committed = []
    for offset in range(6, 0, -1):
        qa_day = as_of - timedelta(days=offset)
        committed.append(
            {
                "run_id": f"backfill-{offset}",
                "qa_date": qa_day.isoformat(),
                "generated_at_utc": datetime(2026, 7, 20, 7, offset, tzinfo=timezone.utc).isoformat(),
                "execution_mode": "historical_backfill",
                "eligible_for_streak": False,
                "status": "green",
            }
        )
    log_path.write_text("".join(json.dumps(item) + "\n" for item in committed))
    subprocess.run(["git", "-C", str(repo), "add", "reports/altdata_qa_daily.jsonl"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "backfill"], check=True)

    today = {
        "run_id": "daily-today",
        "qa_date": as_of.isoformat(),
        "generated_at_utc": datetime(2026, 7, 20, 7, 0, tzinfo=timezone.utc).isoformat(),
        "execution_mode": "daily",
        "eligible_for_streak": True,
        "status": "green",
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(today) + "\n")

    streak = verify_green_log_streak(
        log_path,
        as_of_date=as_of,
        required_days=7,
        repo_root=repo,
        committed_only=True,
    )
    assert streak["status"] == "red"
    assert streak["green_days"] == 0

    subprocess.run(["git", "-C", str(repo), "add", "reports/altdata_qa_daily.jsonl"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "daily"], check=True)
    streak = verify_green_log_streak(
        log_path,
        as_of_date=as_of,
        required_days=7,
        repo_root=repo,
        committed_only=True,
    )
    assert streak["status"] == "red"
    assert streak["green_days"] == 1
