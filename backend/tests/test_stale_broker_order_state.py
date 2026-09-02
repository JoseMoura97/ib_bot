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

An independent ECC reviewer (2026-09-02 13:45 WEST, attempt 7e1c637b) found
that (1)-(3) alone were insufficient: ``backend/app/services/ib_worker.py``'s
``_IbWorker.call()`` enqueues ``(fn, fut)`` and waits on
``fut.result(timeout=timeout)``. When THAT wait times out, the caller gives
up and moves on -- but the queued closure is still sitting in the queue, or
already mid-execution on the worker thread (e.g. blocked inside
``reqAllOpenOrders()``), and nothing stopped it from running to completion
and reaching ``ib.placeOrder()`` for a caller that had already abandoned it.
Sections 4-5 below close that race: a caller-side ``call_ib(..., timeout=X)``
timeout now abandons a ``_CancelToken`` that (a) makes ``_run()`` skip a
still-queued task outright, and (b) is consulted via
``call_is_cancelled()`` immediately before the ``ib.placeOrder`` call site in
``_execute``, so an already-running closure also refuses to place an order
once its caller has given up.

4. ``_IbWorker``-level race: fn is dequeued and blocks inside a broker call
   past the caller's timeout; only after the caller abandons the call does
   the blocking call return -- 0 ``placeOrder`` calls afterward.
5. Route-level wiring check: ``_execute``'s ``placeOrder`` call site actually
   consults ``call_is_cancelled()`` -- when it reports abandoned, the route
   refuses to place, 0 ``placeOrder`` calls.

No IB Gateway socket is opened and no real broker call is made anywhere in
this file — ``call_ib`` is monkeypatched to invoke a synchronous stub broker
that counts ``placeOrder`` invocations (sections 1-3, 5); section 4 exercises
the real ``_IbWorker``/``call_ib`` machinery against an in-memory fake
broker object, with no socket and no ``ib_insync`` network calls.
"""
from __future__ import annotations

import sys
import threading
import time
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


# ---------------------------------------------------------------------------
# 4. _IbWorker-level race: caller times out while fn is already running,
#    blocked inside a broker call -- the closure must not reach placeOrder
#    once it unblocks and the caller has abandoned it.
# ---------------------------------------------------------------------------

def test_call_ib_timeout_blocks_placeorder_from_abandoned_call(monkeypatch):
    """
    Reproduces the ECC reviewer's exact finding (ib_worker.py:74-84, verdict
    FAIL on attempt 7e1c637b @ fd45fea5): a caller that abandons call_ib() via
    timeout must never let the still-running closure reach the broker
    afterwards.

    fn is dequeued by the worker thread and starts executing -- it calls a
    broker method that blocks past the caller's timeout (simulating a hung
    reqAllOpenOrders()). The caller's call_ib(..., timeout=...) expires and
    gives up. Only THEN does the blocking call inside fn return. Before the
    fix, fn kept running to completion on the worker thread and reached
    ib.placeOrder() for a caller that had already abandoned it.
    """
    fake_mod = types.ModuleType("ib_insync")

    class _FakeIBClass:
        def isConnected(self):
            return True

    fake_mod.IB = _FakeIBClass
    monkeypatch.setitem(sys.modules, "ib_insync", fake_mod)

    from app.services import ib_worker

    ib_worker.stop_ib_worker()

    entered_block = threading.Event()
    release_block = threading.Event()
    place_calls: list[int] = []

    class _Broker:
        def isConnected(self):
            return True

        def disconnect(self):
            pass

        def sleep(self, _seconds):
            pass

        def reqAllOpenOrders(self):
            entered_block.set()
            release_block.wait(timeout=2.0)
            return []

        def placeOrder(self, *_a, **_kw):
            place_calls.append(1)
            return object()

    def fn(ib):
        ib.reqAllOpenOrders()  # blocks past the caller's timeout, then returns
        if not ib_worker.call_is_cancelled():
            ib.placeOrder()
        return "reached end"

    # Point the singleton worker's IB handle directly at our fake broker so
    # _ensure_connected()'s isConnected() short-circuits without a real socket.
    # Reset it in `finally` so this test never leaks broker state into the
    # module-level singleton for other tests (e.g. test_ib_worker.py) that
    # run against it afterward.
    ib_worker._worker._ib = _Broker()
    ib_worker._worker._client_id = 1
    try:
        with pytest.raises(FuturesTimeout):
            ib_worker.call_ib(fn, timeout=0.05)

        # The blocking call must actually have been entered -- proves the
        # race is real (fn was already running when the caller gave up), not
        # a no-op skip.
        assert entered_block.wait(timeout=2.0), "fn never started -- race not exercised"

        # Now let the abandoned closure resume.
        release_block.set()

        # Give the worker thread time to finish processing fn to completion.
        time.sleep(0.3)

        assert place_calls == [], "an abandoned call must never reach ib.placeOrder()"
    finally:
        release_block.set()  # never leave the worker thread blocked on teardown
        ib_worker.stop_ib_worker()
        ib_worker._worker._ib = None
        ib_worker._worker._client_id = None


# ---------------------------------------------------------------------------
# 5. Route-level wiring check: _execute's placeOrder call site consults
#    call_is_cancelled() before every ib.placeOrder() call.
# ---------------------------------------------------------------------------

def test_execute_refuses_placeorder_when_call_is_cancelled(client, monkeypatch):
    """
    Complements section 4: proves live.py's _execute actually wires the
    call_is_cancelled() fence into the only placeOrder call site in the
    route, not just that the primitive exists in ib_worker.py. Simulates
    "already abandoned" directly (a real 60s+ outer timeout is impractical in
    a unit test — the outer execute_timeout is legs*per_leg_timeout + 60s).
    """
    import app.api.routes.live as live

    broker = _StaleBrokerStub(open_orders_mode="clear")
    _wire_common(monkeypatch, broker)
    monkeypatch.setattr(live, "call_is_cancelled", lambda: True)

    resp = _post(client)

    assert resp.status_code == 409, f"expected 409, got {resp.status_code}: {resp.text}"
    assert "already timed out" in resp.json()["detail"].lower()
    assert broker.place_calls == 0, "placeOrder must never be reached once call_is_cancelled() is true"
