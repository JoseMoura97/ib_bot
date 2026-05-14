from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    """
    Lightweight health check. Reports IB connectivity status without
    attempting a new connection (non-invasive check against the existing worker state).
    """
    ib_connected = False
    ib_error: str | None = None
    try:
        from app.services.ib_worker import _worker
        ib = _worker._ib
        if ib is not None:
            ib_connected = bool(getattr(ib, "isConnected", lambda: False)())
    except Exception as e:
        ib_error = f"{type(e).__name__}: {e}"
    return {"ok": True, "ib_connected": ib_connected, "ib_error": ib_error}
