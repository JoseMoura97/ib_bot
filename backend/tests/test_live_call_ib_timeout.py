"""
Phase 5 — IB timeout scenarios.

Covers two distinct timeout surfaces:

1. Outer basket-level timeout (`execute_timeout = legs * per_leg + 60s`):
   The outer `call_ib(_execute, timeout=execute_timeout)` raises
   `concurrent.futures.TimeoutError` when the entire execution function stalls
   (e.g. IB Gateway hangs mid-basket). The route must:
   - Write the idempotency row with status="ERROR"
   - Re-raise (client gets a 5xx)

2. Per-leg fill timeout with reqGlobalCancel (complementary to
   test_live_partial_fill.py), confirming that a single slow leg causes the
   entire basket to be cancelled via reqGlobalCancel and remaining legs to be
   skipped — tested separately here with an explicit 30s+ scenario label.
"""
from __future__ import annotations

import sys
import time
import types
import uuid
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import datetime

import pytest

from app.core.config import settings

_PORTFOLIO_ID = "00000000-0000-0000-0000-000000000002"
_ACCOUNT_ID = "U111111"


def _body(**overrides):
    return {
        "account_id": _ACCOUNT_ID,
        "portfolio_id": _PORTFOLIO_ID,
        "allocation_amount": 10_000.0,
        "max_orders": 5,
        "allow_short": False,
        "confirm": True,
        **overrides,
    }


def _make_preview(n_legs: int = 2, notional: float = 5_000.0):
    from app.api.routes.live import LiveRebalanceLeg, LiveRebalancePreviewOut

    legs = [
        LiveRebalanceLeg(
            ticker=f"TK{i}",
            target_weight=1 / n_legs,
            price=100.0,
            target_value=notional / n_legs,
            target_quantity=notional / n_legs / 100,
            current_quantity=0.0,
            delta_quantity=notional / n_legs / 100,
            side="BUY",
        )
        for i in range(n_legs)
    ]
    return LiveRebalancePreviewOut(
        as_of=datetime.utcnow(),
        portfolio_id=_PORTFOLIO_ID,  # type: ignore[arg-type]
        account_id=_ACCOUNT_ID,
        allocation_amount=notional,
        estimated_notional=notional,
        legs=legs,
    )


@pytest.fixture(autouse=True)
def _live_env(monkeypatch):
    monkeypatch.setattr(settings, "enable_live_trading", True)
    monkeypatch.setattr(settings, "live_dry_run", False)
    monkeypatch.setattr(settings, "trading_halt", False)


@pytest.fixture()
def _mock_ib_insync(monkeypatch):
    class _Stock:
        def __init__(self, symbol, exchange="SMART", currency="USD"):
            self.symbol = symbol

    class _MarketOrder:
        def __init__(self, action, total_quantity):
            self.action = action
            self.totalQuantity = total_quantity
            self.orderId = 0
            self.permId = 0
            self.account = ""

    stub = types.ModuleType("ib_insync")
    stub.Stock = _Stock
    stub.MarketOrder = _MarketOrder
    monkeypatch.setitem(sys.modules, "ib_insync", stub)


# ---------------------------------------------------------------------------
# 1. Outer basket-level timeout
# ---------------------------------------------------------------------------

def test_outer_basket_timeout_records_error(client, db_session, monkeypatch):
    """
    When call_ib raises TimeoutError at the basket level the route writes an
    ERROR idempotency row and does not swallow the exception silently.
    """
    def fake_call_ib_timeout(fn, *, timeout=10.0):
        # Simulate IB Gateway hanging for the outer execute call only.
        # Other call_ib uses (circuit-breaker, NLV check) must succeed.
        raise FuturesTimeout("IB Gateway did not respond within timeout")

    monkeypatch.setattr("app.api.routes.live._assert_account_allowed", lambda *a: None)
    monkeypatch.setattr("app.api.routes.live.market_is_open", lambda *a: (True, None))
    monkeypatch.setattr("app.api.routes.live._account_total_pnl", lambda *a: (0.0, 0.0))
    monkeypatch.setattr("app.api.routes.live._account_nlv", lambda *a: 200_000.0)
    monkeypatch.setattr("app.api.routes.live._build_preview", lambda *a, **kw: _make_preview())
    monkeypatch.setattr("app.api.routes.live.call_ib", fake_call_ib_timeout)
    monkeypatch.setattr("app.services.alerting.send_error_alert", lambda *a, **kw: None)
    monkeypatch.setattr("app.services.alerting.send_rebalance_alert", lambda *a, **kw: None)

    # TestClient re-raises server-side exceptions; catch it to inspect DB state.
    with pytest.raises(Exception):
        client.post(
            "/live/rebalance/execute",
            json=_body(),
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )

    # The idempotency row must be persisted with ERROR status so a retry
    # (same idempotency key) does not blindly re-execute while IB may still
    # be processing the original request.
    from app.models.ib_audit import LiveExecutionRequest
    rows = db_session.query(LiveExecutionRequest).filter_by(status="ERROR").all()
    assert rows, "Idempotency row must be written with status=ERROR after outer timeout"


def test_outer_basket_timeout_error_mentions_timeout(client, db_session, monkeypatch):
    """
    The error stored in the idempotency row should contain enough information
    for operators to diagnose the IB Gateway timeout.
    """
    def fake_call_ib_timeout(fn, *, timeout=10.0):
        raise FuturesTimeout("IB Gateway did not respond within timeout")

    monkeypatch.setattr("app.api.routes.live._assert_account_allowed", lambda *a: None)
    monkeypatch.setattr("app.api.routes.live.market_is_open", lambda *a: (True, None))
    monkeypatch.setattr("app.api.routes.live._account_total_pnl", lambda *a: (0.0, 0.0))
    monkeypatch.setattr("app.api.routes.live._account_nlv", lambda *a: 200_000.0)
    monkeypatch.setattr("app.api.routes.live._build_preview", lambda *a, **kw: _make_preview())
    monkeypatch.setattr("app.api.routes.live.call_ib", fake_call_ib_timeout)
    monkeypatch.setattr("app.services.alerting.send_error_alert", lambda *a, **kw: None)
    monkeypatch.setattr("app.services.alerting.send_rebalance_alert", lambda *a, **kw: None)

    with pytest.raises(Exception):
        client.post(
            "/live/rebalance/execute",
            json=_body(),
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )

    from app.models.ib_audit import LiveExecutionRequest
    row = db_session.query(LiveExecutionRequest).filter_by(status="ERROR").first()
    assert row is not None
    assert row.error is not None
    # The error field should not be blank so ops can correlate the audit trail
    assert len(row.error) > 0


# ---------------------------------------------------------------------------
# 2. Per-leg 30s+ timeout — reqGlobalCancel is called, basket aborted
# ---------------------------------------------------------------------------

class _SlowSubmittedStatus:
    status = "Submitted"
    filled = 0.0
    remaining = 5.0
    avgFillPrice = 0.0


class _SlowTrade:
    def __init__(self):
        self.orderStatus = _SlowSubmittedStatus()
        self.order = type("O", (), {"orderId": 3, "permId": 4})()
        self.fills = []


class _SlowIB:
    """
    Simulates a 30s+ scenario: orders are placed but fill confirmations never
    arrive within the per-leg timeout window.
    """

    def __init__(self):
        self.placed: list[str] = []
        self.cancel_calls = 0

    def qualifyContracts(self, *a):
        pass

    def sleep(self, n):
        pass  # do not actually block; wall-clock drives the timeout

    def placeOrder(self, contract, order):
        self.placed.append(getattr(contract, "symbol", "?"))
        return _SlowTrade()

    def reqGlobalCancel(self):
        self.cancel_calls += 1


def test_per_leg_30s_timeout_calls_req_global_cancel(
    client, db_session, monkeypatch, _mock_ib_insync
):
    """
    When a leg stays Submitted past per_leg_timeout (emulating >30s stall),
    reqGlobalCancel must be invoked and the remaining legs must be skipped.
    This mirrors the real-world scenario where IB Gateway hangs mid-basket.
    """
    monkeypatch.setattr(settings, "live_per_leg_timeout_seconds", 0.05)

    fake_ib = _SlowIB()

    def fake_call_ib(fn, *, timeout=10.0):
        return fn(fake_ib)

    monkeypatch.setattr("app.api.routes.live._assert_account_allowed", lambda *a: None)
    monkeypatch.setattr("app.api.routes.live.market_is_open", lambda *a: (True, None))
    monkeypatch.setattr("app.api.routes.live._account_total_pnl", lambda *a: (0.0, 0.0))
    monkeypatch.setattr("app.api.routes.live._account_nlv", lambda *a: 200_000.0)
    monkeypatch.setattr("app.api.routes.live._build_preview", lambda *a, **kw: _make_preview(n_legs=3))
    monkeypatch.setattr("app.api.routes.live.call_ib", fake_call_ib)
    monkeypatch.setattr("app.services.alerting.send_error_alert", lambda *a, **kw: None)
    monkeypatch.setattr("app.services.alerting.send_rebalance_alert", lambda *a, **kw: None)

    resp = client.post(
        "/live/rebalance/execute",
        json=_body(),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    assert resp.status_code in (200, 409), f"Unexpected status {resp.status_code}: {resp.text}"
    assert fake_ib.cancel_calls >= 1, "reqGlobalCancel must fire after per-leg timeout"
    assert len(fake_ib.placed) == 1, (
        f"Only the first leg should have been placed; got {fake_ib.placed}"
    )
    assert "timeout" in str(resp.json()).lower(), "Response must mention fill-timeout"


# ---------------------------------------------------------------------------
# 3. Circuit-breaker P&L call timeout is non-fatal
# ---------------------------------------------------------------------------

def test_pnl_circuit_breaker_timeout_is_non_fatal(client, db_session, monkeypatch, _mock_ib_insync):
    """
    If _account_total_pnl itself times out (IB is slow to respond to
    reqAccountSummary), the circuit-breaker block must fail silently and allow
    execution to proceed.  A P&L read failure must never block a valid order.
    """

    def pnl_timeout(*a):
        raise FuturesTimeout("P&L query timed out")

    fake_ib = _SlowIB()

    def fake_call_ib(fn, *, timeout=10.0):
        return fn(fake_ib)

    monkeypatch.setattr(settings, "live_per_leg_timeout_seconds", 0.05)
    monkeypatch.setattr("app.api.routes.live._assert_account_allowed", lambda *a: None)
    monkeypatch.setattr("app.api.routes.live.market_is_open", lambda *a: (True, None))
    monkeypatch.setattr("app.api.routes.live._account_total_pnl", pnl_timeout)
    monkeypatch.setattr("app.api.routes.live._account_nlv", lambda *a: 200_000.0)
    monkeypatch.setattr("app.api.routes.live._build_preview", lambda *a, **kw: _make_preview(n_legs=1))
    monkeypatch.setattr("app.api.routes.live.call_ib", fake_call_ib)
    monkeypatch.setattr("app.services.alerting.send_error_alert", lambda *a, **kw: None)
    monkeypatch.setattr("app.services.alerting.send_rebalance_alert", lambda *a, **kw: None)

    resp = client.post(
        "/live/rebalance/execute",
        json=_body(),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    # The P&L timeout must not result in an unexpected 5xx from the guard block;
    # execution should continue (and fail on the per-leg timeout, not the P&L read).
    assert resp.status_code in (200, 409), (
        f"P&L timeout should be swallowed, not propagated; got {resp.status_code}: {resp.text}"
    )
