"""Durable, non-IB equity and alternative-data coverage.

Every source is fetched independently, normalized to strict JSON, and committed
independently.  This matters: a malformed value in one source must never roll
back point-in-time vintages already captured from another source.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from sqlalchemy.orm import Session
from urllib3.util.retry import Retry

from app.models.altdata import AltDataSnapshot


CACHE = Path(os.environ.get("EQUITY_COVERAGE_CACHE", "/app/.cache/equity_coverage"))
AUDIT_PATH = CACHE / "last_run.json"
USER_AGENT = os.environ.get(
    "EQUITY_COVERAGE_USER_AGENT", "ib_bot equity research josemiguelmoura97@gmail.com"
)
NASDAQ_URLS = (
    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
)
CFTC_DISAGGREGATED_FUTURES_URL = (
    "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
)
FRED_SERIES = ("SP500", "VIXCLS", "DGS10", "DGS2", "BAMLH0A0HYM2", "DTWEXBGS")
SEC_FORMS = {
    "4", "8-K", "8-K/A", "10-Q", "10-Q/A", "10-K", "10-K/A", "6-K",
    "20-F", "13F-HR", "13F-HR/A", "SC 13D", "SC 13G", "S-1", "DEF 14A",
}
IRON_WING_UNIVERSE = Path(__file__).with_name("iron_wing_universe.txt")


@dataclass
class CaptureResult:
    source: str
    status: str
    criticality: str = "mandatory"
    n_rows: int = 0
    content_hash: str | None = None
    elapsed_seconds: float = 0.0
    error_code: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class CollectorSpec:
    source: str
    collector: Callable[[date], Any]
    criticality: str = "mandatory"


class OptionalExternalSourceError(RuntimeError):
    """A typed, visible failure that must not make the daily job red."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


SUCCESS_STATUSES = frozenset(("stored", "exists", "updated", "unchanged"))
SEC_DAILY_REQUEST_BUDGET = 3
SEC_CONNECT_TIMEOUT_SECONDS = 3
SEC_READ_TIMEOUT_SECONDS = 8


def _session(total_retries: int = 3) -> requests.Session:
    retry = Retry(
        total=total_retries,
        connect=total_retries,
        read=total_retries,
        backoff_factor=0.75,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET", "POST")),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def json_safe(value: Any) -> Any:
    """Return strict-JSON-compatible Python values (NaN/Inf become null)."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except (ValueError, TypeError):
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def dataframe_records(df: pd.DataFrame | None, cap: int = 20_000) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    return json_safe(df.head(cap).to_dict(orient="records"))


def store_snapshot(db: Session, source: str, records: list[dict[str, Any]], as_of: date) -> CaptureResult:
    """Upsert one daily vintage; identical reruns are idempotent."""
    records = json_safe(records)
    if not records:
        raise ValueError(f"{source}: empty payload is not a successful capture")
    body = json.dumps(records, default=str, sort_keys=True, separators=(",", ":"), allow_nan=False)
    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    existing = (
        db.query(AltDataSnapshot)
        .filter(AltDataSnapshot.source == source, AltDataSnapshot.as_of_date == as_of)
        .one_or_none()
    )
    if existing is not None:
        if existing.content_hash == content_hash:
            return CaptureResult(source, "exists", n_rows=len(records), content_hash=content_hash)
        existing.n_rows = len(records)
        existing.content_hash = content_hash
        existing.payload = records
        existing.captured_at = datetime.utcnow()
        return CaptureResult(source, "updated", n_rows=len(records), content_hash=content_hash)

    previous = (
        db.query(AltDataSnapshot)
        .filter(AltDataSnapshot.source == source)
        .order_by(AltDataSnapshot.as_of_date.desc())
        .first()
    )
    unchanged = previous is not None and previous.content_hash == content_hash
    db.add(
        AltDataSnapshot(
            source=source,
            as_of_date=as_of,
            n_rows=len(records),
            content_hash=content_hash,
            payload=None if unchanged else records,
        )
    )
    return CaptureResult(
        source,
        "unchanged" if unchanged else "stored",
        n_rows=len(records),
        content_hash=content_hash,
    )


def collect_nasdaq_directory(_: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    session = _session()
    for url in NASDAQ_URLS:
        response = session.get(url, timeout=(10, 40))
        response.raise_for_status()
        lines = response.text.splitlines()
        if not lines:
            continue
        parsed = list(csv.DictReader(lines, delimiter="|"))
        for row in parsed:
            symbol = (row.get("Symbol") or row.get("ACT Symbol") or "").strip()
            if not symbol or symbol.startswith("File Creation Time") or row.get("Test Issue") == "Y":
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "security_name": row.get("Security Name"),
                    "exchange": row.get("Exchange") or "NASDAQ",
                    "market_category": row.get("Market Category"),
                    "financial_status": row.get("Financial Status"),
                    "etf": row.get("ETF") == "Y",
                    "round_lot_size": row.get("Round Lot Size"),
                    "nextshares": row.get("NextShares") == "Y",
                }
            )
    return rows


def collect_equity_daily_bars(as_of: date) -> list[dict[str, Any]]:
    """Recent adjusted/raw OHLCV and actions for the fixed Iron Wing universe.

    Yahoo is used only as a free research feed; no IB market-data request is
    made.  Chunking and a single bounded retry avoid a rate-limit storm.
    """
    import yfinance as yf

    cache_path = CACHE / "equity_daily_bars" / f"{as_of.isoformat()}.json"
    if cache_path.exists() and cache_path.stat().st_size > 100:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    symbols = [
        line.strip().upper() for line in IRON_WING_UNIVERSE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    records: list[dict[str, Any]] = []
    for start in range(0, len(symbols), 80):
        chunk = symbols[start : start + 80]
        frame = pd.DataFrame()
        for attempt in range(2):
            frame = yf.download(
                chunk,
                period="14d",
                interval="1d",
                auto_adjust=False,
                actions=True,
                progress=False,
                threads=False,
                timeout=30,
            )
            if not frame.empty:
                break
            if attempt == 0:
                time.sleep(2)
        if frame.empty:
            continue
        if isinstance(frame.columns, pd.MultiIndex):
            available = set(frame.columns.get_level_values(1))
            for symbol in chunk:
                if symbol not in available:
                    continue
                one = frame.xs(symbol, axis=1, level=1).reset_index()
                one["symbol"] = symbol
                records.extend(dataframe_records(one))
        else:
            one = frame.reset_index()
            one["symbol"] = chunk[0]
            records.extend(dataframe_records(one))
    if records:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(json_safe(records), separators=(",", ":"), allow_nan=False), encoding="utf-8")
        temporary.replace(cache_path)
    return records


def collect_finra_short(as_of: date) -> list[dict[str, Any]]:
    from finra_short import FinraShortVolume

    frame = FinraShortVolume(user_agent=USER_AGENT).get_window(
        end_date=datetime.combine(as_of, datetime.min.time()),
        lookback_days=1,
        min_avg_volume=0,
        common_stock_only=True,
    )
    return dataframe_records(frame)


def collect_house_disclosures(as_of: date) -> list[dict[str, Any]]:
    from annual_fd_parser import fetch_index

    entries = fetch_index(as_of.year, force=True)
    return json_safe([asdict(entry) for entry in entries])


def collect_house_periodic_transaction_reports(as_of: date) -> list[dict[str, Any]]:
    """Archive the official House index rows that identify disclosed trades.

    Filing type ``P`` is a Periodic Transaction Report (PTR).  This is the
    free, point-in-time congressional-trades source available in the current
    codebase; the rows identify the official filings but do not pretend that
    the individual PDF transaction lines have already been parsed.
    """
    from annual_fd_parser import fetch_index

    # The full House index collector runs immediately before this source and
    # refreshes the shared cache. Reuse it to avoid a duplicate download.
    entries = fetch_index(as_of.year, force=False)
    return json_safe([asdict(entry) for entry in entries if entry.filing_type == "P"])


def _sec_master_cache_path(day: date) -> Path:
    return CACHE / "sec_daily_index" / f"master.{day:%Y%m%d}.idx"


def _sec_master(day: date, session: requests.Session | None = None) -> str | None:
    """Return one SEC master index, preserving access denial as a typed error.

    A 404/503 can mean that a daily index has not yet been published.  A 403 is
    different: it is an access denial, so walking backwards through more dates
    only multiplies traffic and runtime.  It therefore stops the source on the
    first response and is surfaced as ``optional_external_403``.
    """
    path = _sec_master_cache_path(day)
    if path.exists() and path.stat().st_size > 100:
        return path.read_text(encoding="latin-1")
    quarter = (day.month - 1) // 3 + 1
    url = f"https://www.sec.gov/Archives/edgar/daily-index/{day.year}/QTR{quarter}/master.{day:%Y%m%d}.idx"
    try:
        response = (session or _session(total_retries=0)).get(
            url,
            timeout=(SEC_CONNECT_TIMEOUT_SECONDS, SEC_READ_TIMEOUT_SECONDS),
        )
    except requests.RequestException as exc:
        raise OptionalExternalSourceError(
            "optional_external_timeout", f"SEC daily index request failed: {type(exc).__name__}"
        ) from exc
    if response.status_code == 403:
        raise OptionalExternalSourceError(
            "optional_external_403", f"SEC denied daily-index access for {day.isoformat()}"
        )
    if response.status_code in (404, 503):
        return None
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return response.content.decode("latin-1")


def collect_sec_daily_filings(as_of: date) -> list[dict[str, Any]]:
    # At the 05:00 UTC collection time the current-day index does not exist yet.
    # Start at the previous day and walk to the latest published business day.
    session = _session(total_retries=0)
    requests_used = 0
    for offset in range(1, 12):
        day = as_of - timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        if requests_used >= SEC_DAILY_REQUEST_BUDGET:
            break
        requests_used += 1
        text = _sec_master(day, session=session)
        if not text:
            continue
        body = text.split("CIK|Company Name|Form Type|Date Filed|File Name", 1)
        if len(body) != 2:
            continue
        rows = []
        for line in body[1].splitlines():
            parts = line.strip().split("|")
            if len(parts) != 5 or parts[2] not in SEC_FORMS:
                continue
            rows.append(
                {"cik": parts[0], "company_name": parts[1], "form": parts[2],
                 "filed_date": parts[3], "filename": parts[4]}
            )
        if rows:
            return rows
    raise OptionalExternalSourceError(
        "optional_no_published_index",
        f"SEC daily index absent after {requests_used} bounded business-day requests",
    )


SEC_13F_FUNDS: tuple[tuple[str, str], ...] = (
    ("sec_13f_scion_asset_management", "Scion Asset Management"),
    ("sec_13f_berkshire_hathaway", "Berkshire Hathaway"),
)


def collect_sec_13f_fund(_: date, fund: str) -> list[dict[str, Any]]:
    """Fetch one fund with its own client and transaction boundary."""
    import sec_edgar

    client = sec_edgar.SECEdgarClient()
    return dataframe_records(client.get_latest_holdings(fund))


def collect_fred_regime(_: date) -> list[dict[str, Any]]:
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + ",".join(FRED_SERIES)
    response = _session().get(url, timeout=(10, 40))
    response.raise_for_status()
    # FRED returns a ZIP containing one CSV per series when multiple ids are
    # requested.  Preserve a tidy series/date/value shape.
    frames: list[pd.DataFrame] = []
    if response.content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            for name in archive.namelist():
                if not name.lower().endswith(".csv"):
                    continue
                frame = pd.read_csv(archive.open(name))
                if frame.empty:
                    continue
                value_columns = [c for c in frame.columns if c.upper() in FRED_SERIES]
                if not value_columns:
                    continue
                date_column = frame.columns[0]
                for series in value_columns:
                    part = frame[[date_column, series]].tail(40).copy()
                    part.columns = ["date", "value"]
                    part["series"] = series.upper()
                    frames.append(part)
    else:
        frame = pd.read_csv(io.StringIO(response.text))
        if not frame.empty:
            date_column = frame.columns[0]
            for series in [c for c in frame.columns[1:] if c.upper() in FRED_SERIES]:
                part = frame[[date_column, series]].tail(40).copy()
                part.columns = ["date", "value"]
                part["series"] = series.upper()
                frames.append(part)
    if not frames:
        return []
    return dataframe_records(pd.concat(frames, ignore_index=True).replace(".", None))


def collect_usaspending_awards(as_of: date) -> list[dict[str, Any]]:
    """Recent federal awards; one bounded official API page, cached as a vintage."""
    payload = {
        "filters": {
            "time_period": [{"start_date": (as_of - timedelta(days=7)).isoformat(), "end_date": as_of.isoformat()}],
            "award_type_codes": ["A", "B", "C", "D"],
        },
        "fields": ["Award ID", "Recipient Name", "Start Date", "End Date", "Award Amount",
                   "Awarding Agency", "Awarding Sub Agency", "Contract Award Type", "Description"],
        "page": 1,
        "limit": 100,
        "subawards": False,
    }
    response = _session().post(
        "https://api.usaspending.gov/api/v2/search/spending_by_award/",
        json=payload,
        timeout=(10, 60),
    )
    response.raise_for_status()
    return json_safe(response.json().get("results", []))


def collect_cftc_disaggregated_cot(_: date) -> list[dict[str, Any]]:
    """Fetch the latest free CFTC Disaggregated Futures-Only COT vintage.

    The official Socrata dataset is queried twice: one aggregate request finds
    the latest published report date, and one bounded request retrieves that
    exact weekly vintage.  No application token or paid provider is used.
    """
    session = _session()
    latest_response = session.get(
        CFTC_DISAGGREGATED_FUTURES_URL,
        params={"$select": "max(report_date_as_yyyy_mm_dd) as latest_report_date"},
        timeout=(10, 30),
    )
    latest_response.raise_for_status()
    latest_payload = latest_response.json()
    latest = latest_payload[0].get("latest_report_date") if latest_payload else None
    if not isinstance(latest, str) or not latest:
        raise ValueError("CFTC COT latest report date is absent")

    report_response = session.get(
        CFTC_DISAGGREGATED_FUTURES_URL,
        params={
            "$where": f"report_date_as_yyyy_mm_dd='{latest}'",
            "$order": "contract_market_name ASC",
            "$limit": 5_000,
        },
        timeout=(10, 60),
    )
    report_response.raise_for_status()
    rows = report_response.json()
    if not isinstance(rows, list):
        raise ValueError("CFTC COT response is not a record list")
    return json_safe(rows)


COLLECTORS: tuple[CollectorSpec, ...] = (
    CollectorSpec("nasdaq_symbol_directory", collect_nasdaq_directory),
    CollectorSpec("iron_wing_equity_daily_bars", collect_equity_daily_bars),
    CollectorSpec("finra_offexchange_short_volume", collect_finra_short),
    CollectorSpec("house_financial_disclosure_index", collect_house_disclosures),
    CollectorSpec("house_periodic_transaction_report_index", collect_house_periodic_transaction_reports),
    CollectorSpec("sec_daily_material_filings", collect_sec_daily_filings, "optional"),
    CollectorSpec("fred_market_regime", collect_fred_regime),
    CollectorSpec("usaspending_recent_contract_awards", collect_usaspending_awards),
    CollectorSpec("cftc_disaggregated_futures_cot", collect_cftc_disaggregated_cot),
)


def _write_audit(payload: dict[str, Any], path: Path = AUDIT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    tmp.replace(path)


def capture_all(db: Session, as_of: date | None = None, audit_path: Path = AUDIT_PATH) -> dict[str, Any]:
    """Capture all sources with per-source transaction boundaries and audit evidence."""
    as_of = as_of or date.today()
    started = datetime.now(timezone.utc)
    results: list[CaptureResult] = []

    for spec in COLLECTORS:
        source, collector = spec.source, spec.collector
        t0 = time.monotonic()
        try:
            records = collector(as_of)
            result = store_snapshot(db, source, records, as_of)
            result.criticality = spec.criticality
            db.commit()
            result.elapsed_seconds = round(time.monotonic() - t0, 3)
            results.append(result)
        except OptionalExternalSourceError as exc:
            db.rollback()
            results.append(
                CaptureResult(
                    source,
                    exc.code if spec.criticality == "optional" else "error",
                    criticality=spec.criticality,
                    elapsed_seconds=round(time.monotonic() - t0, 3),
                    error_code=exc.code,
                    error=str(exc)[:500],
                )
            )
        except Exception as exc:  # one failed source never poisons the rest
            db.rollback()
            results.append(
                CaptureResult(
                    source,
                    "optional_error" if spec.criticality == "optional" else "error",
                    criticality=spec.criticality,
                    elapsed_seconds=round(time.monotonic() - t0, 3),
                    error_code="optional_external_error" if spec.criticality == "optional" else "source_error",
                    error=f"{type(exc).__name__}: {str(exc)[:500]}",
                )
            )

    # Each tracked 13F fund is its own independently committed vintage.
    for source, fund in SEC_13F_FUNDS:
        fund_t0 = time.monotonic()
        try:
            records = collect_sec_13f_fund(as_of, fund)
            result = store_snapshot(db, source, records, as_of)
            db.commit()
            result.elapsed_seconds = round(time.monotonic() - fund_t0, 3)
            results.append(result)
        except Exception as exc:
            db.rollback()
            results.append(
                CaptureResult(
                    source,
                    "error",
                    elapsed_seconds=round(time.monotonic() - fund_t0, 3),
                    error_code="source_error",
                    error=f"{type(exc).__name__}: {str(exc)[:500]}",
                )
            )

    successful = [r for r in results if r.status in SUCCESS_STATUSES]
    mandatory_failed = [r for r in results if r.criticality == "mandatory" and r.status not in SUCCESS_STATUSES]
    optional_failed = [r for r in results if r.criticality == "optional" and r.status not in SUCCESS_STATUSES]
    audit = {
        "schema_version": 1,
        "run_started_utc": started.isoformat(),
        "run_finished_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": as_of.isoformat(),
        "mode": "research_only_non_trading",
        "ib_requests": 0,
        "orders_placed": 0,
        "subscriptions_purchased": 0,
        "expected_sources": len(COLLECTORS) + len(SEC_13F_FUNDS),
        "accounted_sources": len(results),
        "successful_sources": len(successful),
        "failed_sources": len(results) - len(successful),
        "mandatory_failed_sources": len(mandatory_failed),
        "optional_failed_sources": len(optional_failed),
        "overall_status": "ok" if not mandatory_failed else "error",
        "source_notes": {
            "quiver_congress_trades": "excluded: bulk endpoint timed out and requires licensed/API-key access; no silent replacement",
            "house_financial_disclosure_index": "index metadata only; does not parse every filing attachment or holding",
            "house_periodic_transaction_report_index": "official free PTR filing metadata; PDF transaction lines are not parsed",
        },
        "results": [asdict(r) for r in results],
    }
    _write_audit(audit, audit_path)
    return audit
