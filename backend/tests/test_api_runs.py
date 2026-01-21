from __future__ import annotations


def test_create_portfolio_backtest_run_queues_job(client):
    p = client.post("/portfolios", json={"name": "P1"}).json()
    pid = p["id"]
    client.put(
        f"/portfolios/{pid}/strategies",
        json=[
            {"strategy_name": "Congress Buys", "enabled": True, "weight": 1.0, "overrides": {}},
        ],
    )

    resp = client.post(
        "/runs/portfolio-backtest",
        json={
            "portfolio_id": pid,
            "start_date": "2024-01-01",
            "end_date": "2024-06-01",
            "mode": "nav_blend",
            "rebalance_policy": "per_strategy",
            "transaction_cost_bps": 0.0,
        },
    )
    assert resp.status_code == 200, resp.text
    run = resp.json()
    assert run["type"] == "portfolio_backtest"
    assert run["status"] == "PENDING"

    # Can fetch run
    r2 = client.get(f"/runs/{run['id']}")
    assert r2.status_code == 200, r2.text
