from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse


router = APIRouter()


@router.get("/strategy-dashboard", response_class=HTMLResponse)
def strategy_dashboard():
    """
    Serve the legacy `STRATEGY_DASHBOARD.html` with the plot-data URL rewritten
    to use the running API (`/api/plot-data` via nginx).
    """
    path = Path("/app/STRATEGY_DASHBOARD.html")
    if not path.exists():
        raise HTTPException(status_code=404, detail="STRATEGY_DASHBOARD.html not found in container")

    html = path.read_text(encoding="utf-8", errors="ignore")

    # Rewrite fetch target from file-relative cache path to API endpoint.
    html = html.replace(
        "new URL('./.cache/plot_data.json', window.location.href);",
        "new URL('/api/plot-data', window.location.href);",
    )
    # Make the error message less confusing when served over HTTP
    html = html.replace("'.cache/plot_data.json'", "'/api/plot-data'")

    return HTMLResponse(content=html)

