from __future__ import annotations

import json
from pathlib import Path


def test_plot_data_falls_back_to_validation_when_empty(client, monkeypatch, tmp_path: Path):
    # Arrange: an empty plot_data file + a validation file with strategies.
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

    # Assert: returns synthetic payload with at least one strategy curve.
    assert data["synthetic"] is True
    assert data["data_source"] == "sample_from_validation"
    assert data["price_source"] == "auto"
    assert "Congress Buys" in (data.get("strategies") or {})
    assert len(data["strategies"]["Congress Buys"]["dates"]) > 10
    assert len(data["strategies"]["Congress Buys"]["values"]) == len(data["strategies"]["Congress Buys"]["dates"])

    # And it persists to disk (so future loads are fast).
    persisted = json.loads(plot_path.read_text(encoding="utf-8"))
    assert persisted.get("synthetic") is True

