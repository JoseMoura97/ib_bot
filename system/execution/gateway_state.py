"""One fail-closed IB Gateway state contract for execution paths.

This module deliberately has no socket, web-framework, or broker dependency.
It turns an already-observed Gateway snapshot into the only predicate that
authorizes a broker submission.  Callers must obtain the snapshot without
opening a connection; a dormant Gateway must remain dormant while being
reported and while refusing execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class GatewayStateGuardError(RuntimeError):
    """The Gateway is not in the single state that permits execution."""


@dataclass(frozen=True)
class GatewayStatePolicy:
    dormant: bool
    max_success_age_seconds: float


@dataclass(frozen=True)
class GatewayState:
    connected: bool
    last_success: float | None
    last_error: str | None
    dormant: bool
    health: str
    consecutive_failures: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "last_success": self.last_success,
            "last_error": self.last_error,
            "dormant": self.dormant,
            "health": self.health,
            "consecutive_failures": self.consecutive_failures,
        }


def gateway_state_from_connection(
    connection: Mapping[str, Any],
    *,
    policy: GatewayStatePolicy,
    now: float,
) -> GatewayState:
    """Normalize a raw worker snapshot without attempting a Gateway call."""
    connected = bool(connection.get("connected", False))
    raw_success = connection.get("last_success", connection.get("last_connect_ok_at"))
    try:
        last_success = float(raw_success) if raw_success is not None else None
    except (TypeError, ValueError):
        last_success = None
    raw_error = connection.get("last_error")
    last_error = str(raw_error) if raw_error else None
    try:
        consecutive_failures = max(0, int(connection.get("consecutive_failures", 0)))
    except (TypeError, ValueError):
        consecutive_failures = 0

    if policy.dormant:
        health = "dormant_active" if connected else "dormant"
    elif not connected:
        health = "disconnected"
    elif last_success is None or now - last_success > max(0.0, float(policy.max_success_age_seconds)):
        health = "stale"
    else:
        health = "healthy"

    return GatewayState(
        connected=connected,
        last_success=last_success,
        last_error=last_error,
        dormant=bool(policy.dormant),
        health=health,
        consecutive_failures=consecutive_failures,
    )


def assert_gateway_execution_ready(state: GatewayState | Mapping[str, Any]) -> None:
    """Permit execution only for the canonical ``healthy`` state.

    Keeping this check separate from snapshot creation lets tests inject a
    deterministic broker-free state and prevents an execution preflight from
    "refreshing" a dormant Gateway merely to decide whether it may submit.
    """
    health = state.health if isinstance(state, GatewayState) else str(state.get("health", ""))
    if health == "healthy":
        return
    detail = {
        "dormant": "IB Gateway is dormant; execution is disabled",
        "dormant_active": "IB Gateway is active during enforced dormancy; execution is disabled",
        "disconnected": "IB Gateway is disconnected; execution is disabled",
        "stale": "IB Gateway health is stale; execution is disabled",
    }.get(health, "IB Gateway state is unknown; execution is disabled")
    raise GatewayStateGuardError(detail)
