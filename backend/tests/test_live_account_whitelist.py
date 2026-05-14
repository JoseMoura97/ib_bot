"""Phase 5 tests — server-side account whitelist check."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.core.config import settings

_PORTFOLIO_ID = "00000000-0000-0000-0000-000000000001"
_ALLOWED_ACCOUNT = "U111111"
_BAD_ACCOUNT = "U999999"


def _body(account_id: str = _ALLOWED_ACCOUNT, **overrides):
    return {
        "account_id": account_id,
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


def test_whitelist_rejects_unknown_account(client, monkeypatch):
    """An account not returned by IB.managedAccounts() is rejected with 400."""

    def _strict_whitelist(account_id: str) -> None:
        # Simulate: IB reports only _ALLOWED_ACCOUNT; any other account is rejected
        if account_id != _ALLOWED_ACCOUNT:
            raise HTTPException(
                status_code=400,
                detail=f"account {account_id} is not in IB managed accounts",
            )

    monkeypatch.setattr("app.api.routes.live._assert_account_allowed", _strict_whitelist)
    monkeypatch.setattr("app.services.alerting.send_error_alert", lambda *a, **kw: None)

    resp = client.post(
        "/live/rebalance/execute",
        json=_body(account_id=_BAD_ACCOUNT),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert resp.status_code == 400
    assert _BAD_ACCOUNT in resp.json()["detail"]


def test_whitelist_accepts_managed_account(client, monkeypatch):
    """A known managed account passes the whitelist and proceeds to later guards."""
    calls: list[str] = []

    def _permissive_whitelist(account_id: str) -> None:
        calls.append(account_id)

    monkeypatch.setattr("app.api.routes.live._assert_account_allowed", _permissive_whitelist)
    # Stop after the whitelist at market-open check so we don't need more mocks
    monkeypatch.setattr("app.api.routes.live.market_is_open", lambda *a: (False, "market closed"))
    monkeypatch.setattr("app.services.alerting.send_error_alert", lambda *a, **kw: None)

    resp = client.post(
        "/live/rebalance/execute",
        json=_body(account_id=_ALLOWED_ACCOUNT),
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    # Rejected at market-closed, NOT at whitelist — proves whitelist passed the account
    assert resp.status_code == 403
    assert "market" in resp.json()["detail"].lower() or "closed" in resp.json()["detail"].lower()
    assert calls == [_ALLOWED_ACCOUNT]


def test_whitelist_uses_live_allowed_accounts_env(client, monkeypatch):
    """When LIVE_ALLOWED_ACCOUNTS is set, accounts not in the list get 400 even if
    they appear in IB managedAccounts()."""
    import app.api.routes.live as live_module

    # Patch call_ib so managedAccounts returns both accounts
    def _fake_call_ib(fn, *, timeout=10.0):
        class _FakeIB:
            def managedAccounts(self):
                return [_ALLOWED_ACCOUNT, _BAD_ACCOUNT]

        return fn(_FakeIB())

    monkeypatch.setattr(live_module, "call_ib", _fake_call_ib)
    # Clear the module-level managed-accounts cache so call_ib is actually invoked
    monkeypatch.setattr(live_module, "_managed_accounts_cache", [])
    monkeypatch.setattr(live_module, "_managed_accounts_cache_at", 0.0)
    monkeypatch.setattr(settings, "live_allowed_accounts", _ALLOWED_ACCOUNT)

    with pytest.raises(HTTPException) as exc_info:
        live_module._assert_account_allowed(_BAD_ACCOUNT)

    assert exc_info.value.status_code == 400
    assert _BAD_ACCOUNT in exc_info.value.detail
