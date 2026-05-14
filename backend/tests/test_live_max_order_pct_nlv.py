"""Phase 5 tests — server-side LIVE_MAX_ORDER_PCT_NLV cap enforcement."""
from __future__ import annotations

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


def _make_preview(estimated_notional: float = 5_000.0):
    from app.api.routes.live import LiveRebalanceLeg, LiveRebalancePreviewOut

    leg = LiveRebalanceLeg(
        ticker="AAPL",
        target_weight=1.0,
        price=150.0,
        target_value=estimated_notional,
        target_quantity=estimated_notional / 150,
        current_quantity=0.0,
        delta_quantity=estimated_notional / 150,
        side="BUY",
    )
    return LiveRebalancePreviewOut(
        as_of=datetime.utcnow(),
        portfolio_id=_PORTFOLIO_ID,  # type: ignore[arg-type]
        account_id=_ACCOUNT_ID,
        allocation_amount=estimated_notional,
        estimated_notional=estimated_notional,
        legs=[leg],
    )


@pytest.fixture(autouse=True)
def _live_env(monkeypatch):
    monkeypatch.setattr(settings, "enable_live_trading", True)
    monkeypatch.setattr(settings, "live_dry_run", False)
    monkeypatch.setattr(settings, "trading_halt", False)


def _common_guards(monkeypatch, nlv: float, notional: float):
    """Patch all guards up to (and including) the NLV cap check."""
    monkeypatch.setattr("app.api.routes.live._assert_account_allowed", lambda *a: None)
    monkeypatch.setattr("app.api.routes.live.market_is_open", lambda *a: (True, None))
    monkeypatch.setattr("app.api.routes.live._account_total_pnl", lambda *a: (0.0, 0.0))
    monkeypatch.setattr("app.api.routes.live._account_nlv", lambda *a: nlv)
    monkeypatch.setattr(
        "app.api.routes.live._build_preview",
        lambda *a, **kw: _make_preview(estimated_notional=notional),
    )
    monkeypatch.setattr("app.services.alerting.send_error_alert", lambda *a, **kw: None)
    monkeypatch.setattr("app.services.alerting.send_rebalance_alert", lambda *a, **kw: None)


def test_nlv_cap_rejects_oversized_execute(client, monkeypatch):
    """
    When estimated_notional > NLV * LIVE_MAX_ORDER_PCT_NLV the endpoint returns 403.

    Setup: NLV = $10 000, cap = 50% → $5 000 cap.
    Notional = $8 000 → exceeds cap.
    """
    monkeypatch.setattr(settings, "live_max_order_pct_nlv", 0.50)
    _common_guards(monkeypatch, nlv=10_000.0, notional=8_000.0)

    resp = client.post(
        "/live/rebalance/execute",
        json=_body(),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert "nlv" in detail.lower() or "cap" in detail.lower() or "notional" in detail.lower()


def test_nlv_cap_passes_within_limit(client, monkeypatch):
    """
    When estimated_notional < NLV * LIVE_MAX_ORDER_PCT_NLV the NLV guard passes
    and the request proceeds to the IB execute step.

    Setup: NLV = $100 000, cap = 50% → $50 000 cap.
    Notional = $5 000 → well within cap.
    We inject a fake call_ib that records the call and returns a minimal result
    so the endpoint completes successfully.
    """
    monkeypatch.setattr(settings, "live_max_order_pct_nlv", 0.50)
    _common_guards(monkeypatch, nlv=100_000.0, notional=5_000.0)

    executed: list[str] = []

    def _fake_execute(fn, *, timeout=10.0):
        executed.append("called")
        # Return a minimal results list (no legs actually placed in this unit test)
        return []

    monkeypatch.setattr("app.api.routes.live.call_ib", _fake_execute)

    resp = client.post(
        "/live/rebalance/execute",
        json=_body(),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    # The NLV cap did NOT reject this request — it got all the way to IB execute
    assert executed == ["called"], "call_ib must be reached when notional is within the NLV cap"
    # _execute returns [] so the preview is returned as-is (no order legs placed)
    assert resp.status_code == 200
