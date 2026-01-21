from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException


router = APIRouter()


def _client():
    try:
        from ib_web_client import IBWebClient  # repo root wrapper

        return IBWebClient()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail="IB web client not available. Ensure optional dependency `ibind` is installed and IB Client Portal Gateway is running.",
        ) from e


@router.get("/accounts", response_model=list[dict[str, Any]])
def list_ib_accounts():
    c = _client()
    try:
        return c.get_accounts() or []
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch IB accounts: {e}") from e


@router.get("/accounts/{account_id}/summary", response_model=dict[str, Any])
def ib_account_summary(account_id: str):
    c = _client()
    try:
        return c.get_account_summary(account_id) or {}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch IB account summary: {e}") from e


@router.get("/accounts/{account_id}/positions", response_model=list[dict[str, Any]])
def ib_account_positions(account_id: str):
    c = _client()
    try:
        return c.get_positions(account_id) or []
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch IB positions: {e}") from e

