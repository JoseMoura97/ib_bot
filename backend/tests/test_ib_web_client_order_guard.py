"""Broker-stub proof that every Client Portal submission crosses the shared guard.

Each rejection is asserted against the broker stub's submission ledger, rather
than merely checking an exception or HTTP-shaped error response.
"""
from __future__ import annotations

import importlib
import inspect
import sys
import types
from threading import Lock

import pytest

from system.execution.gateway_state import GatewayState, GatewayStateGuardError
from system.execution.order_preflight import OrderPreFlightGuardError


_ACCOUNT = "U-WEB-ALLOWED"


class _Result:
    success = True
    data = {"ok": True}
    message = ""


class _BrokerStub:
    """Independent submission oracle: only the irreversible endpoint increments it."""

    def __init__(self) -> None:
        self.submissions: list[tuple[str, list[dict[str, object]]]] = []

    def iserver_secdef_search(self, **_kwargs):
        return types.SimpleNamespace(success=True, data=[{"conid": 12345}])

    def iserver_place_orders(self, account_id, orders):
        self.submissions.append((account_id, orders))
        return _Result()


def _module(monkeypatch):
    ibind = types.ModuleType("ibind")
    ibind.IbkrClient = object
    monkeypatch.setitem(sys.modules, "ibind", ibind)
    sys.modules.pop("system.execution.ib_web_client", None)
    return importlib.import_module("system.execution.ib_web_client")


def _client(monkeypatch, state: GatewayState | None = None):
    module = _module(monkeypatch)
    broker = _BrokerStub()
    client = module.IBWebClient.__new__(module.IBWebClient)
    client.client = broker
    client._submitted_notional_usd = 0.0
    client._submitted_idempotency_keys = set()
    client._notional_lock = Lock()
    client._gateway_state_provider = lambda: state or GatewayState(True, 1_000.0, None, False, "healthy")
    return client, broker, module


def _clear_policy(monkeypatch) -> None:
    for name in (
        "TRADING_HALT",
        "LIVE_ALLOWED_ACCOUNTS",
        "LIVE_MAX_ORDER_NOTIONAL_USD",
        "LIVE_MAX_AGGREGATE_NOTIONAL_USD",
    ):
        monkeypatch.delenv(name, raising=False)


def _submit(client, *, key="web-case", **overrides):
    request = {
        "account_id": _ACCOUNT,
        "ticker": "AAPL",
        "side": "BUY",
        "quantity": 10,
        "estimated_price": 100.0,
        "idempotency_key": key,
    }
    request.update(overrides)
    return client.place_market_order(**request)


@pytest.mark.parametrize(
    ("name", "configure", "order_args"),
    [
        ("halt", lambda m: m.setenv("TRADING_HALT", "1"), {}),
        (
            "disallowed_account",
            lambda m: m.setenv("LIVE_ALLOWED_ACCOUNTS", _ACCOUNT),
            {"account_id": "U-WEB-DENIED"},
        ),
        (
            "per_order_notional_limit",
            lambda m: m.setenv("LIVE_MAX_ORDER_NOTIONAL_USD", "999"),
            {},
        ),
        (
            "aggregate_notional_limit",
            lambda m: m.setenv("LIVE_MAX_AGGREGATE_NOTIONAL_USD", "999"),
            {},
        ),
    ],
)
def test_policy_bypass_attempts_submit_zero_orders(monkeypatch, name, configure, order_args):
    """halt and disallowed-account / notional-limit bypass attempts submit 0 orders.

    Frozen-acceptance coverage map for this file. Every web-client bypass
    class is asserted to reach 0 broker-stub submissions:
      - halt                -> this test, case "halt"
      - disallowed-account  -> this test, case "disallowed_account"
      - notional-limit      -> this test, cases "per_order_notional_limit"
                               and "aggregate_notional_limit"
      - stale-Gateway       -> test_stale_gateway_bypass_attempt_submits_zero_orders
      - malformed-order     -> test_malformed_order_bypass_attempts_submit_zero_orders
    The single allowed case submits exactly 1 expected payload:
      - test_allowed_web_order_submits_exactly_one_expected_payload
    """
    _clear_policy(monkeypatch)
    configure(monkeypatch)
    client, broker, _ = _client(monkeypatch)
    if name == "aggregate_notional_limit":
        client._submitted_notional_usd = 100.0

    with pytest.raises(OrderPreFlightGuardError):
        _submit(client, key=f"{name}-key", **order_args)

    assert broker.submissions == [], f"{name} reached Client Portal's order endpoint"


def test_stale_gateway_bypass_attempt_submits_zero_orders(monkeypatch):
    _clear_policy(monkeypatch)
    stale = GatewayState(True, 1.0, None, False, "stale")
    client, broker, _ = _client(monkeypatch, state=stale)

    with pytest.raises(GatewayStateGuardError, match="stale"):
        _submit(client, key="stale-gateway-key")

    assert broker.submissions == []


@pytest.mark.parametrize(
    "order_args",
    [
        {"ticker": "AAPL;DROP"},
        {"side": "HOLD"},
        {"quantity": 0},
        {"estimated_price": float("nan")},
        {"idempotency_key": ""},
    ],
)
def test_malformed_order_bypass_attempts_submit_zero_orders(monkeypatch, order_args):
    _clear_policy(monkeypatch)
    client, broker, module = _client(monkeypatch)

    with pytest.raises(module.WebOrderValidationError):
        _submit(client, key="malformed-key", **order_args)

    assert broker.submissions == []


def test_duplicate_idempotency_key_cannot_submit_a_second_order(monkeypatch):
    _clear_policy(monkeypatch)
    client, broker, module = _client(monkeypatch)

    _submit(client, key="once-only")
    with pytest.raises(module.WebOrderValidationError, match="already been submitted"):
        _submit(client, key="once-only")

    assert len(broker.submissions) == 1


def test_allowed_web_order_submits_exactly_one_expected_payload(monkeypatch):
    _clear_policy(monkeypatch)
    monkeypatch.setenv("LIVE_ALLOWED_ACCOUNTS", _ACCOUNT)
    monkeypatch.setenv("LIVE_MAX_ORDER_NOTIONAL_USD", "1000")
    monkeypatch.setenv("LIVE_MAX_AGGREGATE_NOTIONAL_USD", "1000")
    client, broker, _ = _client(monkeypatch)

    assert _submit(client, key="allowed-once") == {"ok": True}
    assert broker.submissions == [
        (_ACCOUNT, [{"conid": 12345, "orderType": "MKT", "side": "BUY", "quantity": 10.0, "tif": "DAY"}])
    ]


def test_only_web_client_submission_site_is_the_guarded_wrapper(monkeypatch):
    """Audit the module: no second Client Portal order endpoint can bypass guards."""
    _, _, module = _client(monkeypatch)
    source = inspect.getsource(module.IBWebClient)

    assert source.count("iserver_place_orders") == 1
    assert "def _submit_guarded_order" in source
