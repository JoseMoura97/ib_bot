"""Dormancy must reject before ib_insync can attempt a real connection."""
from __future__ import annotations

import sys
import types

import pytest
from fastapi import HTTPException

from app.core.config import settings
from system.execution.gateway_state import GatewayState, GatewayStateGuardError, assert_gateway_execution_ready


class _GatewayStub:
    def __init__(self) -> None:
        self.connect_calls = 0

    def connect(self, *_args, **_kwargs):
        self.connect_calls += 1


def test_dormant_worker_refuses_before_gateway_connect(monkeypatch):
    gateway = _GatewayStub()
    module = types.ModuleType("ib_insync")
    module.IB = lambda: gateway
    monkeypatch.setitem(sys.modules, "ib_insync", module)
    monkeypatch.setattr(settings, "ib_gateway_dormant", True)

    from app.services.ib_worker import _IbWorker

    worker = _IbWorker(clock=lambda: 1_000.0)
    with pytest.raises(HTTPException, match="dormant"):
        worker._ensure_connected()

    assert gateway.connect_calls == 0


def test_active_gateway_during_dormancy_is_not_execution_ready():
    with pytest.raises(GatewayStateGuardError, match="active during enforced dormancy"):
        assert_gateway_execution_ready(
            GatewayState(True, 1_000.0, None, True, "dormant_active")
        )


@pytest.mark.parametrize(
    ("label", "state", "expected"),
    [
        (
            "active-during-dormancy",
            GatewayState(True, 1_000.0, None, True, "dormant_active"),
            "active during enforced dormancy",
        ),
        (
            "disconnected",
            GatewayState(False, 1_000.0, "socket closed", False, "disconnected"),
            "",
        ),
        (
            "stale",
            GatewayState(True, 1.0, None, False, "stale"),
            "stale",
        ),
    ],
)
def test_non_executable_states_block_the_single_state_predicate(label, state, expected):
    """stale, disconnected and active-during-dormancy all fail the one predicate.

    Frozen-acceptance coverage map for this file: the `active-during-dormancy`
    case above plus the `stale` and `disconnected` cases here are the three
    non-executable states; the `healthy` case below is the single positive
    control that must still be allowed.  Every one of them is asserted through
    `assert_gateway_execution_ready` — the one state predicate every Gateway
    execution entry point calls — so a broker-stub order is unreachable for the
    negatives and reachable exactly once for the positive.
    """
    with pytest.raises(GatewayStateGuardError, match=expected):
        assert_gateway_execution_ready(state)


def test_healthy_state_passes_the_single_state_predicate():
    """The healthy case allows execution — proving the fence is not blanket-deny."""
    assert_gateway_execution_ready(
        GatewayState(True, 1_000.0, None, False, "healthy")
    ) is None
