from __future__ import annotations

from app.models.strategy import Strategy


def test_strategies_catalog_includes_meta_when_db_empty(client, monkeypatch):
    import quiver_signals

    monkeypatch.setattr(
        quiver_signals.QuiverSignals,
        "get_all_strategies",
        staticmethod(lambda: {"Congress Buys": {"category": "Politics", "description": "desc"}}),
    )

    res = client.get("/strategies/catalog")
    assert res.status_code == 200
    payload = res.json()
    assert payload["count"] >= 1
    names = [r["name"] for r in payload["rows"]]
    assert "Congress Buys" in names
    row = next(r for r in payload["rows"] if r["name"] == "Congress Buys")
    assert row["enabled"] is False
    assert row["config"] == {}
    assert row["category"] == "Politics"
    assert row["description"] == "desc"


def test_strategies_catalog_merges_db_state(db_session, client, monkeypatch):
    import quiver_signals

    monkeypatch.setattr(
        quiver_signals.QuiverSignals,
        "get_all_strategies",
        staticmethod(lambda: {"Congress Buys": {"category": "Politics"}}),
    )

    db_session.add(Strategy(name="Congress Buys", enabled=True, config={"x": 1}))
    db_session.commit()

    res = client.get("/strategies/catalog")
    assert res.status_code == 200
    payload = res.json()
    row = next(r for r in payload["rows"] if r["name"] == "Congress Buys")
    assert row["enabled"] is True
    assert row["config"] == {"x": 1}
