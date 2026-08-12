from __future__ import annotations

import json
from pathlib import Path


def test_plot_data_keeps_empty_cache_real_only(client, monkeypatch, tmp_path: Path):
    # Arrange: an empty plot-data cache plus validation data.  The dashboard
    # must not turn validation metrics into synthetic curves.
    plot_path = tmp_path / "plot_data.json"
    plot_path.write_text(json.dumps({"generated_at": "t", "strategies": {}, "benchmark": None}), encoding="utf-8")

    validation_path = tmp_path / "last_validation_results.json"
    validation_path.write_text(
        json.dumps(
            {
                "generated_at": "t2",
                "strategies": {
                    "Congress Buys": {"cagr": 12.3, "sharpe": 0.9, "max_drawdown": -25.0, "start_date": "2020-01-01"},
                    "Bad": {"status": "ERROR"},
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("PLOT_DATA_PATH", str(plot_path))
    monkeypatch.setenv("VALIDATION_RESULTS_PATH", str(validation_path))
    monkeypatch.setenv("PRICE_SOURCE", "auto")

    # Act
    res = client.get("/plot-data")
    assert res.status_code == 200
    data = res.json()

    # Assert: the API returns the real (empty) cache unchanged apart from its
    # documented metadata defaults; synthetic fallback generation is disabled.
    assert data.get("synthetic") is not True
    assert data["data_source"] == "unknown"
    assert data["price_source"] == "auto"
    assert data["strategies"] == {}

    # And it does not mutate the cache into a synthetic payload.
    persisted = json.loads(plot_path.read_text(encoding="utf-8"))
    assert persisted.get("synthetic") is not True

