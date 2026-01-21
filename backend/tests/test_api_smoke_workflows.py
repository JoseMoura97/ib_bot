from __future__ import annotations

from datetime import datetime

import pytest


@pytest.fixture()
def celery_calls(client, monkeypatch):
    calls: list[dict] = []

    from app.worker import celery_app as celery_module

    def _spy(name: str, args=None, kwargs=None, **rest):
        calls.append({"name": name, "args": args or [], "kwargs": kwargs or {}, "rest": rest})
        return None

    monkeypatch.setattr(celery_module.celery_app, "send_task", _spy)
    return calls


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_dashboard_plot_data_stub_loads_when_missing(client):
    # Fresh installs won't have plot_data.json yet; endpoint should still load.
    r = client.get("/plot-data")
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("missing") is True
    assert payload.get("strategies") == {}


def test_refresh_buttons_queue_tasks(client, celery_calls):
    r1 = client.post("/plot-data/refresh?force=true&max_age_hours=0")
    assert r1.status_code == 200, r1.text
    assert r1.json().get("queued") is True

    r2 = client.post("/metrics/strategies/refresh?force=true&max_age_hours=0")
    assert r2.status_code == 200, r2.text
    assert r2.json().get("queued") is True

    names = [c["name"] for c in celery_calls]
    assert "refresh_plot_data_task" in names
    assert "refresh_validation_results_task" in names


def test_create_portfolio_allocate_run_backtest_queues_job(client, celery_calls):
    p = client.post(
        "/portfolios",
        json={"name": "Smoke Portfolio", "description": "smoke", "default_cash": 12345, "settings": {}},
    ).json()
    pid = p["id"]

    # Allocate $X (update default_cash)
    pr = client.patch(f"/portfolios/{pid}", json={"default_cash": 25000})
    assert pr.status_code == 200, pr.text
    assert pr.json()["default_cash"] == 25000

    # Enable at least one strategy
    sr = client.put(
        f"/portfolios/{pid}/strategies",
        json=[{"strategy_name": "Congress Buys", "enabled": True, "weight": 1.0, "overrides": {}}],
    )
    assert sr.status_code == 200, sr.text

    rr = client.post(
        "/runs/portfolio-backtest",
        json={
            "portfolio_id": pid,
            "start_date": "2024-01-01",
            "end_date": "2024-02-01",
            "mode": "nav_blend",
            "rebalance_policy": "per_strategy",
            "transaction_cost_bps": 0.0,
        },
    )
    assert rr.status_code == 200, rr.text
    run = rr.json()

    assert any(c["name"] == "portfolio_backtest_task" and c["args"] == [str(run["id"])] for c in celery_calls)


def test_paper_rebalance_executes_and_updates_positions(client, monkeypatch):
    # Avoid network price fetching in tests.
    import app.api.routes.paper as paper_routes
    from app.services.paper_trading import PriceQuote

    def fake_fetch_prices(tickers):
        now = datetime.utcnow()
        return {str(t).upper(): PriceQuote(ticker=str(t).upper(), price=100.0, as_of=now, source="test") for t in tickers}

    monkeypatch.setattr(paper_routes, "fetch_prices", fake_fetch_prices)

    # Create a portfolio with at least one enabled strategy (rebalance requires it)
    p = client.post("/portfolios", json={"name": "Paper Portfolio", "default_cash": 100000, "settings": {}}).json()
    pid = p["id"]
    client.put(
        f"/portfolios/{pid}/strategies",
        json=[{"strategy_name": "Congress Buys", "enabled": True, "weight": 1.0, "overrides": {}}],
    )

    # Preview rebalance (uses fallback target if QUIVER_API_KEY missing)
    preview = client.post("/paper/rebalance/preview", json={"account_id": 1, "portfolio_id": pid, "allocation_usd": 1000})
    assert preview.status_code == 200, preview.text
    legs = preview.json().get("legs") or []
    assert legs, "Expected at least one rebalance leg"

    # Execute and verify positions update
    exec_r = client.post("/paper/rebalance/execute", json={"account_id": 1, "portfolio_id": pid, "allocation_usd": 1000})
    assert exec_r.status_code == 200, exec_r.text

    pos = client.get("/paper/accounts/1/positions")
    assert pos.status_code == 200, pos.text
    rows = pos.json()
    assert any(r.get("ticker") == "SPY" and float(r.get("quantity") or 0) > 0 for r in rows)

    # Orders/fills list endpoints should be available for the UI tables.
    o = client.get("/paper/accounts/1/orders?limit=10")
    assert o.status_code == 200, o.text
    f = client.get("/paper/accounts/1/fills?limit=10")
    assert f.status_code == 200, f.text


def test_paper_order_accepts_symbol_alias_and_ignores_extra_fields(client, monkeypatch):
    # Avoid network lookup by providing explicit price.
    r = client.post(
        "/paper/accounts/1/orders",
        json={"symbol": "AAPL", "side": "BUY", "quantity": 1, "price": 100, "type": "MKT"},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["order"]["ticker"] == "AAPL"
    assert payload["trade"]["ticker"] == "AAPL"

