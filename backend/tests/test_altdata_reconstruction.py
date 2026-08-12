from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.models.altdata import AltDataSnapshot
from app.services.altdata_reconstruction import reconstruct_state_from_vintages


def _vintage(*, snapshot_id: int, source: str, captured_at: datetime) -> AltDataSnapshot:
    return AltDataSnapshot(
        id=snapshot_id,
        source=source,
        as_of_date=captured_at.date(),
        captured_at=captured_at,
        n_rows=1,
        content_hash=f"{snapshot_id:064x}",
        payload={"snapshot_id": snapshot_id},
    )


def test_reconstructs_day_d_using_only_vintages_at_or_before_d():
    day_d = date(2026, 7, 20)
    earlier = _vintage(
        snapshot_id=1,
        source="source_a",
        captured_at=datetime.combine(day_d - timedelta(days=1), datetime.min.time()),
    )
    on_day_d = _vintage(
        snapshot_id=2,
        source="source_a",
        captured_at=datetime.combine(day_d, datetime.min.time()),
    )
    independent_source = _vintage(
        snapshot_id=3,
        source="source_b",
        captured_at=datetime.combine(day_d, datetime.min.time()),
    )

    reconstructed = reconstruct_state_from_vintages(
        [earlier, on_day_d, independent_source], as_of_day=day_d
    )

    assert {source: snapshot.id for source, snapshot in reconstructed.items()} == {
        "source_a": 2,
        "source_b": 3,
    }
    assert all(snapshot.captured_at.date() <= day_d for snapshot in reconstructed.values())


def test_reconstruction_rejects_one_injected_future_vintage():
    day_d = date(2026, 7, 20)
    historical = _vintage(
        snapshot_id=1,
        source="source_a",
        captured_at=datetime.combine(day_d, datetime.min.time()),
    )
    injected_future = _vintage(
        snapshot_id=2,
        source="source_a",
        captured_at=datetime.combine(day_d + timedelta(days=1), datetime.min.time()),
    )

    with pytest.raises(ValueError, match="future vintage 2 captured on 2026-07-21"):
        reconstruct_state_from_vintages(
            [historical, injected_future], as_of_day=day_d
        )
