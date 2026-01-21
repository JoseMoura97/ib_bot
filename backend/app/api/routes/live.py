from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import settings


router = APIRouter()


@router.get("/status")
def live_status():
    return {
        "enabled": bool(settings.enable_live_trading),
        "ib_host": settings.ib_host,
        "ib_port": settings.ib_port,
    }


@router.post("/rebalance")
def live_rebalance():
    """
    Live trading is intentionally guarded.
    This endpoint is a placeholder; real implementation should:
    - require explicit enable flag
    - require confirmation params (max % NLV, max order size, etc.)
    - run in a background task and log all orders/fills
    """
    if not settings.enable_live_trading:
        raise HTTPException(status_code=403, detail="Live trading disabled (set ENABLE_LIVE_TRADING=1)")
    raise HTTPException(status_code=501, detail="Not implemented yet")
