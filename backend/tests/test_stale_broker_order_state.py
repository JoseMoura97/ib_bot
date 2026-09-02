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

ROUND 2 (2026-09-02 13:45 WEST, ECC attempt 7e1c637b, verdict FAIL): (1)-(3)
alone were insufficient. ``backend/app/services/ib_worker.py``'s
``_IbWorker.call()`` enqueues ``(fn, fut)`` and waits on
``fut.result(timeout=timeout)``. When THAT wait times out, the caller gives
up and moves on -- but the queued closure is still sitting in the queue, or
already mid-execution on the worker thread (e.g. blocked inside
``reqAllOpenOrders()``), and nothing stopped it from running to completion
and reaching ``ib.placeOrder()`` for a caller that had already abandoned it.
Round 2 added a ``_CancelToken`` abandoned on caller timeout and a
``call_is_cancelled()`` read consulted immediately before ``placeOrder``.

ROUND 3 (2026-09-02 14:05 WEST, ECC attempt a2334753, verdict FAIL): Round
2's fix was itself a TOCTOU race -- ``call_is_cancelled()`` (read) and
``ib.placeOrder()`` (act) are two separate steps, and ``_IbWorker.call()``
can mark the token abandoned in the gap between them. The reviewer forced
exactly that interleaving with no network I/O: the closure passed the check
with ``cancelled == False``, paused immediately after, the caller timed out
at 50ms and marked the token, and releasing the closure let the order go out
anyway. Round 3 replaces the read+act pair with a single atomic transition:
``_CancelToken.abandon()`` (caller thread, on timeout) and
``_CancelToken.try_commit()`` (worker thread, immediately before
``placeOrder``, with no branching between a True return and the actual
call) contend on the SAME lock. Exactly one wins:

- abandon() wins -> try_commit() (called after) sees the token already
  abandoned and returns False -> 0 ``placeOrder`` calls, and the original
  caller sees a plain, clean ``TimeoutError`` (nothing happened, safe to
  treat as an ordinary timeout).
- try_commit() wins -> the order is placed (or is now guaranteed to be),
  and the caller's later abandon() call sees ``_committed`` already True and
  returns False -> ``call_ib(...)`` raises an explicit
  ``reconciliation required`` 503 instead of a clean timeout, so the
  caller can never mistake "an order may be live at the broker" for
  "nothing happened". A markdown receipt is not proof by itself; every
  claim in this file's receipt is only as good as re-running the tests
  below, which is exactly what an independent reviewer does.

4. ``_IbWorker``-level race, timeout-wins branch: fn is dequeued and blocks
   inside a broker call past the caller's timeout (the caller has already
   abandoned by construction, before fn can reach the commit point) -- 0
   ``placeOrder`` calls, plain ``TimeoutError`` raised to the caller.
5. ``_IbWorker``-level race, commit-wins branch: fn commits (```placeOrder```
   is guaranteed to fire) before the caller's timeout can possibly land,
   then the (fake) broker call itself hangs past the timeout -- the caller
   must see an explicit ``503 reconciliation required`` (never a clean
   timeout), and exactly 1 ``placeOrder`` call is made once the block
   releases.
6. ``_CancelToken`` unit-level exhaustiveness: both possible orderings of
   ``abandon()``/``try_commit()`` are asserted directly and deterministically
   (no threading, no timing dependency) -- the primitive's contract holds
   independent of any scheduler behaviour.
7. Route-level wiring check: ``_execute``'s ``placeOrder`` call site actually
   consults the atomic ``call_try_commit()`` (not a plain read) -- when it
   returns False, the route refuses to place, 0 ``placeOrder`` calls.

No IB Gateway socket is opened and no real broker call is made anywhere in
this file — ``call_ib`` is monkeypatched to invoke a synchronous stub broker
that counts ``placeOrder`` invocations (sections 1-3, 7); sections 4-6
exercise the real ``_IbWorker``/``call_ib``/``_CancelToken`` machinery
against in-memory fake broker objects and threading primitives, with no
socket and no ``ib_insync`` network calls.
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


def _fresh_worker_fake_ib(monkeypatch):
    """Stop the module-level ib_worker singleton and point its IB handle at
    an in-memory fake so _ensure_connected()'s isConnected() short-circuits
    without a real socket. Caller must reset ``_ib``/``_client_id`` back to
    None in a ``finally`` so this test never leaks broker state into the
    singleton for other tests (e.g. test_ib_worker.py) that run afterward."""
    fake_mod = types.ModuleType("ib_insync")

    class _FakeIBClass:
        def isConnected(self):
            return True

    fake_mod.IB = _FakeIBClass
    monkeypatch.setitem(sys.modules, "ib_insync", fake_mod)

    from app.services import ib_worker

    ib_worker.stop_ib_worker()
    return ib_worker


# ---------------------------------------------------------------------------
# 4. _IbWorker-level race, timeout-wins branch: the caller has already
#    abandoned (by construction) before fn can reach the commit point --
#    0 placeOrder calls, and the caller sees a clean TimeoutError.
# ---------------------------------------------------------------------------

def test_call_ib_timeout_wins_blocks_placeorder(monkeypatch):
    """
    fn is dequeued by the worker thread and blocks inside a broker call
    (simulating a hung reqAllOpenOrders()) past the caller's timeout. The
    caller's call_ib(..., timeout=...) expires and gives up -- abandon()
    fires while fn is still blocked, i.e. strictly before fn can ever reach
    try_commit(). Once released, fn's try_commit() must see the token
    already abandoned and refuse -- 0 placeOrder calls -- and the caller
    must see a plain, clean TimeoutError (nothing happened, safe as an
    ordinary timeout).
    """
    ib_worker = _fresh_worker_fake_ib(monkeypatch)

    entered_block = threading.Event()
    release_block = threading.Event()
    place_calls: list[int] = []
    commit_results: list[bool] = []

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
        commit_results.append(ib_worker.call_try_commit())
        if commit_results[-1]:
            ib.placeOrder()
        return "reached end"

    ib_worker._worker._ib = _Broker()
    ib_worker._worker._client_id = 1
    try:
        with pytest.raises(FuturesTimeout):
            ib_worker.call_ib(fn, timeout=0.05)

        # The blocking call must actually have been entered -- proves the
        # race is real (fn was already running when the caller gave up), not
        # a no-op skip.
        assert entered_block.wait(timeout=2.0), "fn never started -- race not exercised"

        # Caller has already timed out and abandoned by this point. Now let
        # the blocked closure resume and reach try_commit().
        release_block.set()
        time.sleep(0.3)  # let the worker thread finish processing fn

        assert commit_results == [False], "try_commit() must refuse once the caller has abandoned"
        assert place_calls == [], "an abandoned call must never reach ib.placeOrder()"
    finally:
        release_block.set()  # never leave the worker thread blocked on teardown
        ib_worker.stop_ib_worker()
        ib_worker._worker._ib = None
        ib_worker._worker._client_id = None


# ---------------------------------------------------------------------------
# 5. _IbWorker-level race, commit-wins branch: fn commits before the caller
#    can possibly time out, then the broker call itself hangs -- the caller
#    must see an explicit reconciliation-required error, never a clean
#    timeout, and exactly 1 placeOrder call happens once released.
# ---------------------------------------------------------------------------

def test_call_ib_commit_wins_surfaces_reconciliation_required(monkeypatch):
    """
    Forces the exact interleaving the ECC reviewer used to fail Round 2: fn
    calls try_commit() (which succeeds -- nothing has abandoned it yet) and
    ONLY THEN, inside the now-committed placeOrder call itself, blocks past
    the caller's timeout. try_commit() winning the lock before the timeout
    can even fire is what makes this deterministic rather than a real race.
    The caller's later abandon() must see the commit and refuse to report a
    clean timeout -- call_ib() must raise an explicit 503
    "reconciliation required" instead, and exactly 1 placeOrder call must
    land once the block releases (the order is not undone by discovering the
    race after the fact -- it already went out).
    """
    ib_worker = _fresh_worker_fake_ib(monkeypatch)

    committed = threading.Event()
    release_place_order = threading.Event()
    place_calls: list[int] = []

    class _Broker:
        def isConnected(self):
            return True

        def disconnect(self):
            pass

        def sleep(self, _seconds):
            pass

        def placeOrder(self, *_a, **_kw):
            place_calls.append(1)
            release_place_order.wait(timeout=2.0)  # simulate a hung broker ack
            return object()

    def fn(ib):
        ok = ib_worker.call_try_commit()
        assert ok, "try_commit() must succeed before any timeout has had a chance to fire"
        committed.set()
        ib.placeOrder()  # blocks past the caller's timeout once inside
        return "reached end"

    ib_worker._worker._ib = _Broker()
    ib_worker._worker._client_id = 1
    try:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as excinfo:
            ib_worker.call_ib(fn, timeout=0.05)

        assert committed.wait(timeout=2.0), "fn never committed -- race not exercised"
        assert excinfo.value.status_code == 503
        detail = str(excinfo.value.detail).lower()
        assert "reconciliation required" in detail
        assert "unknown" in detail or "must be reconciled" in detail

        # The order was genuinely committed -- release it and confirm exactly
        # one placeOrder call actually happened (it is not, and must not be,
        # silently discarded just because the caller stopped waiting).
        release_place_order.set()
        time.sleep(0.2)
        assert place_calls == [1], "a committed call must place exactly once, never zero and never twice"
    finally:
        release_place_order.set()  # never leave the worker thread blocked on teardown
        ib_worker.stop_ib_worker()
        ib_worker._worker._ib = None
        ib_worker._worker._client_id = None


# ---------------------------------------------------------------------------
# 6. _CancelToken unit-level exhaustiveness: both orderings, no threading,
#    no timing dependency -- the contract holds independent of scheduling.
# ---------------------------------------------------------------------------

def test_cancel_token_abandon_before_commit_blocks_action():
    from app.services.ib_worker import _CancelToken

    token = _CancelToken()
    assert token.abandon() is True, "abandon() must report clean when nothing has committed yet"
    assert token.try_commit() is False, "try_commit() must refuse once abandoned"
    # Idempotence: a second abandon() must not flip the outcome.
    assert token.abandon() is True


def test_cancel_token_commit_before_abandon_surfaces_ambiguity():
    from app.services.ib_worker import _CancelToken

    token = _CancelToken()
    assert token.try_commit() is True, "try_commit() must succeed before anything abandons it"
    assert token.abandon() is False, "abandon() must report ambiguous once a commit has already won"
    # A later leg's try_commit() on the SAME (now-abandoned) token must
    # refuse -- no further orders once the caller has given up, even though
    # an earlier one already committed.
    assert token.try_commit() is False, "no further commits once abandoned, even after an earlier commit"


# ---------------------------------------------------------------------------
# 7. Route-level wiring check: _execute's placeOrder call site consults the
#    ATOMIC call_try_commit() (not a plain read) before every placeOrder.
# ---------------------------------------------------------------------------

def test_execute_refuses_placeorder_when_call_try_commit_denies(client, monkeypatch):
    """
    Complements sections 4-5: proves live.py's _execute actually wires the
    atomic call_try_commit() fence into the only placeOrder call site in the
    route, not just that the primitive exists in ib_worker.py. Simulates
    "already abandoned" directly (a real 60s+ outer timeout is impractical in
    a unit test — the outer execute_timeout is legs*per_leg_timeout + 60s).
    """
    import app.api.routes.live as live

    broker = _StaleBrokerStub(open_orders_mode="clear")
    _wire_common(monkeypatch, broker)
    monkeypatch.setattr(live, "call_try_commit", lambda: False)

    resp = _post(client)

    assert resp.status_code == 409, f"expected 409, got {resp.status_code}: {resp.text}"
    assert "already timed out" in resp.json()["detail"].lower()
    assert broker.place_calls == 0, "placeOrder must never be reached once call_try_commit() denies"
