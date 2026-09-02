"""Roadmap 5144dfda / plan 8f2e018b, phase p3-stale-broker-state.

Broker timeout or stale/contradictory order state must halt new placement
until a bounded reconciliation observes a terminal or matching broker state.

Covers the live-facing order-preflight contract in
``backend/app/api/routes/live.py::execute_live_rebalance_core`` — the
anti-duplicate / stale-state guard that runs immediately before the only
``ib.placeOrder`` call site in that path. Before this phase, an exception
raised while checking existing broker order state (e.g. a broker timeout)
was silently swallowed and treated as "no open orders", so a hung/erroring
broker check FAILED OPEN and let a new basket race an in-flight/duplicate
one. This suite proves the fixed fail-closed behaviour:

1. A broker timeout while checking order state -> reconciliation-required
   error, 0 ``placeOrder`` calls.
2. A stale/contradictory order snapshot (a non-terminal order already open
   at the broker) -> reconciliation-required error, 0 ``placeOrder`` calls.
3. Only after reconciliation (the broker confirms a terminal/matching
   state) does exactly 1 controlled placement path proceed.

No IB Gateway socket is opened and no real broker call is made anywhere in
this file — ``call_ib`` is monkeypatched to invoke a synchronous stub broker
that counts ``placeOrder`` invocations.
"""
from __future__ import annotations

import sys
import types
import uuid
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import datetime

import pytest

from app.core.config import settings

_ACCOUNT_ID = "U-STALE-STATE"
_PORTFOLIO_ID = "00000000-0000-0000-0000-000000000003"


def _body(**overrides):
    return {
        "account_id": _ACCOUNT_ID,
        "portfolio_id": _PORTFOLIO_ID,
        "allocation_amount": 1_000.0,
        "max_orders": 5,
        "allow_short": False,
        "confirm": True,
        **overrides,
    }


def _preview():
    from app.api.routes.live import LiveRebalanceLeg, LiveRebalancePreviewOut

    return LiveRebalancePreviewOut(
        as_of=datetime.utcnow(),
        portfolio_id=_PORTFOLIO_ID,  # type: ignore[arg-type]
        account_id=_ACCOUNT_ID,
        allocation_amount=1_000.0,
        estimated_notional=1_000.0,
        legs=[
            LiveRebalanceLeg(
                ticker="AAPL", target_weight=1.0, price=100.0, target_value=1_000.0,
                target_quantity=10.0, current_quantity=0.0, delta_quantity=10.0, side="BUY",
            )
        ],
    )


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


class _OpenOrder:
    """Mimics an ib_insync Trade as returned by ``reqAllOpenOrders``."""

    def __init__(self, account: str, status: str):
        self.order = types.SimpleNamespace(orderId=99, permId=100, account=account)
        self.orderStatus = types.SimpleNamespace(status=status, filled=0.0, remaining=5.0, avgFillPrice=0.0)


class _Trade:
    def __init__(self):
        self.orderStatus = types.SimpleNamespace(status="Filled", filled=10.0, remaining=0.0, avgFillPrice=100.0)
        self.order = types.SimpleNamespace(orderId=1, permId=2)
        self.fills = []


class _StaleBrokerStub:
    """Broker stub whose reported order state is controlled per-call.

    ``open_orders_mode`` drives what ``reqAllOpenOrders`` does on the *next*
    call, so a single stub instance can model a broker that later becomes
    reconciled (mimics a real re-check after the operator confirms state):

    - "timeout": raise, simulating a broker call that never answers in time.
    - "stale": return one non-terminal open order for this account.
    - "clear": return no open orders (broker confirms nothing outstanding).
    - "terminal": return one order for this account already in a terminal
      status (broker confirms the earlier order finished, not still live).
    """

    def __init__(self, open_orders_mode: str):
        self.open_orders_mode = open_orders_mode
        self.place_calls = 0
        self.open_orders_calls = 0

    def reqAllOpenOrders(self):
        self.open_orders_calls += 1
        if self.open_orders_mode == "timeout":
            raise FuturesTimeout("IB Gateway did not respond to reqAllOpenOrders within timeout")
        if self.open_orders_mode == "stale":
            return [_OpenOrder(_ACCOUNT_ID, "Submitted")]
        if self.open_orders_mode == "terminal":
            return [_OpenOrder(_ACCOUNT_ID, "Filled")]
        return []  # "clear"

    def placeOrder(self, *_args, **_kwargs):
        self.place_calls += 1
        return _Trade()

    def qualifyContracts(self, *_args):
        pass

    def sleep(self, _seconds):
        pass


def _wire_common(monkeypatch, broker):
    import app.api.routes.live as live

    _install_ib_insync(monkeypatch)
    monkeypatch.setattr(settings, "enable_live_trading", True)
    monkeypatch.setattr(settings, "live_dry_run", False)
    monkeypatch.setattr(settings, "trading_halt", False)
    monkeypatch.setattr(live, "_assert_account_allowed", lambda _account: None)
    monkeypatch.setattr(live, "market_is_open", lambda *_args: (True, None))
    monkeypatch.setattr(live, "_account_total_pnl", lambda *_args: (0.0, 0.0))
    monkeypatch.setattr(live, "_account_nlv", lambda *_args: 100_000.0)
    monkeypatch.setattr(live, "_build_preview", lambda *_args, **_kwargs: _preview())
    monkeypatch.setattr(live, "call_ib", lambda fn, **_kwargs: fn(broker))
    monkeypatch.setattr("app.services.alerting.send_error_alert", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.services.alerting.send_rebalance_alert", lambda *_args, **_kwargs: None)
    return live


def _post(client):
    return client.post(
        "/live/rebalance/execute",
        json=_body(),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )


# ---------------------------------------------------------------------------
# 1. Broker timeout checking existing order state -> fail closed
# ---------------------------------------------------------------------------

def test_broker_timeout_blocks_placement_and_surfaces_reconciliation(client, monkeypatch):
    """A timeout while confirming broker order state must not be treated as
    'no open orders' — it must fail closed with a surfaced error, and the
    order-placement site must never be reached."""
    broker = _StaleBrokerStub(open_orders_mode="timeout")
    _wire_common(monkeypatch, broker)

    resp = _post(client)

    assert resp.status_code >= 500, f"expected a fail-closed 5xx, got {resp.status_code}: {resp.text}"
    detail = resp.json()["detail"].lower()
    assert "reconciliation required" in detail
    assert "timeout" in detail or "futurestimeout" in detail
    assert broker.place_calls == 0, "a broker timeout while checking order state must reach 0 placeOrder calls"


# ---------------------------------------------------------------------------
# 2. Stale/contradictory order snapshot -> fail closed
# ---------------------------------------------------------------------------

def test_stale_open_order_blocks_placement_and_surfaces_reconciliation(client, monkeypatch):
    """A non-terminal order already open at the broker for this account must
    block a new basket instead of stacking on top of it."""
    broker = _StaleBrokerStub(open_orders_mode="stale")
    _wire_common(monkeypatch, broker)

    resp = _post(client)

    assert resp.status_code == 409, f"expected 409, got {resp.status_code}: {resp.text}"
    detail = resp.json()["detail"].lower()
    assert "reconciliation required" in detail
    assert "non-terminal" in detail
    assert broker.place_calls == 0, "a stale open order must reach 0 placeOrder calls"


# ---------------------------------------------------------------------------
# 3. Only after reconciliation does exactly one controlled path proceed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reconciled_mode", ["clear", "terminal"])
def test_reconciled_broker_state_permits_exactly_one_placement(client, monkeypatch, reconciled_mode):
    """Two stale/erroring attempts are blocked (0 broker placements each);
    only the third attempt, after the broker confirms a matching/terminal
    state, is allowed through — and it places exactly once."""
    broker = _StaleBrokerStub(open_orders_mode="timeout")
    _wire_common(monkeypatch, broker)

    # Attempt 1: broker timeout mid-reconciliation-check -> blocked.
    resp1 = _post(client)
    assert resp1.status_code >= 500
    assert broker.place_calls == 0

    # Attempt 2: broker now answers but reports a stale non-terminal order
    # still outstanding -> still blocked, still 0 placements.
    broker.open_orders_mode = "stale"
    resp2 = _post(client)
    assert resp2.status_code == 409
    assert broker.place_calls == 0

    # Attempt 3: reconciliation completes — the broker now reports either no
    # open orders ("clear") or the earlier order resolved to a terminal
    # status ("terminal"). This is the single controlled path allowed to
    # reach the broker.
    broker.open_orders_mode = reconciled_mode
    resp3 = _post(client)
    assert resp3.status_code == 200, f"reconciled attempt should succeed, got {resp3.status_code}: {resp3.text}"
    assert broker.place_calls == 1, "exactly one controlled placement is permitted after reconciliation"

    # No attempt before reconciliation ever reached the broker, and the
    # reconciled attempt reached it exactly once across the whole sequence.
    assert broker.open_orders_calls == 3
