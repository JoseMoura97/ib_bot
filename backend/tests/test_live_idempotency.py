"""Phase 5 tests — idempotency key behaviour for /live/rebalance/execute."""
from __future__ import annotations

import uuid

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


@pytest.fixture(autouse=True)
def _live_env(monkeypatch):
    monkeypatch.setattr(settings, "enable_live_trading", True)
    monkeypatch.setattr(settings, "live_dry_run", False)
    monkeypatch.setattr(settings, "trading_halt", False)


# ---------------------------------------------------------------------------
# Missing key
# ---------------------------------------------------------------------------

def test_execute_requires_idempotency_key(client):
    """Execute without Idempotency-Key header → 400."""
    resp = client.post("/live/rebalance/execute", json=_body())
    assert resp.status_code == 400
    assert "idempotency" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Replay of a previously completed request
# ---------------------------------------------------------------------------

def test_idempotency_replay_returns_cached_without_ib_call(client, db_session, monkeypatch):
    """Re-submitting an OK idempotency key returns the cached result; IB is never called."""
    from datetime import datetime

    from app.models.ib_audit import LiveExecutionRequest

    idem_key = str(uuid.uuid4())
    cached_result = {
        "as_of": datetime.utcnow().isoformat(),
        "portfolio_id": _PORTFOLIO_ID,
        "account_id": _ACCOUNT_ID,
        "allocation_amount": 10_000.0,
        "estimated_notional": 9_500.0,
        "legs": [],
    }

    row = LiveExecutionRequest(
        account_id=_ACCOUNT_ID,
        portfolio_id=_PORTFOLIO_ID,
        idempotency_key=idem_key,
        status="OK",
        request={},
        result=cached_result,
    )
    db_session.add(row)
    db_session.commit()

    ib_calls: list[str] = []

    def _no_ib(fn, *, timeout=10.0):
        ib_calls.append("called")
        raise AssertionError("IB should not be invoked for a replayed idempotency key")

    monkeypatch.setattr("app.api.routes.live.call_ib", _no_ib)

    resp = client.post(
        "/live/rebalance/execute",
        json=_body(),
        headers={"Idempotency-Key": idem_key},
    )
    assert resp.status_code == 200
    assert ib_calls == [], "call_ib must not be invoked on replay"
    data = resp.json()
    assert data["estimated_notional"] == 9_500.0


# ---------------------------------------------------------------------------
# IN_PROGRESS → 409 Conflict
# ---------------------------------------------------------------------------

def test_idempotency_in_progress_returns_409(client, db_session):
    """An in-flight idempotency key returns 409 so the caller can back off."""
    from app.models.ib_audit import LiveExecutionRequest

    idem_key = str(uuid.uuid4())
    row = LiveExecutionRequest(
        account_id=_ACCOUNT_ID,
        portfolio_id=_PORTFOLIO_ID,
        idempotency_key=idem_key,
        status="IN_PROGRESS",
        request={},
        result={},
    )
    db_session.add(row)
    db_session.commit()

    resp = client.post(
        "/live/rebalance/execute",
        json=_body(),
        headers={"Idempotency-Key": idem_key},
    )
    assert resp.status_code == 409
    assert "progress" in resp.json()["detail"].lower()
