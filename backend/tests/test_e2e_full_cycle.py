"""
End-to-end integration test:
  Create portfolio -> set strategies/weights -> run paper rebalance ->
  verify positions -> check snapshot/pnl endpoints
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.paper_trading import PriceQuote


MOCK_PRICES = {
    "AAPL": PriceQuote(ticker="AAPL", price=180.0, as_of=None, source="mock"),
    "MSFT": PriceQuote(ticker="MSFT", price=420.0, as_of=None, source="mock"),
    "GOOGL": PriceQuote(ticker="GOOGL", price=170.0, as_of=None, source="mock"),
    "SPY": PriceQuote(ticker="SPY", price=500.0, as_of=None, source="mock"),
}


def _mock_fetch_prices(tickers):
    return {t: MOCK_PRICES.get(t, PriceQuote(ticker=t, price=100.0, as_of=None, source="mock")) for t in tickers}


@pytest.fixture(autouse=True)
def mock_prices():
    with patch("app.services.paper_trading.fetch_prices", side_effect=_mock_fetch_prices):
        with patch("app.api.routes.paper.fetch_prices", side_effect=_mock_fetch_prices):
            yield


class TestFullCycle:
    def test_portfolio_create_and_strategies(self, client, db_session):
        # 1. Create portfolio
        resp = client.post("/api/portfolios", json={
            "name": "E2E Test Portfolio",
            "description": "Integration test",
            "default_cash": 100000,
            "settings": {"mode": "nav_blend"},
        })
        assert resp.status_code == 200
        portfolio = resp.json()
        pid = portfolio["id"]
        assert portfolio["name"] == "E2E Test Portfolio"

        # 2. Set strategies with weights
        strategies = [
            {"strategy_name": "Congress Buys", "enabled": True, "weight": 0.5, "overrides": {}},
            {"strategy_name": "Michael Burry", "enabled": True, "weight": 0.5, "overrides": {}},
        ]
        resp = client.put(f"/api/portfolios/{pid}/strategies", json=strategies)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["strategies"]) == 2
        assert abs(sum(s["weight"] for s in data["strategies"]) - 1.0) < 0.01

        # 3. Get portfolio with strategies
        resp = client.get(f"/api/portfolios/{pid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "E2E Test Portfolio"

    def test_paper_account_lifecycle(self, client, db_session):
        # 1. Create paper account
        resp = client.post("/api/paper/accounts", json={
            "name": "E2E Paper Account",
            "initial_cash": 50000,
        })
        assert resp.status_code == 200
        acct = resp.json()
        aid = acct["id"]
        assert acct["balance"] == 50000

        # 2. Fund account
        resp = client.post(f"/api/paper/accounts/{aid}/fund", json={"amount": 10000})
        assert resp.status_code == 200
        assert resp.json()["balance"] == 60000

        # 3. Get summary
        resp = client.get(f"/api/paper/accounts/{aid}/summary")
        assert resp.status_code == 200
        summary = resp.json()
        assert summary["cash"] == 60000

        # 4. Place order
        resp = client.post(f"/api/paper/accounts/{aid}/orders", json={
            "ticker": "AAPL",
            "side": "BUY",
            "quantity": 10,
            "price": 180.0,
        })
        assert resp.status_code == 200
        order = resp.json()
        assert order["order"]["ticker"] == "AAPL"
        assert order["order"]["quantity"] == 10

        # 5. Check positions
        resp = client.get(f"/api/paper/accounts/{aid}/positions")
        assert resp.status_code == 200
        positions = resp.json()
        assert any(p["ticker"] == "AAPL" for p in positions)

        # 6. Check P&L endpoints (should be empty since no snapshots yet)
        resp = client.get(f"/api/paper/accounts/{aid}/snapshots")
        assert resp.status_code == 200
        assert resp.json() == []

        resp = client.get(f"/api/paper/accounts/{aid}/pnl")
        assert resp.status_code == 200
        pnl = resp.json()
        assert pnl["summary"]["days"] == 0

    def test_paper_rebalance_with_portfolio(self, client, db_session):
        # Create portfolio with SPY fallback (no quiver key)
        resp = client.post("/api/portfolios", json={
            "name": "Rebalance Test",
            "default_cash": 100000,
            "settings": {},
        })
        pid = resp.json()["id"]

        strategies = [
            {"strategy_name": "Test Strategy", "enabled": True, "weight": 1.0, "overrides": {}},
        ]
        resp = client.put(f"/api/portfolios/{pid}/strategies", json=strategies)
        assert resp.status_code == 200

        # Create paper account
        resp = client.post("/api/paper/accounts", json={"name": "Rebal Account", "initial_cash": 100000})
        aid = resp.json()["id"]

        # Preview rebalance (falls back to SPY when no quiver key)
        resp = client.post("/api/paper/rebalance/preview", json={
            "portfolio_id": pid,
            "allocation_amount": 50000,
            "account_id": aid,
        })
        assert resp.status_code == 200
        preview = resp.json()
        assert "legs" in preview
        assert len(preview["legs"]) > 0

        # Execute rebalance
        resp = client.post("/api/paper/rebalance/execute", json={
            "portfolio_id": pid,
            "allocation_amount": 50000,
            "account_id": aid,
        })
        assert resp.status_code == 200
        result = resp.json()
        assert len(result["orders"]) > 0

        # Verify positions exist
        resp = client.get(f"/api/paper/accounts/{aid}/positions")
        assert resp.status_code == 200
        positions = resp.json()
        assert len(positions) > 0

    def test_live_status_and_safety(self, client):
        # Live status endpoint
        resp = client.get("/api/live/status")
        assert resp.status_code == 200
        status = resp.json()
        assert "enabled" in status
        assert "halted" in status
        assert "dry_run" in status

    def test_halt_and_resume(self, client):
        # Halt
        resp = client.post("/api/live/halt")
        assert resp.status_code == 200
        assert resp.json()["halted"] is True

        # Resume (may fail if live trading not enabled, which is expected)
        resp = client.post("/api/live/resume")
        # Accept either 200 (success) or 403 (live trading not enabled)
        assert resp.status_code in (200, 403)

    def test_allocations_ledger(self, client, db_session):
        # Create portfolio first
        resp = client.post("/api/portfolios", json={"name": "Alloc Test", "default_cash": 50000})
        pid = resp.json()["id"]

        # Create allocation
        resp = client.post("/api/allocations", json={
            "account_id": "1",
            "portfolio_id": pid,
            "amount": 25000,
            "mode": "paper",
            "notes": "E2E test",
        })
        assert resp.status_code == 200

        # List allocations
        resp = client.get(f"/api/allocations?portfolio_id={pid}")
        assert resp.status_code == 200
        allocs = resp.json()
        assert len(allocs) >= 1
        assert allocs[0]["amount"] == 25000
