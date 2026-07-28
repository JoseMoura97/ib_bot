from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from app.models.altdata import AltDataSnapshot

from scripts.export_congress_pit import FREE_HOUSE_SOURCES, REQUIRED_COLUMNS, export_snapshots


def _snapshot(source: str, captured: datetime, payload: list[dict], *, snapshot_id: int = 1):
    return AltDataSnapshot(
        id=snapshot_id,
        source=source,
        as_of_date=captured.date(),
        captured_at=captured,
        n_rows=len(payload),
        content_hash="a" * 64,
        payload=payload,
    )


def test_export_writes_free_source_daily_partitions(tmp_path):
    ptr = _snapshot(
        "house_periodic_transaction_report_index",
        datetime(2026, 7, 20, 6, 0),
        [
            {
                "doc_id": "20034201",
                "first_name": "Mark",
                "last_name": "Alford",
                "bioguide_id": None,
                "filing_type": "P",
                "filing_year": 2026,
            }
        ],
    )
    index = _snapshot(
        "house_financial_disclosure_index",
        datetime(2026, 7, 21, 6, 0),
        [
            {
                "doc_id": "20035000",
                "first_name": "Ada",
                "last_name": "Example",
                "bioguide_id": "E000000",
                "filing_type": "P",
                "filing_year": 2026,
            }
        ],
        snapshot_id=2,
    )

    manifest = export_snapshots([ptr, index], tmp_path / "congress_pit")

    assert manifest["partition_count"] == 2
    assert manifest["paid_sources_included"] == []
    assert manifest["record_granularity"] == "official House filing-index row, not an individual trade"
    frame = pd.read_parquet(tmp_path / "congress_pit")
    assert set(frame.columns) == {*REQUIRED_COLUMNS, "date"}
    assert set(frame["date"].astype(str)) == {"2026-07-20", "2026-07-21"}
    assert frame["source"].isin(FREE_HOUSE_SOURCES).all()
    assert "ticker" not in frame.columns
    assert set(frame["doc_id"]) == {"20034201", "20035000"}


def test_export_rejects_non_free_source(tmp_path):
    quiver = _snapshot(
        "quiver_congress_trades",
        datetime(2026, 7, 20, 6, 0),
        [{"doc_id": "paid"}],
    )
    with pytest.raises(ValueError, match="non-free/unknown"):
        export_snapshots([quiver], tmp_path / "congress_pit")


def test_export_reconstructs_metadata_only_snapshot_from_prior_vintage(tmp_path):
    first = _snapshot(
        "house_periodic_transaction_report_index",
        datetime(2026, 7, 20, 6, 0),
        [{"doc_id": "20034201", "filing_type": "P", "filing_year": 2026}],
    )
    metadata_only = _snapshot(
        "house_periodic_transaction_report_index",
        datetime(2026, 7, 21, 6, 0),
        [],
        snapshot_id=2,
    )
    metadata_only.payload = None
    metadata_only.n_rows = 1

    manifest = export_snapshots([first, metadata_only], tmp_path / "congress_pit")
    frame = pd.read_parquet(tmp_path / "congress_pit")

    assert manifest["partition_count"] == 2
    continued = frame[frame["date"].astype(str) == "2026-07-21"]
    assert continued["doc_id"].tolist() == ["20034201"]
    assert continued["payload_mode"].tolist() == ["carried_forward_unchanged"]
