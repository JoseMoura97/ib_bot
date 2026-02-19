from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException


def test_ib_accounts_returns_all(client, monkeypatch):
    from app.api.routes import ib as ib_routes

    def fake_call_ib(fn, *, timeout: float = 10.0):
        class FakeIb:
            def managedAccounts(self):
                return ["U1", "U2", "U3"]

            class wrapper:
                accounts = ["U1", "U2", "U3"]

        return fn(FakeIb())

    monkeypatch.setattr(ib_routes, "call_ib", fake_call_ib)

    res = client.get("/ib/accounts")
    assert res.status_code == 200
    assert res.json() == [{"account_id": "U1"}, {"account_id": "U2"}, {"account_id": "U3"}]


def test_ib_accounts_splits_comma_separated(client, monkeypatch):
    from app.api.routes import ib as ib_routes

    def fake_call_ib(fn, *, timeout: float = 10.0):
        class FakeIb:
            def managedAccounts(self):
                # Some wrappers return one element with commas.
                return ["U1,U2,U3"]

            class wrapper:
                accounts = ["U1,U2,U3"]

        return fn(FakeIb())

    monkeypatch.setattr(ib_routes, "call_ib", fake_call_ib)

    res = client.get("/ib/accounts")
    assert res.status_code == 200
    assert res.json() == [{"account_id": "U1"}, {"account_id": "U2"}, {"account_id": "U3"}]


def test_ib_status_handles_connect_error(client, monkeypatch):
    from app.api.routes import ib as ib_routes

    def fake_call_ib(_fn, *, timeout: float = 10.0):
        raise HTTPException(status_code=503, detail="boom")

    monkeypatch.setattr(ib_routes, "call_ib", fake_call_ib)
    monkeypatch.setattr(ib_routes, "current_ib_connection", lambda: {"host": "h", "port": 123})

    res = client.get("/ib/status")
    assert res.status_code == 200
    data = res.json()
    assert data["connected"] is False
    assert data["error"] == "boom"
    assert data["host"] == "h"
    assert data["port"] == 123


def test_ib_accounts_falls_back_to_account_summary(client, monkeypatch):
    from app.api.routes import ib as ib_routes

    def fake_call_ib(fn, *, timeout: float = 10.0):
        class FakeIb:
            def managedAccounts(self):
                # Incomplete list from managedAccounts
                return ["U1"]

            class wrapper:
                accounts = ["U1"]

            def accountSummary(self, *args, **kwargs):
                # Richer list from summary rows (legacy dashboard behavior)
                return [
                    SimpleNamespace(account="All", tag="NetLiquidation", value="0", currency="USD"),
                    SimpleNamespace(account="U1", tag="NetLiquidation", value="1", currency="USD"),
                    SimpleNamespace(account="U2", tag="NetLiquidation", value="2", currency="USD"),
                    SimpleNamespace(account="U3", tag="NetLiquidation", value="3", currency="USD"),
                ]

        return fn(FakeIb())

    monkeypatch.setattr(ib_routes, "call_ib", fake_call_ib)

    res = client.get("/ib/accounts")
    assert res.status_code == 200
    assert res.json() == [{"account_id": "U1"}, {"account_id": "U2"}, {"account_id": "U3"}]


def test_ib_accounts_prefers_richest_source_and_dedupes(client, monkeypatch):
    from app.api.routes import ib as ib_routes

    def fake_call_ib(fn, *, timeout: float = 10.0):
        class FakeIb:
            def managedAccounts(self):
                # Base list (with whitespace + dup)
                return [" U1 ", "U1"]

            class wrapper:
                # Richer list, still with dup
                accounts = ["U1", "U2", "U2"]

            def accountSummary(self, *args, **kwargs):
                # Richest list, includes "All" which must be ignored
                return [
                    SimpleNamespace(account="All", tag="NetLiquidation", value="0", currency="USD"),
                    SimpleNamespace(account="U1", tag="NetLiquidation", value="1", currency="USD"),
                    SimpleNamespace(account="U2", tag="NetLiquidation", value="2", currency="USD"),
                    SimpleNamespace(account="U3", tag="NetLiquidation", value="3", currency="USD"),
                    SimpleNamespace(account="U3", tag="AvailableFunds", value="4", currency="USD"),
                ]

        return fn(FakeIb())

    monkeypatch.setattr(ib_routes, "call_ib", fake_call_ib)

    res = client.get("/ib/accounts")
    assert res.status_code == 200
    assert res.json() == [{"account_id": "U1"}, {"account_id": "U2"}, {"account_id": "U3"}]


def test_ib_connect_updates_connection_and_returns_accounts(client, monkeypatch):
    from app.api.routes import ib as ib_routes

    seen = {}

    def fake_configure_ib_connection(*, host: str, port: int) -> None:
        seen["host"] = host
        seen["port"] = port

    monkeypatch.setattr(ib_routes, "configure_ib_connection", fake_configure_ib_connection)
    monkeypatch.setattr(ib_routes, "current_ib_connection", lambda: {"host": "newhost", "port": 4002})

    def fake_call_ib(fn, *, timeout: float = 10.0):
        class FakeIb:
            def managedAccounts(self):
                return ["A1", "A2", "A3"]

        return fn(FakeIb())

    monkeypatch.setattr(ib_routes, "call_ib", fake_call_ib)

    res = client.post("/ib/connect", json={"host": "newhost", "port": 4002})
    assert res.status_code == 200
    data = res.json()
    assert seen == {"host": "newhost", "port": 4002}
    assert data["connected"] is True
    assert data["host"] == "newhost"
    assert data["port"] == 4002
    assert data["accounts"] == ["A1", "A2", "A3"]


def test_ib_accounts_merges_ib_extra_accounts(client, monkeypatch):
    from app.api.routes import ib as ib_routes

    # Pretend operator configured extra accounts.
    monkeypatch.setattr(ib_routes.settings, "ib_extra_accounts", "U2, U3")

    def fake_call_ib(fn, *, timeout: float = 10.0):
        class FakeIb:
            def managedAccounts(self):
                return ["U1", "U2"]

        return fn(FakeIb())

    monkeypatch.setattr(ib_routes, "call_ib", fake_call_ib)

    res = client.get("/ib/accounts")
    assert res.status_code == 200
    # Expect union with stable order (managed first, then extras not already present).
    assert res.json() == [{"account_id": "U1"}, {"account_id": "U2"}, {"account_id": "U3"}]


def test_ib_status_merges_ib_extra_accounts(client, monkeypatch):
    from app.api.routes import ib as ib_routes

    monkeypatch.setattr(ib_routes.settings, "ib_extra_accounts", "U9")
    monkeypatch.setattr(ib_routes, "current_ib_connection", lambda: {"host": "h", "port": 4001})

    def fake_call_ib(_fn, *, timeout: float = 10.0):
        return ["U1"]

    monkeypatch.setattr(ib_routes, "call_ib", fake_call_ib)

    res = client.get("/ib/status")
    assert res.status_code == 200
    data = res.json()
    assert data["connected"] is True
    assert data["accounts"] == ["U1", "U9"]


def test_ib_accounts_merges_query_extra_accounts(client, monkeypatch):
    from app.api.routes import ib as ib_routes

    def fake_call_ib(fn, *, timeout: float = 10.0):
        class FakeIb:
            def managedAccounts(self):
                return ["U1"]

        return fn(FakeIb())

    monkeypatch.setattr(ib_routes, "call_ib", fake_call_ib)

    res = client.get("/ib/accounts", params={"extra_accounts": "U2,U3"})
    assert res.status_code == 200
    assert res.json() == [{"account_id": "U1"}, {"account_id": "U2"}, {"account_id": "U3"}]


def test_ib_status_merges_query_extra_accounts(client, monkeypatch):
    from app.api.routes import ib as ib_routes

    monkeypatch.setattr(ib_routes, "current_ib_connection", lambda: {"host": "h", "port": 4001})

    def fake_call_ib(_fn, *, timeout: float = 10.0):
        return ["U1"]

    monkeypatch.setattr(ib_routes, "call_ib", fake_call_ib)

    res = client.get("/ib/status", params={"extra_accounts": "U2"})
    assert res.status_code == 200
    data = res.json()
    assert data["accounts"] == ["U1", "U2"]


def test_normalize_accounts_splits_whitespace_and_semicolons():
    from app.api.routes import ib as ib_routes

    assert ib_routes._normalize_accounts("U1 U2\nU3") == ["U1", "U2", "U3"]
    assert ib_routes._normalize_accounts("U1;U2, U3") == ["U1", "U2", "U3"]


def test_snapshot_falls_back_to_group_all_and_filters_positions(client, monkeypatch):
    from app.api.routes import ib as ib_routes

    def fake_call_ib(fn, *, timeout: float = 10.0):
        # Mimic a setup where accountSummary(account_id) and accountValues(account_id)
        # return nothing for sub-accounts, but accountSummary(group="All") has rows.
        class FakeIb:
            def accountValues(self, account_id: str):
                return []

            def accountSummary(self, *args, **kwargs):
                # Called as accountSummary(account_id) and accountSummary(group="All")
                if args and isinstance(args[0], str) and args[0] != "All":
                    return []
                if kwargs.get("group") and kwargs.get("group") != "All":
                    return []
                return [
                    SimpleNamespace(account="All", tag="NetLiquidation", value="0", currency="USD"),
                    SimpleNamespace(account="U23842850", tag="NetLiquidation", value="100", currency="USD"),
                    SimpleNamespace(account="U23842850", tag="TotalCashValue", value="50", currency="USD"),
                    SimpleNamespace(account="U23842862", tag="NetLiquidation", value="200", currency="USD"),
                    SimpleNamespace(account="U23842862", tag="TotalCashValue", value="80", currency="USD"),
                ]

            def positions(self, account_id: str | None = None):
                # Simulate positions(account_id) returning empty, but positions() returns all.
                if account_id:
                    return []
                c = SimpleNamespace(symbol="AAPL", localSymbol="AAPL", secType="STK", currency="USD", exchange="SMART")
                return [
                    SimpleNamespace(account="U23842850", position=1.0, avgCost=10.0, contract=c),
                    SimpleNamespace(account="U23842862", position=2.0, avgCost=20.0, contract=c),
                ]

        return fn(FakeIb())

    monkeypatch.setattr(ib_routes, "call_ib", fake_call_ib)
    monkeypatch.setattr(ib_routes, "current_ib_connection", lambda: {"host": "h", "port": 4001})

    res = client.get("/ib/accounts/U23842850/snapshot")
    assert res.status_code == 200
    data = res.json()
    assert data["account_id"] == "U23842850"
    assert data["cash_by_currency"] == {"USD": 50.0}
    assert data["key"]["NetLiquidation"]["USD"] == 100.0
    assert len(data["positions"]) == 1

