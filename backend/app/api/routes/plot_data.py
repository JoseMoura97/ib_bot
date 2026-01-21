from __future__ import annotations

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
    return FileResponse(str(path), media_type="application/json", filename="plot_data.json")


@router.post("/refresh")
def refresh_plot_data(force: bool = True, max_age_hours: int = 24):
    """
    Enqueue a background refresh of .cache/plot_data.json.
    """
    celery_app.send_task("refresh_plot_data_task", kwargs={"force": bool(force), "max_age_hours": int(max_age_hours)})
    return {"queued": True}

