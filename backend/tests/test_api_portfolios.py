from __future__ import annotations


def test_create_and_get_portfolio(client):
    resp = client.post(
        "/portfolios",
        json={"name": "My Portfolio", "description": "test", "default_cash": 100000, "settings": {}},
    )
    assert resp.status_code == 200, resp.text
    portfolio = resp.json()
    assert portfolio["name"] == "My Portfolio"
    pid = portfolio["id"]

    resp2 = client.get(f"/portfolios/{pid}")
    assert resp2.status_code == 200, resp2.text
    got = resp2.json()
    assert got["id"] == pid
    assert got["strategies"] == []


def test_set_portfolio_strategies(client):
    p = client.post("/portfolios", json={"name": "P1"}).json()
    pid = p["id"]

    body = [
        {"strategy_name": "Congress Buys", "enabled": True, "weight": 0.6, "overrides": {}},
        {"strategy_name": "Top Lobbying Spenders", "enabled": True, "weight": 0.4, "overrides": {}},
    ]
    resp = client.put(f"/portfolios/{pid}/strategies", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["strategies"]) == 2
