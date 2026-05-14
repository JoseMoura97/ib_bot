"""Phase 5 tests — per-leg fill timeout aborts the basket and calls reqGlobalCancel."""
from __future__ import annotations

import sys
import types
import uuid
from datetime import datetime

import pytest

from app.core.config import settings

_PORTFOLIO_ID = "00000000-0000-0000-0000-000000000001"
_ACCOUNT_ID = "U999999"


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
            ticker=f"TICK{i}",
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
    """Inject a stub ib_insync so _execute's import works in the AnyIO worker thread."""

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


class _SubmittedForeverStatus:
    status = "Submitted"
    filled = 0.0
    remaining = 10.0
    avgFillPrice = 0.0


class _SubmittedForeverTrade:
    def __init__(self):
        self.orderStatus = _SubmittedForeverStatus()
        self.order = type("O", (), {"orderId": 1, "permId": 2})()
        self.fills = []


class _PartialFillFakeIB:
    """Immediately returns a trade that never leaves Submitted status."""

    def __init__(self):
        self.placed: list[str] = []
        self.cancel_calls = 0

    def qualifyContracts(self, *a):
        pass

    def sleep(self, n):
        # Do not actually sleep so the timeout expires based on wall-clock
        pass

    def placeOrder(self, contract, order):
        self.placed.append(getattr(contract, "symbol", "?"))
        return _SubmittedForeverTrade()

    def reqGlobalCancel(self):
        self.cancel_calls += 1


def test_partial_fill_timeout_aborts_basket(client, db_session, monkeypatch, _mock_ib_insync):
    """
    When an order stays in Submitted indefinitely the per-leg timeout fires,
    reqGlobalCancel is called, and remaining legs are skipped.
    """
    # Very short timeout so the test does not actually wait 60 s
    monkeypatch.setattr(settings, "live_per_leg_timeout_seconds", 0.1)

    fake_ib = _PartialFillFakeIB()

    def fake_call_ib(fn, *, timeout=10.0):
        return fn(fake_ib)

    monkeypatch.setattr("app.api.routes.live._assert_account_allowed", lambda *a: None)
    monkeypatch.setattr("app.api.routes.live.market_is_open", lambda *a: (True, None))
    monkeypatch.setattr("app.api.routes.live._account_total_pnl", lambda *a: (0.0, 0.0))
    monkeypatch.setattr("app.api.routes.live._account_nlv", lambda *a: 200_000.0)
    monkeypatch.setattr("app.api.routes.live._build_preview", lambda *a, **kw: _make_preview(n_legs=2))
    monkeypatch.setattr("app.api.routes.live.call_ib", fake_call_ib)
    monkeypatch.setattr("app.services.alerting.send_error_alert", lambda *a, **kw: None)
    monkeypatch.setattr("app.services.alerting.send_rebalance_alert", lambda *a, **kw: None)

    resp = client.post(
        "/live/rebalance/execute",
        json=_body(),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    assert resp.status_code in (200, 409)
    assert fake_ib.cancel_calls >= 1, "reqGlobalCancel must be called after fill timeout"

    # After the first leg times out the basket is aborted — second leg must not be placed
    assert len(fake_ib.placed) == 1, "Remaining legs must be skipped after first-leg timeout"

    # Response detail or body should mention the timeout
    detail_or_body = resp.json()
    text = str(detail_or_body).lower()
    assert "timeout" in text, "Response must mention fill-timeout"
