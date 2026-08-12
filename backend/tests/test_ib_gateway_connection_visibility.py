import sys
import types

import pytest
from fastapi import HTTPException


class _FakeGateway:
    def __init__(self) -> None:
        self.connected = False
        self.fail_connect = False

    def isConnected(self):
        return self.connected

    def connect(self, *_args, **_kwargs):
        if self.fail_connect:
            raise ConnectionError("gateway unavailable")
        self.connected = True

    def disconnect(self):
        self.connected = False


def _worker(monkeypatch, now, gateway):
    module = types.ModuleType("ib_insync")
    module.IB = lambda: gateway
    monkeypatch.setitem(sys.modules, "ib_insync", module)

    from app.services.ib_worker import _IbWorker

    return _IbWorker(clock=lambda: now[0], disconnect_alert_threshold_seconds=30.0)


def test_healthy_gateway_state_is_exposed_by_live_status(client, monkeypatch):
    now = [100.0]
    worker = _worker(monkeypatch, now, _FakeGateway())
    worker._ensure_connected()

    import app.api.routes.live as live

    monkeypatch.setattr(live, "current_ib_connection", worker.get_connection_info)
    response = client.get("/live/status")

    assert response.status_code == 200
    assert response.json()["connected"] is True
    assert response.json()["last_connect_ok_at"] == 100.0
    assert response.json()["last_error"] is None
    assert response.json()["consecutive_failures"] == 0


def test_forced_connect_failure_is_visible_within_one_poll(monkeypatch):
    now = [100.0]
    gateway = _FakeGateway()
    gateway.fail_connect = True
    worker = _worker(monkeypatch, now, gateway)

    with pytest.raises(HTTPException):
        worker._ensure_connected()

    state = worker.get_connection_info()
    assert state["connected"] is False
    assert state["consecutive_failures"] >= 1
    assert "Cannot connect to IB Gateway" in state["last_error"]


def test_outage_past_injected_threshold_alerts_exactly_once(monkeypatch):
    now = [100.0]
    gateway = _FakeGateway()
    gateway.fail_connect = True
    worker = _worker(monkeypatch, now, gateway)
    alerts = []
    monkeypatch.setattr(
        "app.services.alerting.send_gateway_disconnected_alert",
        lambda **kwargs: alerts.append(kwargs),
    )

    for timestamp in (100.0, 129.0, 130.0, 190.0):
        now[0] = timestamp
        with pytest.raises(HTTPException):
            worker._ensure_connected()

    assert len(alerts) == 1
    assert alerts[0]["error"]


def test_outage_before_injected_threshold_does_not_alert(monkeypatch):
    now = [100.0]
    gateway = _FakeGateway()
    gateway.fail_connect = True
    worker = _worker(monkeypatch, now, gateway)
    alerts = []
    monkeypatch.setattr(
        "app.services.alerting.send_gateway_disconnected_alert",
        lambda **kwargs: alerts.append(kwargs),
    )

    for timestamp in (100.0, 129.9):
        now[0] = timestamp
        with pytest.raises(HTTPException):
            worker._ensure_connected()

    assert alerts == []


def test_recovery_resets_connection_counters_and_outage_alert_state(monkeypatch):
    now = [100.0]
    gateway = _FakeGateway()
    gateway.fail_connect = True
    worker = _worker(monkeypatch, now, gateway)
    alerts = []
    monkeypatch.setattr(
        "app.services.alerting.send_gateway_disconnected_alert",
        lambda **kwargs: alerts.append(kwargs),
    )

    for timestamp in (100.0, 130.0):
        now[0] = timestamp
        with pytest.raises(HTTPException):
            worker._ensure_connected()
    assert len(alerts) == 1

    gateway.fail_connect = False
    now[0] = 131.0
    worker._ensure_connected()
    state = worker.get_connection_info()
    assert state["connected"] is True
    assert state["consecutive_failures"] == 0
    assert state["last_error"] is None

    gateway.disconnect()
    gateway.fail_connect = True
    for timestamp in (200.0, 230.0):
        now[0] = timestamp
        with pytest.raises(HTTPException):
            worker._ensure_connected()
    assert len(alerts) == 2
