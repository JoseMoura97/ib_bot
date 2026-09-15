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
