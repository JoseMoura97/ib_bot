from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.worker.celery_app import celery_app


router = APIRouter()


def _plot_data_path() -> Path:
    # Default to repo-root .cache when running in docker images (WORKDIR=/app)
    p = os.getenv("PLOT_DATA_PATH") or "/app/.cache/plot_data.json"
    return Path(p)


def _validation_results_path() -> Path:
    p = os.getenv("VALIDATION_RESULTS_PATH") or "/app/.cache/last_validation_results.json"
    return Path(p)


@router.get("")
def get_plot_data():
    path = _plot_data_path()
    if not path.exists():
        # Return a small stub payload so the UI can still load end-to-end on fresh installs.
        # Users can click "Refresh plot data" to queue generation.
        return JSONResponse(
            {
                "generated_at": None,
                "data_source": "missing",
                "price_source": os.getenv("PRICE_SOURCE") or "unknown",
                "strategies": {},
                "benchmark": None,
                "missing": True,
                "detail": f"plot_data.json not found at {path}",
            }
        )
    # Read JSON so we can patch missing fields and fall back when empty.
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return JSONResponse(
            {
                "generated_at": None,
                "data_source": "error",
                "price_source": os.getenv("PRICE_SOURCE") or "unknown",
                "strategies": {},
                "benchmark": None,
                "missing": True,
                "detail": f"plot_data.json unreadable: {type(e).__name__}: {e}",
            }
        )

    if not isinstance(payload, dict):
        payload = {"generated_at": None, "strategies": {}, "benchmark": None}

    payload.setdefault("data_source", os.getenv("PLOT_DATA_SOURCE") or "unknown")
    payload.setdefault("price_source", os.getenv("PRICE_SOURCE") or "unknown")
    payload.setdefault("strategies", {})
    payload.setdefault("benchmark", None)

    # REMOVED: Synthetic fallback generation
    # Users should only see real data. If plot_data.json is empty, they need to click "Update Data".

    return JSONResponse(payload)


@router.post("/refresh")
def refresh_plot_data(force: bool = True, max_age_hours: int = 24):
    """
    Enqueue a background refresh of .cache/plot_data.json.
    """
    ar = celery_app.send_task("refresh_plot_data_task", kwargs={"force": bool(force), "max_age_hours": int(max_age_hours)})
    return {"queued": True, "task_id": getattr(ar, "id", None)}


@router.get("/refresh/{task_id}")
def refresh_plot_data_status(task_id: str):
    """
    Check Celery task status for a plot-data refresh.
    """
    r = celery_app.AsyncResult(task_id)
    state = getattr(r, "state", None) or "UNKNOWN"
    detail = None
    progress = None
    
    if state == "PROGRESS":
        # Extract progress metadata
        try:
            info = getattr(r, "info", None)
            if isinstance(info, dict):
                progress = {
                    "stage": info.get("stage", "running"),
                    "percent": info.get("percent", 0),
                    "strategies_count": info.get("strategies_count"),
                }
        except Exception:
            pass
    elif state in {"FAILURE", "REVOKED"}:
        try:
            detail = str(getattr(r, "result", None))
        except Exception:
            detail = None
    
    return {"task_id": task_id, "state": state, "detail": detail, "progress": progress}

