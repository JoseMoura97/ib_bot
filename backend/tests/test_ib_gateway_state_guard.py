"""Broker-stub proof that Gateway state is a fail-closed execution fence."""
from __future__ import annotations

import sys
import types
import uuid
from datetime import datetime

import pytest

from app.core.config import settings
from system.execution.gateway_state import GatewayState


_ACCOUNT = "U-GATEWAY-STATE"
_PORTFOLIO = "00000000-0000-0000-0000-000000000049"


class _Trade:
    orderStatus = types.SimpleNamespace(status="Filled", filled=1.0, remaining=0.0, avgFillPrice=100.0)
    order = types.SimpleNamespace(orderId=1, permId=2)
    fills = []


class _BrokerStub:
    """In-memory broker: a test fails if a blocked case reaches this method."""

    def __init__(self) -> None:
        self.place_calls = 0

    def reqAllOpenOrders(self):
        return []

    def qualifyContracts(self, *_args):
        pass

    def sleep(self, _seconds):
        pass

    def placeOrder(self, *_args):
        self.place_calls += 1
        return _Trade()


def _install_ib_insync(monkeypatch):
    module = types.ModuleType("ib_insync")
    module.Stock = lambda symbol, *_args: types.SimpleNamespace(symbol=symbol)

    class _MarketOrder:
        def __init__(self, action, quantity):
            self.action = action
            self.totalQuantity = quantity
            self.account = ""

    module.MarketOrder = _MarketOrder
    monkeypatch.setitem(sys.modules, "ib_insync", module)


def _healthy_state() -> GatewayState:
    return GatewayState(True, 1_000.0, None, False, "healthy")


def _wire_execution(monkeypatch, broker: _BrokerStub, state: GatewayState):
    import app.api.routes.live as live

    _install_ib_insync(monkeypatch)
    monkeypatch.setattr(settings, "enable_live_trading", True)
    monkeypatch.setattr(settings, "live_dry_run", False)
    monkeypatch.setattr(settings, "trading_halt", False)
    monkeypatch.setattr(settings, "live_allowed_accounts", None)
    monkeypatch.setattr(settings, "live_max_order_notional_usd", 0.0)
    monkeypatch.setattr(settings, "live_max_aggregate_notional_usd", 0.0)
    monkeypatch.setattr(live, "current_ib_gateway_state", lambda: state)
    monkeypatch.setattr(live, "_assert_account_allowed", lambda _account: None)
    monkeypatch.setattr(live, "market_is_open", lambda *_args: (True, None))
    monkeypatch.setattr(live, "_account_total_pnl", lambda *_args: (0.0, 0.0))
    monkeypatch.setattr(live, "_account_nlv", lambda *_args: 100_000.0)
    monkeypatch.setattr(live, "call_ib", lambda fn, **_kwargs: fn(broker))
    monkeypatch.setattr("app.services.alerting.send_error_alert", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.services.alerting.send_rebalance_alert", lambda *_args, **_kwargs: None)

    def _preview(*_args, **_kwargs):
        return live.LiveRebalancePreviewOut(
            as_of=datetime.utcnow(), portfolio_id=_PORTFOLIO, account_id=_ACCOUNT,
            allocation_amount=1_000.0, estimated_notional=1_000.0,
            legs=[live.LiveRebalanceLeg(
                ticker="AAPL", target_weight=1.0, price=100.0, target_value=1_000.0,
                target_quantity=10.0, current_quantity=0.0, delta_quantity=10.0, side="BUY",
            )],
        )

    monkeypatch.setattr(live, "_build_preview", _preview)


def _post(client):
    return client.post(
        "/live/rebalance/execute",
        json={"account_id": _ACCOUNT, "portfolio_id": _PORTFOLIO, "allocation_amount": 1_000, "confirm": True},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )


@pytest.mark.parametrize(
    ("state", "expected_detail"),
    [
        (GatewayState(False, 1_000.0, "connection refused", False, "disconnected"), "disconnected"),
        (GatewayState(True, 900.0, None, False, "stale"), "stale"),
        (GatewayState(True, 1_000.0, None, True, "dormant_active"), "active during enforced dormancy"),
    ],
)
def test_unhealthy_gateway_states_reach_zero_broker_orders(client, monkeypatch, state, expected_detail):
    broker = _BrokerStub()
    _wire_execution(monkeypatch, broker, state)

    response = _post(client)

    assert response.status_code == 503
    assert expected_detail in response.json()["detail"]
    assert broker.place_calls == 0


@pytest.mark.parametrize(
    ("state", "expected_detail"),
    [
        (GatewayState(False, 1_000.0, "connection refused", False, "disconnected"), "disconnected"),
        (GatewayState(True, 900.0, None, False, "stale"), "stale"),
    ],
)
def test_gateway_transition_before_submission_reaches_zero_broker_orders(
    client, monkeypatch, state, expected_detail
):
    """A healthy entry snapshot cannot authorize a later failed Gateway state."""
    import app.api.routes.live as live

    broker = _BrokerStub()
    _wire_execution(monkeypatch, broker, _healthy_state())
    snapshots = iter([_healthy_state(), state])
    monkeypatch.setattr(live, "current_ib_gateway_state", lambda: next(snapshots))

    response = _post(client)

    assert response.status_code == 503
    assert expected_detail in response.json()["detail"]
    assert broker.place_calls == 0


def test_healthy_gateway_state_allows_exactly_one_broker_order(client, monkeypatch):
    broker = _BrokerStub()
    _wire_execution(monkeypatch, broker, _healthy_state())

    response = _post(client)

    assert response.status_code == 200
    assert broker.place_calls == 1
