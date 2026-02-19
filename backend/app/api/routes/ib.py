from __future__ import annotations

import asyncio
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.ib_worker import call_ib, configure_ib_connection, current_ib_connection


router = APIRouter()


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _connect_ib():
    """
    Backwards-compatible wrapper.

    We keep a persistent thread-local connection so "Refresh balances" doesn't
    flip IB Gateway's API client to disconnected after every request.
    """
    # Ensure event loop for this AnyIO worker thread (legacy; get_ib also does this).
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    # We no longer return the IB object because it must be used from the worker thread.
    # Keep this function for legacy call sites (none expected) and for parity with docs.
    raise RuntimeError("_connect_ib is deprecated; use call_ib(...) instead")


def _normalize_accounts(raw: Any) -> list[str]:
    """
    Normalize IB "managed accounts" into a stable list[str].

    Depending on IB API / wrappers, this can be:
    - list[str] (ideal)
    - comma-separated str (ibapi callback payload)
    - list containing a comma-separated str (some wrappers)
    """
    if raw is None:
        return []

    def _split(s: str) -> list[str]:
        # Accept comma, semicolon, whitespace, and newlines as separators.
        return [p for p in re.split(r"[,\s;]+", s) if p]

    parts: list[str] = []
    if isinstance(raw, str):
        parts = _split(raw)
    else:
        # Try iterating, but fall back to stringifying the value if needed.
        try:
            it = list(raw)  # type: ignore[arg-type]
        except Exception:
            it = [raw]
        for item in it:
            if item is None:
                continue
            if isinstance(item, str):
                parts.extend(_split(item))
            else:
                parts.append(str(item))

    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        s = str(p).strip()
        if not s:
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _account_values_for_account(ib: Any, account_id: str) -> list[Any]:
    """
    Prefer `accountValues(account_id)` for individual accounts; if empty, fall back
    to `accountSummary(group="All")` and filter rows for the account.
    """
    # 1) accountValues(account_id) if available
    try:
        fn = getattr(ib, "accountValues", None)
        if callable(fn):
            vals = fn(account_id) or []
            if vals:
                return vals
    except Exception:
        pass

    # 2) accountSummary(account_id) if it returns anything
    try:
        vals = ib.accountSummary(account_id) or []
        if vals:
            return vals
    except Exception:
        pass

    # 3) accountSummary(group="All") then filter
    try:
        try:
            rows = ib.accountSummary(group="All") or []
        except TypeError:
            rows = ib.accountSummary("All") or []
    except Exception:
        return []

    out: list[Any] = []
    for r in rows:
        acct = getattr(r, "account", None)
        if acct == account_id:
            out.append(r)
    return out


def _positions_for_account(ib: Any, account_id: str) -> list[Any]:
    """
    Prefer `positions(account_id)`; if empty, fall back to `positions()` and filter.
    """
    try:
        vals = ib.positions(account_id) or []
        if vals:
            return vals
    except Exception:
        pass

    try:
        vals = ib.positions() or []
    except Exception:
        return []

    out: list[Any] = []
    for p in vals:
        acct = getattr(p, "account", None)
        if acct == account_id:
            out.append(p)
    return out


def _accounts_from_account_summary(ib: Any) -> list[str]:
    """
    Fallback account discovery from account summary.

    In some setups, `managedAccounts()` can be incomplete transiently; querying
    `accountSummary(group="All")` and extracting the `account` field can expose
    the full set (matching the legacy dashboard approach).
    """
    try:
        # ib_insync supports either `accountSummary(group=...)` or positional forms,
        # depending on version/wrapper.
        try:
            rows = ib.accountSummary(group="All") or []
        except TypeError:
            # Older signature: `accountSummary(group)` or `accountSummary()`.
            rows = ib.accountSummary("All") or []
    except Exception:
        return []

    seen: set[str] = set()
    out: list[str] = []
    for r in rows:
        acct = getattr(r, "account", None)
        s = str(acct).strip() if acct is not None else ""
        if not s or s == "All":
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _managed_accounts(ib: Any) -> list[str]:
    """
    Robust managed-accounts retrieval.

    We prefer `ib.managedAccounts()` but fall back to `ib.wrapper.accounts`
    or `accountSummary(group="All")` if that provides a richer list.
    """
    raw = None
    try:
        raw = ib.managedAccounts()
    except Exception:
        raw = None
    a1 = _normalize_accounts(raw)

    wrapper = getattr(ib, "wrapper", None)
    a2 = _normalize_accounts(getattr(wrapper, "accounts", None))

    a3 = _accounts_from_account_summary(ib)

    # Pick the richest list, preserving order.
    best = a1
    if len(a2) > len(best):
        best = a2
    if len(a3) > len(best):
        best = a3
    return best


def _extra_accounts() -> list[str]:
    """
    Operator-provided accounts to include in dropdown.
    Set via `IB_EXTRA_ACCOUNTS="U1,U2,U3"`.
    """
    raw = getattr(settings, "ib_extra_accounts", None)
    return _normalize_accounts(raw)


def _merge_accounts(*parts: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for a in part or []:
            if not a:
                continue
            if a in seen:
                continue
            seen.add(a)
            merged.append(a)
    return merged


def _account_values_to_dicts(vals: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for v in vals or []:
        out.append(
            {
                "account": getattr(v, "account", None),
                "tag": getattr(v, "tag", None),
                "value": getattr(v, "value", None),
                "currency": getattr(v, "currency", None),
                "modelCode": getattr(v, "modelCode", None),
            }
        )
    return out


def _positions_to_dicts(pos: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in pos or []:
        c = getattr(p, "contract", None)
        out.append(
            {
                "account": getattr(p, "account", None),
                "position": getattr(p, "position", None),
                "avgCost": getattr(p, "avgCost", None),
                "contract": {
                    "conId": getattr(c, "conId", None),
                    "symbol": getattr(c, "symbol", None),
                    "localSymbol": getattr(c, "localSymbol", None),
                    "secType": getattr(c, "secType", None),
                    "currency": getattr(c, "currency", None),
                    "exchange": getattr(c, "exchange", None),
                    "primaryExchange": getattr(c, "primaryExchange", None),
                },
            }
        )
    return out


@router.get("/status", response_model=dict[str, Any])
def ib_status(extra_accounts: str | None = None):
    """
    Lightweight status endpoint for the Live page.
    """
    conn = current_ib_connection()
    try:
        base_accounts = call_ib(lambda ib: _managed_accounts(ib), timeout=10.0)
    except HTTPException as e:
        return {"connected": False, "host": conn["host"], "port": conn["port"], "error": e.detail}

    merged = _merge_accounts(base_accounts or [], _extra_accounts(), _normalize_accounts(extra_accounts))
    return {"connected": True, "host": conn["host"], "port": conn["port"], "accounts": merged}


@router.get("/accounts", response_model=list[dict[str, Any]])
def list_ib_accounts(extra_accounts: str | None = None):
    base_accounts = call_ib(lambda ib: _managed_accounts(ib), timeout=10.0)
    merged = _merge_accounts(base_accounts or [], _extra_accounts(), _normalize_accounts(extra_accounts))
    return [{"account_id": a} for a in merged]


@router.get("/accounts/{account_id}/summary", response_model=list[dict[str, Any]])
def ib_account_summary(account_id: str):
    summary = call_ib(lambda ib: _account_values_for_account(ib, account_id), timeout=15.0)
    return _account_values_to_dicts(summary)


@router.get("/accounts/{account_id}/positions", response_model=list[dict[str, Any]])
def ib_account_positions(account_id: str):
    pos = call_ib(lambda ib: _positions_for_account(ib, account_id), timeout=15.0)
    return _positions_to_dicts(pos)


@router.get("/accounts/{account_id}/snapshot", response_model=dict[str, Any])
def ib_account_snapshot(account_id: str):
    """
    Convenience endpoint for the Live UI:
    - key balances (NLV, AvailableFunds, TotalCashValue) by currency
    - cash_by_currency
    - positions (no market prices; just size + avg cost)
    """
    def _fetch(ib: Any):
        return _account_values_for_account(ib, account_id), _positions_for_account(ib, account_id)

    summary_vals, pos_vals = call_ib(_fetch, timeout=15.0)
    summary_raw = _account_values_to_dicts(summary_vals)
    positions_raw = _positions_to_dicts(pos_vals)

    # Extract common tags by currency
    tags_of_interest = {
        "NetLiquidation",
        "AvailableFunds",
        "TotalCashValue",
        "CashBalance",
        "SettledCash",
    }
    by_tag: dict[str, dict[str, float]] = {}
    cash_by_currency: dict[str, float] = {}

    for row in summary_raw:
        tag = str(row.get("tag") or "")
        ccy = str(row.get("currency") or "")
        if not tag or not ccy:
            continue
        if tag not in tags_of_interest:
            continue
        val = _to_float(row.get("value"))
        if val is None:
            continue
        by_tag.setdefault(tag, {})[ccy] = float(val)
        if tag == "TotalCashValue":
            cash_by_currency[ccy] = float(val)

    return {
        "account_id": account_id,
        "host": current_ib_connection()["host"],
        "port": current_ib_connection()["port"],
        "summary": summary_raw,
        "positions": positions_raw,
        "key": by_tag,
        "cash_by_currency": cash_by_currency,
    }


class IbConnectRequest(BaseModel):
    host: str = Field(..., min_length=1)
    port: int = Field(..., ge=1, le=65535)


@router.post("/connect", response_model=dict[str, Any])
def ib_connect(req: IbConnectRequest):
    """
    Update the backend's IB connection target (host/port) at runtime.
    Useful when switching between paper (4001) and live (4002), or when
    connecting to TWS (7496/7497).
    """
    configure_ib_connection(host=req.host, port=int(req.port))
    conn = current_ib_connection()
    try:
        accounts = call_ib(lambda ib: _managed_accounts(ib), timeout=10.0)
        return {"connected": True, "host": conn["host"], "port": conn["port"], "accounts": accounts}
    except HTTPException as e:
        return {"connected": False, "host": conn["host"], "port": conn["port"], "error": e.detail}

