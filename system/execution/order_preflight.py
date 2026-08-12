"""Fail-closed checks shared by every direct IB order-placement path.

This module deliberately has no web-framework or broker dependency so legacy
executors and the API route cannot drift into separate safety policies.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


class OrderPreFlightGuardError(RuntimeError):
    """An order was refused before it reached a broker client."""


@dataclass(frozen=True)
class OrderPreFlightPolicy:
    trading_halt: bool
    live_allowed_accounts: str | None
    max_order_notional_usd: float = 0.0
    max_aggregate_notional_usd: float = 0.0

    @classmethod
    def from_environment(cls) -> "OrderPreFlightPolicy":
        return cls(
            trading_halt=os.getenv("TRADING_HALT", "").strip().lower() in {"1", "true", "yes", "on"},
            live_allowed_accounts=os.getenv("LIVE_ALLOWED_ACCOUNTS"),
            max_order_notional_usd=_nonnegative_float(os.getenv("LIVE_MAX_ORDER_NOTIONAL_USD")),
            max_aggregate_notional_usd=_nonnegative_float(os.getenv("LIVE_MAX_AGGREGATE_NOTIONAL_USD")),
        )


def _nonnegative_float(raw: str | None) -> float:
    try:
        return max(0.0, float(raw or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _allowed_accounts(raw: str | None) -> set[str]:
    return {account.strip() for account in (raw or "").replace(";", ",").split(",") if account.strip()}


def order_pre_flight_guard(
    *,
    account_id: str | None,
    order_notional_usd: float | None,
    aggregate_notional_usd: float | None = None,
    policy: OrderPreFlightPolicy | None = None,
) -> None:
    """Reject an order before broker submission when any hard policy is breached.

    A configured notional limit needs a priced order.  If a caller cannot
    produce one, the guard fails closed instead of treating an unknown market
    order as zero dollars.
    """
    policy = policy or OrderPreFlightPolicy.from_environment()
    if policy.trading_halt:
        raise OrderPreFlightGuardError("Trading halted (TRADING_HALT=1)")

    allowed = _allowed_accounts(policy.live_allowed_accounts)
    if allowed and account_id not in allowed:
        raise OrderPreFlightGuardError(
            f"account_id {account_id!r} not in LIVE_ALLOWED_ACCOUNTS allowlist"
        )

    order_cap = float(policy.max_order_notional_usd)
    aggregate_cap = float(policy.max_aggregate_notional_usd)
    if (order_cap > 0.0 or aggregate_cap > 0.0) and order_notional_usd is None:
        raise OrderPreFlightGuardError("priced notional is required while LIVE notional caps are enabled")

    order_notional = abs(float(order_notional_usd or 0.0))
    aggregate_notional = abs(float(aggregate_notional_usd if aggregate_notional_usd is not None else order_notional))
    if order_cap > 0.0 and order_notional > order_cap:
        raise OrderPreFlightGuardError(
            f"order notional ${order_notional:,.2f} exceeds LIVE_MAX_ORDER_NOTIONAL_USD ${order_cap:,.2f}"
        )
    if aggregate_cap > 0.0 and aggregate_notional > aggregate_cap:
        raise OrderPreFlightGuardError(
            f"aggregate notional ${aggregate_notional:,.2f} exceeds "
            f"LIVE_MAX_AGGREGATE_NOTIONAL_USD ${aggregate_cap:,.2f}"
        )
