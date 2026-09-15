"""Observable health contract tests; no Gateway socket is opened."""
from __future__ import annotations

from system.execution.gateway_state import GatewayState


def test_live_status_exposes_canonical_gateway_health_contract(client, monkeypatch):
    import app.api.routes.live as live

    state = GatewayState(
        connected=True, last_success=1_000.0, last_error=None, dormant=False, health="healthy"
    )
    monkeypatch.setattr(live, "current_ib_gateway_state", lambda: state)

    response = client.get("/live/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["connected"] is True
    assert payload["last_success"] == 1_000.0
    assert payload["last_error"] is None
    assert payload["dormant"] is False
    assert payload["gateway_health"] == "healthy"


def test_live_status_reports_active_gateway_as_dormancy_violation(client, monkeypatch):
    import app.api.routes.live as live

    state = GatewayState(
        connected=True, last_success=1_000.0, last_error="must remain stopped", dormant=True, health="dormant_active"
    )
    monkeypatch.setattr(live, "current_ib_gateway_state", lambda: state)

    payload = client.get("/live/status").json()

    assert payload["connected"] is True
    assert payload["last_success"] == 1_000.0
    assert payload["last_error"] == "must remain stopped"
    assert payload["dormant"] is True
    assert payload["gateway_health"] == "dormant_active"
