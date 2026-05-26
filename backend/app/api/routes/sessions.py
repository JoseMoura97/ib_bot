"""
IB Session routes — thin proxy to the ibeam session manager (port 5056).
Lets the frontend connect/disconnect IB accounts and poll auth status.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sm_url(path: str) -> str:
    """Build a session-manager URL."""
    base = settings.ibeam_session_manager_url.rstrip("/")
    return f"{base}/{path.lstrip('/')}"


def _extract_detail(response: "httpx.Response") -> str:
    """Pull the human-readable message out of a session-manager error response."""
    try:
        body = response.json()
        if isinstance(body, dict) and "detail" in body:
            inner = body["detail"]
            if isinstance(inner, str):
                try:
                    import json as _json
                    parsed = _json.loads(inner)
                    if isinstance(parsed, dict) and "detail" in parsed:
                        return str(parsed["detail"])
                except Exception:
                    pass
            return str(inner)
        return response.text
    except Exception:
        return response.text


async def _sm_get(path: str) -> Any:
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(_sm_url(path))
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError as exc:
            raise HTTPException(
                status_code=503,
                detail="Session manager is not reachable. Make sure it's running: "
                       "uvicorn infra/ibeam/session_manager:app --port 5056",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=_extract_detail(exc.response)) from exc


async def _sm_post(path: str, body: dict[str, Any]) -> Any:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.post(_sm_url(path), json=body)
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError as exc:
            raise HTTPException(
                status_code=503,
                detail="Session manager is not reachable. Make sure it's running: "
                       "uvicorn infra/ibeam/session_manager:app --port 5056",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=_extract_detail(exc.response)) from exc


async def _sm_delete(path: str) -> Any:
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.delete(_sm_url(path))
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError as exc:
            raise HTTPException(status_code=503, detail="Session manager is not reachable.") from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=_extract_detail(exc.response)) from exc


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ConnectRequest(BaseModel):
    ib_account: str = Field(..., min_length=1, description="IB login username (e.g. jibas.bot)")
    ib_password: str = Field(..., min_length=1, description="IB password")
    totp_secret: str = Field(..., min_length=16, description="Base32 TOTP secret from authenticator app setup")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/connect", status_code=201)
async def connect_account(body: ConnectRequest) -> dict[str, Any]:
    """
    Spin up an ibeam container for the given IB account.
    If a session already exists (409), returns it directly so the frontend
    can poll for auth status without showing an error.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.post(_sm_url("sessions"), json={
                "account": body.ib_account,
                "password": body.ib_password,
                "totp_key": body.totp_secret,
            })
            if r.status_code == 409:
                sessions = await _sm_get("sessions")
                existing = next(
                    (s for s in (sessions or []) if s.get("session_id") == body.ib_account),
                    None,
                )
                return existing or {"session_id": body.ib_account, "status": "existing"}
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError as exc:
            raise HTTPException(
                status_code=503,
                detail="Session manager is not reachable. Make sure it's running: "
                       "uvicorn infra/ibeam/session_manager:app --port 5056",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=_extract_detail(exc.response),
            ) from exc


@router.get("")
async def list_sessions() -> list[dict[str, Any]]:
    """Return all known ibeam sessions and their current status."""
    return await _sm_get("sessions")


@router.get("/{account_id}/status")
async def session_status(account_id: str) -> dict[str, Any]:
    """
    Query the ibeam container's auth status directly.
    Poll this after calling /connect until authenticated=true (up to ~90s).
    """
    return await _sm_get(f"sessions/{account_id}/status")


@router.delete("/{account_id}")
async def disconnect_account(account_id: str) -> dict[str, Any]:
    """Stop and remove the ibeam container for the given account."""
    return await _sm_delete(f"sessions/{account_id}")
