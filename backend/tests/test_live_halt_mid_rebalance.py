"""Phase 5 tests — cooperative trading halt behaviour."""
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
    """Stub ib_insync so _execute's dynamic import works inside the AnyIO worker thread
    (real ib_insync calls asyncio.get_event_loop() which raises RuntimeError there)."""

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
# Halt blocks a new execute request
# ---------------------------------------------------------------------------

def test_halt_blocks_new_execute(client, monkeypatch):
    """With trading_halt active the endpoint returns 403 before any IB call."""
    monkeypatch.setattr(settings, "trading_halt", True)

    ib_calls: list[str] = []

    def _no_ib(fn, *, timeout=10.0):
        ib_calls.append("called")
        raise AssertionError("IB must not be reached when halted")

    monkeypatch.setattr("app.api.routes.live.call_ib", _no_ib)
    monkeypatch.setattr("app.services.alerting.send_error_alert", lambda *a, **kw: None)

    resp = client.post(
        "/live/rebalance/execute",
        json=_body(),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 403
    assert "halt" in resp.json()["detail"].lower()
    assert ib_calls == []


# ---------------------------------------------------------------------------
# Halt mid-rebalance: reqGlobalCancel is called and remaining legs are skipped
# ---------------------------------------------------------------------------

class _FakeOrderStatus:
    def __init__(self, status: str = "Filled"):
        self.status = status
        self.filled = 25.0
        self.remaining = 0.0
        self.avgFillPrice = 100.0


class _FakeFill:
    class _Exec:
        orderId = 1
        permId = 2
        execId = "exec-1"
        time = "20260509 10:00:00"
        shares = 25.0
        price = 100.0

    execution = _Exec()


class _FakeTrade:
    def __init__(self, status: str = "Filled"):
        self.orderStatus = _FakeOrderStatus(status)
        self.order = type("O", (), {"orderId": 1, "permId": 2})()
        self.fills = [_FakeFill()]


class _HaltMidRunFakeIB:
    """Fills the first leg and then sets trading_halt so leg 2 is aborted."""

    def __init__(self):
        self.placed: list[str] = []
        self.cancel_calls = 0

    def qualifyContracts(self, *a):
        pass

    def sleep(self, n):
        pass

    def placeOrder(self, contract, order):
        symbol = getattr(contract, "symbol", "?")
        self.placed.append(symbol)
        # Trigger cooperative halt after the very first leg is submitted
        if len(self.placed) == 1:
            settings.trading_halt = True
        return _FakeTrade("Filled")

    def reqGlobalCancel(self):
        self.cancel_calls += 1


def test_halt_mid_rebalance_aborts_and_cancels(client, db_session, monkeypatch, _mock_ib_insync):
    """After the first leg, a halt trips reqGlobalCancel and skips remaining legs."""
    monkeypatch.setattr(settings, "live_per_leg_timeout_seconds", 5)

    fake_ib = _HaltMidRunFakeIB()

    def fake_call_ib(fn, *, timeout=10.0):
        return fn(fake_ib)

    monkeypatch.setattr("app.api.routes.live._assert_account_allowed", lambda *a: None)
    monkeypatch.setattr("app.api.routes.live.market_is_open", lambda *a: (True, None))
    monkeypatch.setattr("app.api.routes.live._account_total_pnl", lambda *a: (0.0, 0.0))
    monkeypatch.setattr("app.api.routes.live._account_nlv", lambda *a: 200_000.0)
    monkeypatch.setattr("app.api.routes.live._build_preview", lambda *a, **kw: _make_preview(n_legs=2))
    monkeypatch.setattr("app.api.routes.live.call_ib", fake_call_ib)
    monkeypatch.setattr("app.services.alerting.send_error_alert", lambda *a, **kw: None)
    monkeypatch.setattr("app.services.alerting.send_halt_alert", lambda *a, **kw: None)
    monkeypatch.setattr("app.services.alerting.send_rebalance_alert", lambda *a, **kw: None)

    resp = client.post(
        "/live/rebalance/execute",
        json=_body(),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    # Halt fires mid-basket → endpoint returns 409 (INCOMPLETE rebalance)
    assert resp.status_code in (200, 409)
    assert fake_ib.cancel_calls >= 1, "reqGlobalCancel must be called when halt fires mid-rebalance"
    assert len(fake_ib.placed) == 1, "Only the first leg must be placed before halt fires"

    # Reset halt so it doesn't bleed into other tests
    settings.trading_halt = False
