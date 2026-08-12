"""Regression coverage for every direct broker order-placement site.

The broker stubs count submission calls, so a response/error alone cannot hide
an accidental guard bypass.
"""
from __future__ import annotations

import importlib
import sys
import types
import uuid
from datetime import datetime
from threading import Lock

import pytest

from app.core.config import settings


_ACCOUNT = "U-ALLOWED"
_PORTFOLIO = "00000000-0000-0000-0000-000000000001"


class _BrokerStub:
    def __init__(self):
        self.place_calls = 0

    def placeOrder(self, *_args, **_kwargs):
        self.place_calls += 1
        return _Trade()

    def qualifyContracts(self, *_args):
        pass

    def reqAllOpenOrders(self):
        return []

    def sleep(self, _seconds):
        pass

    def reqTickers(self, _contract):
        return [_Ticker(100.0)]


class _Ticker:
    def __init__(self, price):
        self.price = price

    def marketPrice(self):
        return self.price


class _Trade:
    def __init__(self):
        self.orderStatus = types.SimpleNamespace(status="Filled", filled=10.0, remaining=0.0, avgFillPrice=100.0)
        self.order = types.SimpleNamespace(orderId=1, permId=2)
        self.fills = []


class _WebResult:
    success = True
    data = {"ok": True}
    message = ""


class _WebBrokerStub(_BrokerStub):
    def iserver_secdef_search(self, **_kwargs):
        return types.SimpleNamespace(success=True, data=[{"conid": 123}])

    def iserver_place_orders(self, _account_id, orders):
        self.placeOrder(orders)
        return _WebResult()


def _install_ib_insync(monkeypatch):
    module = types.ModuleType("ib_insync")
    module.IB = object
    module.Stock = lambda symbol, *_args: types.SimpleNamespace(symbol=symbol)

    class _MarketOrder:
        def __init__(self, action, quantity):
            self.action = action
            self.totalQuantity = quantity
            self.account = ""

    module.MarketOrder = _MarketOrder
    monkeypatch.setitem(sys.modules, "ib_insync", module)


def _configure_policy(monkeypatch, condition: str):
    for name in ("TRADING_HALT", "LIVE_ALLOWED_ACCOUNTS", "LIVE_MAX_ORDER_NOTIONAL_USD", "LIVE_MAX_AGGREGATE_NOTIONAL_USD"):
        monkeypatch.delenv(name, raising=False)
    account = _ACCOUNT
    if condition == "halt":
        monkeypatch.setenv("TRADING_HALT", "1")
    elif condition == "account":
        monkeypatch.setenv("LIVE_ALLOWED_ACCOUNTS", _ACCOUNT)
        account = "U-NOT-ALLOWED"
    elif condition == "per_order_cap":
        monkeypatch.setenv("LIVE_MAX_ORDER_NOTIONAL_USD", "500")
    elif condition == "aggregate_cap":
        monkeypatch.setenv("LIVE_MAX_AGGREGATE_NOTIONAL_USD", "500")
    return account


def _preview(account_id: str):
    from app.api.routes.live import LiveRebalanceLeg, LiveRebalancePreviewOut

    return LiveRebalancePreviewOut(
        as_of=datetime.utcnow(),
        portfolio_id=_PORTFOLIO,  # type: ignore[arg-type]
        account_id=account_id,
        allocation_amount=1_000.0,
        estimated_notional=1_000.0,
        legs=[
            LiveRebalanceLeg(
                ticker="AAPL", target_weight=1.0, price=100.0, target_value=1_000.0,
                target_quantity=10.0, current_quantity=0.0, delta_quantity=10.0, side="BUY",
            )
        ],
    )


@pytest.mark.parametrize("condition", ["halt", "account", "per_order_cap", "aggregate_cap"])
def test_api_market_order_guard_blocks_before_place_order(client, monkeypatch, condition):
    """The API's ``ib.placeOrder`` site never sees a rejected order."""
    import app.api.routes.live as live

    account = _configure_policy(monkeypatch, condition)
    broker = _BrokerStub()
    _install_ib_insync(monkeypatch)
    monkeypatch.setattr(settings, "enable_live_trading", True)
    monkeypatch.setattr(settings, "live_dry_run", False)
    monkeypatch.setattr(settings, "trading_halt", condition == "halt")
    monkeypatch.setattr(settings, "live_allowed_accounts", _ACCOUNT if condition == "account" else None)
    monkeypatch.setattr(settings, "live_max_order_notional_usd", 500.0 if condition == "per_order_cap" else 0.0)
    monkeypatch.setattr(settings, "live_max_aggregate_notional_usd", 500.0 if condition == "aggregate_cap" else 0.0)
    monkeypatch.setattr(live, "_assert_account_allowed", lambda _account: None)
    monkeypatch.setattr(live, "market_is_open", lambda *_args: (True, None))
    monkeypatch.setattr(live, "_account_total_pnl", lambda *_args: (0.0, 0.0))
    monkeypatch.setattr(live, "_account_nlv", lambda *_args: 100_000.0)
    monkeypatch.setattr(live, "_build_preview", lambda *_args, **_kwargs: _preview(account))
    monkeypatch.setattr(live, "call_ib", lambda fn, **_kwargs: fn(broker))
    monkeypatch.setattr("app.services.alerting.send_error_alert", lambda *_args, **_kwargs: None)

    response = client.post(
        "/live/rebalance/execute",
        json={"account_id": account, "portfolio_id": _PORTFOLIO, "allocation_amount": 1_000, "confirm": True},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code >= 400
    assert broker.place_calls == 0


@pytest.mark.parametrize("condition", ["halt", "account", "per_order_cap", "aggregate_cap"])
def test_executor_rebalance_guard_blocks_before_place_order(monkeypatch, condition):
    """The legacy ``IBExecutor.rebalance`` site shares the same pre-flight fence."""
    _install_ib_insync(monkeypatch)
    sys.modules.pop("system.execution.ib_executor", None)
    executor_module = importlib.import_module("system.execution.ib_executor")
    account = _configure_policy(monkeypatch, condition)
    broker = _BrokerStub()
    executor = executor_module.IBExecutor()
    executor.ib = broker
    monkeypatch.setattr(executor, "get_current_positions", lambda _account: {})

    with pytest.raises(RuntimeError):
        executor.rebalance(["AAPL"], allocation_per_stock_usd=1_000.0, account=account)
    assert broker.place_calls == 0


@pytest.mark.parametrize("condition", ["halt", "account", "per_order_cap", "aggregate_cap"])
def test_web_client_guard_blocks_before_place_order(monkeypatch, condition):
    """The Client Portal market-order site is refused before its broker submission."""
    ibind = types.ModuleType("ibind")
    ibind.IbkrClient = object
    monkeypatch.setitem(sys.modules, "ibind", ibind)
    sys.modules.pop("system.execution.ib_web_client", None)
    web_module = importlib.import_module("system.execution.ib_web_client")
    account = _configure_policy(monkeypatch, condition)
    broker = _WebBrokerStub()
    client = web_module.IBWebClient.__new__(web_module.IBWebClient)
    client.client = broker
    client._submitted_notional_usd = 0.0
    client._notional_lock = Lock()

    with pytest.raises(RuntimeError):
        client.place_market_order(account, "AAPL", "BUY", 10, estimated_price=100.0)
    assert broker.place_calls == 0


def test_allowed_api_order_places_exactly_one_order(client, monkeypatch):
    """A permitted API order still reaches the broker exactly once."""
    import app.api.routes.live as live

    broker = _BrokerStub()
    _install_ib_insync(monkeypatch)
    monkeypatch.setattr(settings, "enable_live_trading", True)
    monkeypatch.setattr(settings, "live_dry_run", False)
    monkeypatch.setattr(settings, "trading_halt", False)
    monkeypatch.setattr(settings, "live_allowed_accounts", _ACCOUNT)
    monkeypatch.setattr(settings, "live_max_order_notional_usd", 2_000.0)
    monkeypatch.setattr(settings, "live_max_aggregate_notional_usd", 2_000.0)
    monkeypatch.setattr(live, "_assert_account_allowed", lambda _account: None)
    monkeypatch.setattr(live, "market_is_open", lambda *_args: (True, None))
    monkeypatch.setattr(live, "_account_total_pnl", lambda *_args: (0.0, 0.0))
    monkeypatch.setattr(live, "_account_nlv", lambda *_args: 100_000.0)
    monkeypatch.setattr(live, "_build_preview", lambda *_args, **_kwargs: _preview(_ACCOUNT))
    monkeypatch.setattr(live, "call_ib", lambda fn, **_kwargs: fn(broker))
    monkeypatch.setattr("app.services.alerting.send_error_alert", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.services.alerting.send_rebalance_alert", lambda *_args, **_kwargs: None)

    response = client.post(
        "/live/rebalance/execute",
        json={"account_id": _ACCOUNT, "portfolio_id": _PORTFOLIO, "allocation_amount": 1_000, "confirm": True},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 200
    assert broker.place_calls == 1
