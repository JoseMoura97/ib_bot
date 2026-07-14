from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.models.altdata import AltDataSnapshot
from app.services import equity_coverage as coverage
from app.worker import equity_coverage_cli


def test_json_safe_removes_non_finite_values():
    records = coverage.dataframe_records(
        pd.DataFrame([{"ticker": "BRK.B", "put_call": float("nan"), "weight": float("inf")}])
    )
    assert records == [{"ticker": "BRK.B", "put_call": None, "weight": None}]
    json.dumps(records, allow_nan=False)


def test_snapshot_is_idempotent_and_updates_same_day(db_session):
    day = date(2026, 7, 13)
    first = coverage.store_snapshot(db_session, "demo", [{"v": 1}], day)
    db_session.commit()
    second = coverage.store_snapshot(db_session, "demo", [{"v": 1}], day)
    db_session.commit()
    changed = coverage.store_snapshot(db_session, "demo", [{"v": 2}], day)
    db_session.commit()

    assert (first.status, second.status, changed.status) == ("stored", "exists", "updated")
    assert db_session.query(AltDataSnapshot).count() == 1
    assert db_session.query(AltDataSnapshot).one().payload == [{"v": 2}]


def test_capture_all_commits_good_source_when_another_fails(db_session, monkeypatch, tmp_path):
    def good(_):
        return [{"ok": True}]

    def broken(_):
        raise TimeoutError("bounded source timeout")

    monkeypatch.setattr(
        coverage,
        "COLLECTORS",
        (coverage.CollectorSpec("good", good), coverage.CollectorSpec("broken", broken)),
    )
    monkeypatch.setattr(coverage, "SEC_13F_FUNDS", ())
    audit_path = tmp_path / "last_run.json"
    audit = coverage.capture_all(db_session, date(2026, 7, 13), audit_path)

    assert audit["successful_sources"] == 1
    assert audit["failed_sources"] == 1
    assert audit["mandatory_failed_sources"] == 1
    assert db_session.query(AltDataSnapshot).filter_by(source="good").count() == 1
    assert json.loads(audit_path.read_text())["orders_placed"] == 0


def test_sec_daily_index_uses_official_file_name_header(monkeypatch):
    sample = "preamble\nCIK|Company Name|Form Type|Date Filed|File Name\n"
    sample += "1|Issuer|8-K|2026-07-10|edgar/data/1/a.txt\n"
    monkeypatch.setattr(coverage, "_sec_master", lambda _, session=None: sample)

    rows = coverage.collect_sec_daily_filings(date(2026, 7, 13))

    assert rows == [{"cik": "1", "company_name": "Issuer", "form": "8-K",
                     "filed_date": "2026-07-10", "filename": "edgar/data/1/a.txt"}]


def test_sec_403_stops_immediately_with_typed_optional_error(monkeypatch, tmp_path):
    class Response:
        status_code = 403

        def raise_for_status(self):  # pragma: no cover - 403 is handled first
            raise AssertionError("raise_for_status must not be reached")

    class Session:
        def __init__(self):
            self.calls = 0

        def get(self, *_args, **_kwargs):
            self.calls += 1
            return Response()

    session = Session()
    monkeypatch.setattr(coverage, "_sec_master_cache_path", lambda day: tmp_path / f"{day}.idx")

    with pytest.raises(coverage.OptionalExternalSourceError) as raised:
        coverage._sec_master(date(2026, 7, 10), session=session)

    assert raised.value.code == "optional_external_403"
    assert session.calls == 1


def test_sec_daily_index_has_hard_request_budget(monkeypatch):
    requested = []

    def absent(day, session=None):
        requested.append(day)
        return None

    monkeypatch.setattr(coverage, "_sec_master", absent)
    monkeypatch.setattr(coverage, "_session", lambda total_retries=3: object())

    with pytest.raises(coverage.OptionalExternalSourceError) as raised:
        coverage.collect_sec_daily_filings(date(2026, 7, 13))

    assert raised.value.code == "optional_no_published_index"
    assert len(requested) == coverage.SEC_DAILY_REQUEST_BUDGET


def test_house_ptr_collector_keeps_only_periodic_transaction_reports(monkeypatch):
    from annual_fd_parser import AnnualFDIndexEntry

    def entry(doc_id, filing_type):
        return AnnualFDIndexEntry(
            doc_id=doc_id,
            bioguide_id=None,
            first_name="Test",
            last_name="Member",
            filing_year=2026,
            filing_type=filing_type,
        )

    monkeypatch.setattr(
        "annual_fd_parser.fetch_index",
        lambda _year, force=False: [entry("ptr", "P"), entry("annual", "A")],
    )

    rows = coverage.collect_house_periodic_transaction_reports(date(2026, 7, 13))

    assert [row["doc_id"] for row in rows] == ["ptr"]
    assert rows[0]["filing_type"] == "P"


def test_cftc_collector_fetches_exact_latest_official_vintage(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    class Session:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if len(self.calls) == 1:
                return Response([{"latest_report_date": "2026-07-07T00:00:00.000"}])
            return Response([
                {
                    "contract_market_name": "CORN - CHICAGO BOARD OF TRADE",
                    "report_date_as_yyyy_mm_dd": "2026-07-07T00:00:00.000",
                    "open_interest_all": "100",
                }
            ])

    session = Session()
    monkeypatch.setattr(coverage, "_session", lambda total_retries=3: session)

    rows = coverage.collect_cftc_disaggregated_cot(date(2026, 7, 13))

    assert rows[0]["open_interest_all"] == "100"
    assert len(session.calls) == 2
    assert session.calls[0][0] == coverage.CFTC_DISAGGREGATED_FUTURES_URL
    assert session.calls[1][1]["params"]["$where"] == (
        "report_date_as_yyyy_mm_dd='2026-07-07T00:00:00.000'"
    )
    assert session.calls[1][1]["params"]["$limit"] == 5_000


def test_optional_failure_is_visible_but_overall_capture_is_green(db_session, monkeypatch, tmp_path):
    def good(_):
        return [{"ok": True}]

    def sec_denied(_):
        raise coverage.OptionalExternalSourceError("optional_external_403", "denied")

    monkeypatch.setattr(
        coverage,
        "COLLECTORS",
        (
            coverage.CollectorSpec("mandatory_good", good),
            coverage.CollectorSpec("sec_optional", sec_denied, "optional"),
        ),
    )
    monkeypatch.setattr(coverage, "SEC_13F_FUNDS", ())

    audit = coverage.capture_all(db_session, date(2026, 7, 13), tmp_path / "audit.json")

    assert audit["overall_status"] == "ok"
    assert audit["mandatory_failed_sources"] == 0
    assert audit["optional_failed_sources"] == 1
    assert audit["results"][1]["status"] == "optional_external_403"
    assert audit["results"][1]["error_code"] == "optional_external_403"


def test_cli_exit_ignores_optional_failure_but_not_mandatory(monkeypatch, capsys):
    class DummyDB:
        def close(self):
            pass

    base = {
        "successful_sources": 8,
        "failed_sources": 1,
        "mandatory_failed_sources": 0,
        "optional_failed_sources": 1,
        "overall_status": "ok",
        "as_of_date": "2026-07-13",
    }
    monkeypatch.setattr(equity_coverage_cli, "SessionLocal", DummyDB)
    monkeypatch.setattr(equity_coverage_cli, "capture_all", lambda _db: dict(base))
    assert equity_coverage_cli.main() == 0
    capsys.readouterr()

    red = dict(base, mandatory_failed_sources=1, optional_failed_sources=0, overall_status="error")
    monkeypatch.setattr(equity_coverage_cli, "capture_all", lambda _db: red)
    assert equity_coverage_cli.main() == 1


def test_sec_13f_funds_fail_independently(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(coverage, "COLLECTORS", ())
    monkeypatch.setattr(
        coverage,
        "SEC_13F_FUNDS",
        (("sec_13f_scion", "Scion"), ("sec_13f_berkshire", "Berkshire")),
    )

    def fetch(_day, fund):
        if fund == "Scion":
            raise TimeoutError("Scion unavailable")
        return [{"issuer": "Berkshire holding"}]

    monkeypatch.setattr(coverage, "collect_sec_13f_fund", fetch)
    audit = coverage.capture_all(db_session, date(2026, 7, 13), tmp_path / "audit.json")

    assert audit["accounted_sources"] == 2
    assert audit["successful_sources"] == 1
    assert audit["mandatory_failed_sources"] == 1
    assert db_session.query(AltDataSnapshot).filter_by(source="sec_13f_berkshire").count() == 1
    assert db_session.query(AltDataSnapshot).filter_by(source="sec_13f_scion").count() == 0


def test_equity_coverage_has_exactly_one_external_fetch_schedule():
    from app.worker.celery_app import celery_app

    schedules = [
        value for value in celery_app.conf.beat_schedule.values()
        if value.get("task") == "altdata_snapshot_daily_task"
    ]
    assert len(schedules) == 1
    assert set(schedules[0]["schedule"].minute) == {0}
    assert set(schedules[0]["schedule"].hour) == {6}

    repo = Path(__file__).resolve().parents[2]
    assert not (repo / "infra" / "equity-coverage.service").exists()
    assert not (repo / "infra" / "equity-coverage.timer").exists()
